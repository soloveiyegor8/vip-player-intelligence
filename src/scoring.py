"""Очередь приоритетов: объединяет сигналы из данных (signals.py) и LLM-разбор (llm.py).

Работает и без LLM: тогда очередь строится только на сигналах из данных,
а действие берётся из DEFAULT_ACTIONS. Когда LLM-разбор есть, он:
  * добавляет смысловые флаги (RG-нарушения, мультиаккаунт, грубость…);
  * снимает шум: «последнее слово за игроком» убирается, если ответ не нужен,
    платёжная проблема понижается, если в диалоге она решена;
  * даёт конкретное следующее действие и черновик сообщения.
"""
from __future__ import annotations

import json

from .load import OUT_DIR
from .signals import SEVERITY_ORDER

SEVERITY_WEIGHT = {"critical": 100, "high": 40, "medium": 15, "low": 5, "info": 0}

SEVERITY_LABEL = {"critical": "🔴 критично", "high": "🟠 высокий", "medium": "🟡 средний",
                  "low": "⚪ низкий", "info": "ℹ️ инфо"}

# Действие по умолчанию для сигналов из данных: (кто, что, срок).
DEFAULT_ACTIONS = {
    "PAYMENT_FAILURES": ("manager", "Связаться, предложить другой метод оплаты, при повторе передать в payments", "today"),
    "PENDING_WITHDRAWAL": ("payments", "Проверить статус вывода и сообщить игроку точный срок", "today"),
    "RG_DEPOSIT_PATTERN": ("teamlead", "Без промо. Мягкий check-in, предложить лимит или паузу", "today"),
    "RG_BONUS_DEPENDENCE": ("teamlead", "Остановить выдачу бонусов, обсудить игрока с менеджером", "today"),
    "PLAYER_IGNORED": ("manager", "Ответить игроку по существу", "now"),
    "CHURNED": ("manager", "Персональный реактивационный контакт с учётом любимой игры", "this_week"),
    "NO_CONTACT": ("teamlead", "Назначить первый контакт ответственному менеджеру", "this_week"),
    "DEPOSIT_DROP": ("manager", "Выяснить причину падения активности", "this_week"),
    "INACTIVE": ("manager", "Связаться, узнать, всё ли в порядке", "this_week"),
    "SLOW_RESPONSE": ("teamlead", "Разобрать с менеджером время ответа", "this_week"),
    "ONE_WAY_OUTREACH": ("teamlead", "Остановить шаблонные рассылки, сменить подход", "this_week"),
    "PLAYER_LAST_WORD": ("manager", "Проверить, нужен ли ответ", "this_week"),
    "BIRTHDAY": ("manager", "Поздравить с днём рождения", "today"),
    "UPGRADE_CANDIDATE": ("teamlead", "Рассмотреть перевод в VIP после RG-проверки", "this_week"),
}

OWNER_LABEL = {"manager": "менеджер", "teamlead": "тимлид", "payments": "платежи", "compliance": "комплаенс",
               "support": "саппорт", "product": "продукт"}
DEADLINE_LABEL = {"now": "в течение часа", "today": "сегодня", "this_week": "на этой неделе", "none": "—"}


# Источники LLM-разбора в порядке предпочтения: настоящий прогон через API, ручной разбор, локальная модель.
SOURCES = {
    "claude": ("Claude API", OUT_DIR / "analysis.json"),
    "manual": ("Claude, вручную в Claude Code", OUT_DIR / "analysis_manual.json"),
    "ollama": ("Ollama, локальная модель", OUT_DIR / "analysis_ollama.json"),
}


def available_sources() -> list[str]:
    return [k for k, (_, path) in SOURCES.items() if path.exists()]


def load_analysis(source: str | None = None) -> tuple[dict[str, dict], str]:
    """LLM-разбор по dialog_id и название модели. Без source — первый имеющийся по порядку SOURCES."""
    if source is None:
        avail = available_sources()
        if not avail:
            return {}, ""
        source = avail[0]
    path = SOURCES[source][1]
    if not path.exists():
        return {}, ""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {r["dialog_id"]: r["analysis"] for r in data["results"]}, data.get("model", "")


def merge_player(p: dict, analyses: dict[str, dict]) -> dict:
    """Итоговые флаги, приоритет и действие для одного игрока."""
    llm = [analyses[d] for d in p["dialog_ids"] if d in analyses]
    items = []
    for s in p["signals"]:
        item = {**s, "source": "data"}
        if llm:
            a = llm[0]
            if s["code"] == "PLAYER_LAST_WORD" and not a["needs_reply"]:
                continue
            if s["code"] == "PAYMENT_FAILURES" and a["resolved"] == "yes":
                item = {**item, "severity": "low", "detail": s["detail"] + " — решено в диалоге"}
        items.append(item)
    for a in llm:
        for f in a["flags"]:
            items.append({"code": f["code"], "severity": f["severity"], "source": "llm",
                          "detail": f["explanation"], "evidence": f["evidence"]})
    items.sort(key=lambda x: SEVERITY_ORDER[x["severity"]])

    weights = sorted((SEVERITY_WEIGHT[i["severity"]] for i in items), reverse=True)
    priority = (weights[0] + 0.25 * sum(weights[1:])) if weights else 0
    priority += min(p["value_60d_usd"] / 1000, 20)  # ценность игрока как тай-брейкер

    top = next((i for i in items if i["severity"] != "info" and i["code"] != "GOOD_PRACTICE"), None)
    if llm and llm[0]["next_action"]["deadline"] != "none":
        na = llm[0]["next_action"]
        action = (na["owner"], na["action"], na["deadline"])
    elif top and top["code"] in DEFAULT_ACTIONS:
        action = DEFAULT_ACTIONS[top["code"]]
    else:
        action = None

    return {
        **p,
        "items": items,
        "top_severity": top["severity"] if top else None,
        "reason": top["detail"] if top else "",
        "action": action,
        "priority": round(priority, 1),
        "llm": llm[0] if llm else None,
    }


def build_queue(signals_data: dict, analyses: dict[str, dict]) -> list[dict]:
    rows = [merge_player(p, analyses) for p in signals_data["players"]]
    return sorted(rows, key=lambda r: -r["priority"])
