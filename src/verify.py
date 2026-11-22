"""Второй проход: узкие проверки по каждому критичному нарушению.

Модель среднего размера плохо держит длинную рубрику целиком и склонна отвечать «да», как только видит
в переписке бонус или слово «лимит». Поэтому каждое нарушение разложено на две части:

  * предпосылка — что сделал или сказал игрок (или что известно из CRM): «игрок говорил о проигрыше»,
    «игрок хотел вывести деньги», «у игрока свой лимит»;
  * нарушение — что в ответ сделал менеджер: «предложил бонус», «отговаривал от вывода».

Модель только находит цитаты, а решение принимает код:
  * цитата предпосылки должна быть из сообщения игрока (или предпосылка берётся из данных CRM);
  * цитата нарушения — из сообщения менеджера и позже по времени, чем предпосылка;
  * факты комплаенса (отписка, мультиаккаунт) — одна цитата игрока.

Вопросы взяты из определений рубрики (src/prompts/system.md), а не из конкретных диалогов.

Запуск:
    python -m src.verify --provider ollama
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request

from . import llm
from . import signals as sig
from .load import OUT_DIR, load_dialogs, load_players

# код: (вопрос о предпосылке со стороны игрока, вопрос о действии менеджера, предпосылка из CRM)
CHECKS = {
    "RG_SELF_EXCLUSION_DISCOURAGED": (
        "Игрок сам просит заблокировать аккаунт, самоисключение, паузу или лимит?",
        "В ответ на эту просьбу менеджер отговаривает, торгуется, предлагает бонус или кешбэк, или "
        "отправляет в другой отдел вместо того, чтобы оформить сам? Если менеджер оформил просьбу — «no».",
        None),
    "RG_LOSS_CHASING_ENCOURAGED": (
        "Игрок сам пишет, что проиграл, слил деньги, в минусе, в долгах или хочет отыграться? "
        "Вопросы про кешбэк, бонусы, депозиты или выводы без слов о проигрыше — «no».",
        "После этих слов игрока менеджер предлагает бонус, кешбэк, депозит или игру, чтобы вернуть "
        "проигранное? Если менеджер отказал в бонусе или предложил лимит или паузу — «no».",
        None),
    "RG_RISK_SIGNS_IGNORED": (
        "Игрок сам пишет, что всё проиграл, в долгах, просит бонус сразу после проигрыша или хочет отыграться?",
        "Менеджер в ответ даёт бонус, кешбэк или промо? Если менеджер отказал в бонусе и предложил лимит или "
        "паузу — «no».",
        {"RG_DEPOSIT_PATTERN", "RG_BONUS_DEPENDENCE"}),
    "RG_LIMIT_INCREASE_PUSHED": (
        "Игрок упоминает лимит, который он сам себе установил?",
        "Менеджер предлагает ПОВЫСИТЬ или СНЯТЬ лимит игрока? Установка нового лимита, снижение лимита или "
        "ограничение платёжной системы — «no».",
        {"LIMIT_SET"}),
    "RG_WITHDRAWAL_DISCOURAGED": (
        "Игрок хочет вывести деньги или просит отменить вывод?",
        "Менеджер отговаривает от вывода, предлагает оставить деньги на балансе, зовёт в турнир вместо вывода, "
        "пугает сроками вывода или отменяет вывод, чтобы игрок продолжил играть? Если менеджер помогает "
        "вывести быстрее — «no».",
        {"PENDING_WITHDRAWAL"}),
}
FACTS = {
    "OPT_OUT_REQUEST": "Игрок просит отписать его от рассылок, перестать писать или прекратить контакты?",
    "MULTI_ACCOUNT": "Игрок упоминает несколько аккаунтов на одного человека или семью: общую карту, аккаунт "
                     "супруга или родственника, перевод бонусов между аккаунтами?",
}

# Цитата должна быть про само действие: модель среднего размера отвечает «да» слишком охотно,
# поэтому код дополнительно проверяет, что в цитате есть признак этого действия.
# Это не подгонка под диалоги, а словарь действий из определений рубрики, на русском и английском.
MARKERS = {
    "premise": {
        "RG_SELF_EXCLUSION_DISCOURAGED": r"блок|самоисключ|пауз|лимит|закр|останов|прекрат|block|exclu|pause|limit|close|stop|break",
        "RG_LOSS_CHASING_ENCOURAGED": r"слил|проигр|минус|долг|отыгр|отбить|мимо|не везёт|не везет|lost|losing|loss|debt|chase|win back",
        "RG_RISK_SIGNS_IGNORED": r"слил|проигр|минус|долг|отыгр|отбить|мимо|ещё бонус|еще бонус|lost|losing|debt|chase",
        "RG_LIMIT_INCREASE_PUSHED": r"лимит|limit",
        "RG_WITHDRAWAL_DISCOURAGED": r"вывод|вывест|вывожу|withdraw|cash ?out|payout",
    },
    "violation": {
        "RG_SELF_EXCLUSION_DISCOURAGED": r"не будем|радикальн|передума|саппорт|поддержк|кешбэк|кэшбэк|бонус|support|instead|cashback|bonus|sure\?",
        "RG_LOSS_CHASING_ENCOURAGED": r"бонус|кешбэк|кэшбэк|фриспин|релоад|депозит|%|bonus|cashback|spins|reload|deposit",
        "RG_RISK_SIGNS_IGNORED": r"бонус|кешбэк|кэшбэк|фриспин|релоад|%|bonus|cashback|spins|reload",
        "RG_LIMIT_INCREASE_PUSHED": r"подня|повыс|увелич|сня|убра|raise|increase|lift|remove|higher",
        "RG_WITHDRAWAL_DISCOURAGED": r"остав|баланс|турнир|отмен|дней|days|keep|leave|tournament|cancel|balance",
    },
}


# Отказ от оффера — противоположность нарушения: «без бонусов», «no offers».
NEGATIONS = r"без бонус|без оффер|без промо|бонусов не будет|не дам|no offers|no bonus|without (any )?offers"


def _has(code: str, part: str, quote: str) -> bool:
    import re
    text = quote.lower()
    if part == "violation" and re.search(NEGATIONS, text):
        return False
    return bool(re.search(MARKERS[part][code], text))


SCHEMA = llm._obj({
    "premise": {"type": "string", "enum": ["yes", "no"]},
    "premise_quote": {"type": "string", "description": "Дословная цитата игрока или пустая строка"},
    "violation": {"type": "string", "enum": ["yes", "no"]},
    "violation_quote": {"type": "string", "description": "Дословная цитата менеджера или пустая строка"},
    "explanation": {"type": "string", "description": "Одно предложение по-русски"},
})
FACT_SCHEMA = llm._obj({
    "answer": {"type": "string", "enum": ["yes", "no"]},
    "quote": {"type": "string", "description": "Дословная цитата игрока или пустая строка"},
    "explanation": {"type": "string", "description": "Одно предложение по-русски"},
})

SYSTEM = ("Ты проверяешь переписку VIP-менеджера онлайн-казино с игроком на одно конкретное нарушение. "
          "Отвечай строго на заданные вопросы. «yes» — только если это прямо написано в переписке. "
          "Цитаты приводи дословно, из одного сообщения. Объяснение — одно предложение по-русски.")

CACHE = {"ollama": OUT_DIR / "verify_ollama", "claude": OUT_DIR / "verify_claude"}


def transcript(d: dict) -> str:
    return "\n".join(f"[{m['sent_at']:%d.%m %H:%M}] {'Игрок' if m['from'] == 'player' else 'Менеджер'}: {m['text']}"
                     for m in d["messages"])


def _call(provider: str, user: str, schema: dict) -> dict:
    if provider == "ollama":
        body = {"model": llm.OLLAMA_MODEL, "stream": False, "format": schema,
                "options": {"temperature": 0, "num_ctx": 4096},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
        req = urllib.request.Request(f"{llm.OLLAMA_URL}/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(json.loads(r.read())["message"]["content"])
    import anthropic
    resp = anthropic.Anthropic().beta.messages.create(
        model=llm.MODEL, max_tokens=2000, system=SYSTEM, messages=[{"role": "user", "content": user}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def _msg_index(quote: str, d: dict, who: str) -> int | None:
    """Номер сообщения автора who, из которого взята цитата, или None."""
    probe = " ".join(llm._norm(quote).strip("[]").replace("'", "").replace(",", " ").split())
    if len(probe) < 6:
        return None
    probe = probe[:25]
    for i, m in enumerate(d["messages"]):
        if m["from"] != who:
            continue
        msg = " ".join(llm._norm(m["text"]).strip("[]").replace("'", "").replace(",", " ").split())
        if probe in msg or msg[:25] in probe:
            return i
    return None


def decide(code: str, res: dict, d: dict, crm: set[str]) -> dict:
    """Решение кодом по ответу модели."""
    if code in FACTS:
        ok = res["answer"] == "yes" and _msg_index(res["quote"], d, "player") is not None
        return {"confirmed": ok, "evidence": res["quote"], "why": "цитата игрока найдена" if ok else ""}
    _, _, crm_premise = CHECKS[code]
    p_idx = _msg_index(res["premise_quote"], d, "player") if res["premise"] == "yes" else None
    premise_from_crm = bool(crm_premise and crm & crm_premise)
    v_idx = _msg_index(res["violation_quote"], d, "manager") if res["violation"] == "yes" else None
    if v_idx is None:
        return {"confirmed": False, "evidence": "", "why": "нет подтверждённой цитаты менеджера"}
    # Цитату модели проверяем по полному тексту сообщения: модели обрезают цитаты.
    v_text = d["messages"][v_idx]["text"]
    if not _has(code, "violation", v_text):
        return {"confirmed": False, "evidence": "", "why": "в цитате менеджера нет признака нарушения"}
    if p_idx is not None and not _has(code, "premise", d["messages"][p_idx]["text"]):
        p_idx = None
    if p_idx is not None and v_idx > p_idx:
        return {"confirmed": True, "evidence": res["violation_quote"], "context": res["premise_quote"],
                "why": "слова игрока, затем ответ менеджера"}
    if premise_from_crm:
        return {"confirmed": True, "evidence": res["violation_quote"],
                "context": "данные CRM: " + ", ".join(sorted(crm & crm_premise)), "why": "данные CRM и ответ менеджера"}
    return {"confirmed": False, "evidence": "", "why": "нет предпосылки со стороны игрока"}


def verify_dialog(provider: str, d: dict, crm: set[str]) -> dict:
    """Проверки по всем нарушениям для диалога, с кэшем по хэшу вопроса и переписки."""
    cache_dir = CACHE[provider]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{d['dialog_id']}.json"
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    out = {}
    items = [(c, f"Вопрос 1: {q1}\nВопрос 2: {q2}", SCHEMA) for c, (q1, q2, _) in CHECKS.items()]
    items += [(c, f"Вопрос: {q}", FACT_SCHEMA) for c, q in FACTS.items()]
    for code, question, schema in items:
        key = hashlib.sha256(f"{provider}|{SYSTEM}|{question}|{transcript(d)}".encode()).hexdigest()[:16]
        if cached.get(code, {}).get("key") == key:
            res = cached[code]["model"]
        else:
            res = _call(provider, f"Переписка:\n{transcript(d)}\n\n{question}", schema)
        out[code] = {"key": key, "model": res, **decide(code, res, d, crm),
                     "explanation": res.get("explanation", "")}
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


ALL_CODES = set(CHECKS) | set(FACTS)


def merge(analysis: dict, checks: dict) -> dict:
    """Критичные флаги берутся из проверки, остальные — из основного разбора."""
    flags = [f for f in analysis["flags"] + [{k: v for k, v in f.items() if k != "review_reason"}
                                             for f in analysis.get("review_flags", [])]
             if f["code"] not in ALL_CODES]
    for code, c in checks.items():
        if c["confirmed"]:
            flags.append({"code": code, "evidence": c["evidence"], "explanation": c["explanation"],
                          "severity": llm.FLAG_SEVERITY[code], "verified": True})
    if any(c["confirmed"] for c in checks.values()):
        analysis["overall"] = "critical"
        flags = [f for f in flags if f["code"] != "GOOD_PRACTICE"]
    elif analysis["overall"] == "critical":
        # Модель считала контакт критичным, но ни одно критичное нарушение не подтвердилось.
        analysis["overall"] = "poor"
    analysis["flags"], analysis["review_flags"] = flags, []
    analysis["verified"] = True
    return analysis


def crm_codes() -> dict[str, set[str]]:
    """Сигналы из данных по игроку — предпосылки, которые не нужно спрашивать у модели."""
    return {p["player_id"]: {s["code"] for s in p["signals"]} for p in sig.build()["players"]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=list(CACHE), default="ollama")
    ap.add_argument("--only", help="список dialog_id через запятую")
    args = ap.parse_args()

    out_path = llm.PROVIDERS[args.provider]["out"]
    data = json.loads(out_path.read_text(encoding="utf-8"))
    dialogs = {d["dialog_id"]: d for d in load_dialogs()[0]}
    crm = crm_codes()
    only = set(args.only.split(",")) if args.only else None
    for r in data["results"]:
        did = r["dialog_id"]
        if only and did not in only:
            continue
        try:
            checks = verify_dialog(args.provider, dialogs[did], crm[dialogs[did]["player_id"]])
        except Exception as e:  # одна ошибка не должна ронять весь прогон
            print(f"{did}  ERROR {e}", file=sys.stderr, flush=True)
            continue
        merge(r["analysis"], checks)
        llm.apply_guards(r["analysis"], dialogs[did])
        found = [c for c, v in checks.items() if v["confirmed"]]
        print(f"{did}  {', '.join(found) or '—'}", flush=True)
    data["verified"] = True
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"готово → {out_path}")


if __name__ == "__main__":
    main()
