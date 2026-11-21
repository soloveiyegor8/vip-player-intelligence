"""LLM-разбор диалогов через Claude API.

На вход модели: профиль игрока из CRM + сигналы из signals.py + переписка.
На выходе: JSON строго по схеме ANALYSIS_SCHEMA (structured outputs).
Результат каждого диалога кэшируется в out/llm/<dialog_id>.json по хэшу входа,
поэтому повторный запуск не тратит токены, пока не поменялись промпт, модель или данные.

Запуск:
    python -m src.llm                    # все диалоги (из кэша, где можно)
    python -m src.llm --only D010,D003   # выборочно
    python -m src.llm --force            # игнорировать кэш
    python -m src.llm --dry-run D010     # показать промпт без вызова API
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

from . import signals as sig
from .load import OUT_DIR, ROOT, load_dialogs, load_players


def load_env(path: Path = ROOT / ".env") -> None:
    """Подхватывает KEY=VALUE из .env (файл в .gitignore). Переменные окружения имеют приоритет."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

MODEL = "claude-opus-5-5"
EFFORT = "high"          # разбор с RG-нюансами — нужен вдумчивый анализ; на 40 диалогах цена небольшая
MAX_TOKENS = 16000
WORKERS = 4

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"
CACHE_DIR = OUT_DIR / "llm"

# Серьёзность флага задаёт код, а не модель: так очередь стабильна и правится в одном месте.
FLAG_SEVERITY = {
    "RG_SELF_EXCLUSION_DISCOURAGED": "critical",
    "RG_LOSS_CHASING_ENCOURAGED": "critical",
    "RG_LIMIT_INCREASE_PUSHED": "critical",
    "RG_WITHDRAWAL_DISCOURAGED": "critical",
    "RG_RISK_SIGNS_IGNORED": "critical",
    "OPT_OUT_REQUEST": "critical",
    "MULTI_ACCOUNT": "critical",
    "JURISDICTION_CHANGE": "high",
    "MISLEADING_INFO": "high",
    "PRESSURE_TACTICS": "high",
    "ISSUE_IGNORED": "high",
    "PROMISE_NOT_KEPT": "high",
    "UNRESOLVED_PAYMENT": "high",
    "RUDE_TONE": "high",
    "CHURN_THREAT": "high",
    "PASSED_THE_BUCK": "medium",
    "SLOW_RESPONSE": "medium",
    "VAGUE_ANSWER": "medium",
    "WRONG_NAME": "medium",
    "LATE_GREETING": "low",
    "FEEDBACK_NOT_ESCALATED": "low",
    "GENERIC_OUTREACH": "low",
    "GOOD_PRACTICE": "info",
}

SCORE_KEYS = ["responsiveness", "problem_solving", "accuracy", "personalization", "tone", "responsible_gambling"]

INTENTS = [
    "deposit_issue", "withdrawal_issue", "bonus_request", "bonus_terms_question", "cashback_question",
    "limit_or_exclusion_request", "opt_out_request", "complaint", "tech_issue", "vip_terms_question",
    "competitor_comparison", "account_change", "small_talk", "manager_promo", "manager_care_checkin",
    "manager_greeting", "manager_onboarding", "manager_feedback_request", "other",
]


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


ANALYSIS_SCHEMA = _obj({
    "player_intent": {"type": "string", "enum": INTENTS,
                      "description": "Главная тема диалога; для диалогов, начатых менеджером, — тип его обращения"},
    "intent_summary": {"type": "string", "description": "Суть запроса или ситуации, одно предложение"},
    "resolved": {"type": "string", "enum": ["yes", "partially", "no", "not_applicable"]},
    "needs_reply": {"type": "boolean", "description": "Ждёт ли игрок ответа менеджера прямо сейчас"},
    "flags": {"type": "array", "items": _obj({
        "code": {"type": "string", "enum": list(FLAG_SEVERITY)},
        "evidence": {"type": "string", "description": "Дословная цитата из переписки или факт из профиля"},
        "explanation": {"type": "string"},
    })},
    "scores": _obj({k: {"type": "integer", "description": "0–3"} for k in SCORE_KEYS}),
    "overall": {"type": "string", "enum": ["critical", "poor", "ok", "good", "excellent"]},
    "summary": {"type": "string", "description": "Что произошло, 1–2 предложения для тимлида"},
    "manager_feedback": {"type": "string", "description": "Коучинг для менеджера: что сделано хорошо и что исправить"},
    "next_action": _obj({
        "owner": {"type": "string", "enum": ["manager", "teamlead", "payments", "compliance", "support", "product"]},
        "action": {"type": "string"},
        "deadline": {"type": "string", "enum": ["now", "today", "this_week", "none"]},
    }),
    "draft_message": {"type": "string", "description": "Черновик сообщения игроку на его языке или пустая строка"},
})

PROFILE_FIELDS = [
    "brand", "geo", "language", "status", "vip_since", "account_status",
    "deposits_30d_usd", "deposits_30d_count", "deposits_prev_30d_usd", "deposits_prev_30d_count",
    "last_deposit_at", "failed_deposits_7d", "withdrawals_30d_usd", "last_withdrawal_at",
    "pending_withdrawal_usd", "bonuses_30d_usd", "bonuses_30d_count", "last_login_at", "birthday", "favorite_game",
]


# ─────────────────────────── сборка запроса ───────────────────────────

def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_user_message(dialog: dict, player: dict, player_sig: dict, dialog_metrics: dict, as_of: str) -> str:
    profile = "\n".join(f"- {k}: {_fmt(player.get(k))}" for k in PROFILE_FIELDS)
    signals = "\n".join(f"- [{s['severity']}] {s['code']}: {s['detail']}" for s in player_sig["signals"]) or "- нет"
    metrics = (
        f"- время ответов менеджера, мин: {dialog_metrics['response_times_min'] or '—'}\n"
        f"- последнее сообщение: {dialog_metrics['last_from']}, "
        f"сообщений игрока без ответа в конце: {dialog_metrics['unanswered_player_msgs']}"
    )
    lines = []
    for m in dialog["messages"]:
        who = "Игрок" if m["from"] == "player" else f"Менеджер ({dialog['manager']})"
        lines.append(f"[{m['sent_at']:%Y-%m-%d %H:%M}] {who}: {m['text']}")
    transcript = "\n".join(lines)

    return (
        f"Дата среза (as_of): {as_of}\n"
        f"Диалог {dialog['dialog_id']}, канал: {dialog['channel']}, менеджер: {dialog['manager']}, "
        f"игрок: {dialog['player_id']}\n\n"
        f"## Профиль игрока\n{profile}\n\n"
        f"## Сигналы из данных (посчитаны кодом)\n{signals}\n\n"
        f"## Метрики диалога\n{metrics}\n\n"
        f"## Переписка\n{transcript}\n\n"
        "Разбери этот диалог по инструкции."
    )


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    if hasattr(v, "strftime"):
        return "—" if str(v) == "NaT" else v.strftime("%Y-%m-%d")
    return str(v)


# ─────────────────────────── вызов модели ───────────────────────────

class AnalysisError(RuntimeError):
    pass


def call_claude(client: anthropic.Anthropic, system: str, user: str) -> tuple[dict, dict]:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        # Неизменная инструкция кэшируется; меняется только сообщение с диалогом.
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA},
        },
        # Если классификатор безопасности откажет (тема азартных игр), запрос перезапустится на запасной модели.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise AnalysisError(f"модель отказалась: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise AnalysisError("ответ обрезан по max_tokens")
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise AnalysisError(f"нет текстового ответа, stop_reason={response.stop_reason}")
    try:
        analysis = json.loads(text)
    except json.JSONDecodeError as e:
        raise AnalysisError(f"невалидный JSON: {e}") from e

    u = response.usage
    usage = {
        "model": response.model,
        "input_tokens": u.input_tokens,
        "output_tokens": u.output_tokens,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
    }
    return analysis, usage


def postprocess(analysis: dict) -> dict:
    """Добавляем серьёзность флагов и зажимаем оценки в 0–3 — модель может выйти за диапазон."""
    for f in analysis["flags"]:
        f["severity"] = FLAG_SEVERITY[f["code"]]
    analysis["flags"].sort(key=lambda f: sig.SEVERITY_ORDER[f["severity"]])
    analysis["scores"] = {k: max(0, min(3, int(v))) for k, v in analysis["scores"].items()}
    analysis["score_total"] = sum(analysis["scores"].values())
    return analysis


# ─────────────────────────── оркестрация ───────────────────────────

def prepare_inputs() -> tuple[str, list[dict]]:
    """Готовит пары (диалог, текст запроса) для всех диалогов."""
    dialogs, as_of = load_dialogs()
    players = load_players()
    built = sig.build(as_of)
    p_sig = {p["player_id"]: p for p in built["players"]}
    d_met = {d["dialog_id"]: d for d in built["dialogs"]}
    system = system_prompt()

    jobs = []
    for d in dialogs:
        player = players.loc[d["player_id"]].to_dict()
        user = build_user_message(d, player, p_sig[d["player_id"]], d_met[d["dialog_id"]], as_of.date().isoformat())
        key = hashlib.sha256(f"{MODEL}|{EFFORT}|{system}|{user}".encode()).hexdigest()[:16]
        jobs.append({"dialog": d, "user": user, "key": key})
    return system, jobs


def analyze_one(client: anthropic.Anthropic, system: str, job: dict, force: bool) -> dict:
    d = job["dialog"]
    path = CACHE_DIR / f"{d['dialog_id']}.json"
    if not force and path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("input_key") == job["key"] and "analysis" in cached:
            return {**cached, "from_cache": True}

    analysis, usage = call_claude(client, system, job["user"])
    record = {
        "dialog_id": d["dialog_id"],
        "player_id": d["player_id"],
        "manager": d["manager"],
        "input_key": job["key"],
        "usage": usage,
        "analysis": postprocess(analysis),
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**record, "from_cache": False}


def run(only: list[str] | None = None, force: bool = False) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    system, jobs = prepare_inputs()
    if only:
        jobs = [j for j in jobs if j["dialog"]["dialog_id"] in only]
    client = anthropic.Anthropic()

    results, errors = [], []
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(analyze_one, client, system, j, force): j["dialog"]["dialog_id"] for j in jobs}
        for fut in as_completed(futures):
            did = futures[fut]
            try:
                r = fut.result()
                a = r["analysis"]
                codes = ",".join(f["code"] for f in a["flags"]) or "—"
                src = "cache" if r["from_cache"] else f"{r['usage']['output_tokens']} out"
                print(f"{did}  {a['overall']:<9} {codes}  ({src})")
                results.append(r)
            except (AnalysisError, anthropic.APIError) as e:
                print(f"{did}  ERROR {e}", file=sys.stderr)
                errors.append({"dialog_id": did, "error": str(e)})

    # Сводный файл собираем из всего кэша, а не только из текущего прогона.
    all_records = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CACHE_DIR.glob("D*.json"))]
    (OUT_DIR / "analysis.json").write_text(
        json.dumps({"model": MODEL, "effort": EFFORT, "results": all_records}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fresh = [r for r in results if not r["from_cache"]]
    if fresh:
        tin = sum(r["usage"]["input_tokens"] for r in fresh)
        tout = sum(r["usage"]["output_tokens"] for r in fresh)
        tcache = sum(r["usage"]["cache_read_input_tokens"] for r in fresh)
        print(f"\nновых вызовов: {len(fresh)}, токены in/out/cache-read: {tin}/{tout}/{tcache}")
    print(f"готово: {len(results)}, ошибок: {len(errors)} → {OUT_DIR / 'analysis.json'}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="список dialog_id через запятую")
    ap.add_argument("--force", action="store_true", help="игнорировать кэш")
    ap.add_argument("--dry-run", metavar="DIALOG_ID", help="напечатать промпт для диалога и выйти")
    args = ap.parse_args()

    if args.dry_run:
        system, jobs = prepare_inputs()
        job = next(j for j in jobs if j["dialog"]["dialog_id"] == args.dry_run)
        print(f"── system: {len(system)} символов ({PROMPT_PATH.name})\n── user:\n{job['user']}")
        print(f"\n── schema:\n{json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False)[:600]}…")
        return
    run(only=args.only.split(",") if args.only else None, force=args.force)


if __name__ == "__main__":
    main()
