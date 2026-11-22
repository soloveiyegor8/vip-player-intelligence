"""Выгрузка всего, что нужно веб-интерфейсу, в один файл docs/data.json.

Сайт (docs/index.html) — статическая страница без сервера: всю логику (сигналы, разбор, проверки,
приоритеты, метрики) считает Python, а страница только показывает результат.

Запуск:
    python -m src.export
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime

from . import scoring
from .load import OUT_DIR, ROOT, load_dialogs, load_players
from .signals import THRESHOLDS, build

DOCS = ROOT / "docs"
EVAL_FILES = {"claude": "eval.json", "manual": "eval_manual.json", "ollama": "eval_ollama.json"}
SOURCE_NOTE = {
    "claude": "Прогон через Claude API",
    "manual": "Разбор Claude вручную в Claude Code. Разметку делала та же модель — метрики завышены",
    "ollama": "Бесплатная локальная модель + второй проход-проверка кодом",
}


def _val(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    if hasattr(v, "strftime"):
        return None if str(v) == "NaT" else v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        return v.item()
    return v


def managers_stats(sig: dict, queue: list[dict], analyses: dict) -> list[dict]:
    sla = THRESHOLDS["sla_response_min"]
    out = []
    for mgr in sorted({r["manager"] for r in queue}):
        mdlg = [d for d in sig["dialogs"] if d["manager"] == mgr]
        times = [t for d in mdlg for t in d["response_times_min"]]
        mq = [r for r in queue if r["manager"] == mgr]
        codes = [i["code"] for r in mq for i in r["items"]]
        mllm = [analyses[d["dialog_id"]] for d in mdlg if d["dialog_id"] in analyses]
        out.append({
            "manager": mgr,
            "players": len(mq),
            "dialogs": len(mdlg),
            "median_response_min": round(statistics.median(times)) if times else None,
            "late": sum(t > sla for t in times),
            "responses": len(times),
            "ignored": codes.count("PLAYER_IGNORED"),
            "no_contact": codes.count("NO_CONTACT"),
            "critical": sum(r["top_severity"] == "critical" for r in mq),
            "high": sum(r["top_severity"] == "high" for r in mq),
            "rg_violations": sum(f["code"].startswith("RG_") for a in mllm for f in a["flags"]) if mllm else None,
            "good_practice": sum(any(f["code"] == "GOOD_PRACTICE" for f in a["flags"]) for a in mllm) if mllm else None,
            "avg_score": round(statistics.mean(a["score_total"] / 6 for a in mllm), 2) if mllm else None,
            "value_60d_usd": sum(r["value_60d_usd"] for r in mq),
        })
    return out


def build_source(sig: dict, analyses: dict, dialogs: dict) -> dict:
    queue = scoring.build_queue(sig, analyses)
    rows = [{
        "player_id": r["player_id"], "manager": r["manager"], "dialog_ids": r["dialog_ids"],
        "top_severity": r["top_severity"], "reason": r["reason"], "action": list(r["action"]) if r["action"] else None,
        "priority": r["priority"], "value_60d_usd": r["value_60d_usd"],
        "items": [{k: i.get(k) for k in ("code", "severity", "source", "detail", "evidence")} for i in r["items"]],
    } for r in queue]
    return {
        "queue": rows,
        "retention": scoring.retention_view(queue),
        "practices": scoring.best_practices(analyses, dialogs),
        "managers": managers_stats(sig, queue, analyses),
        "analyses": analyses,
    }


def main() -> None:
    sig = build()
    dialogs_list, as_of = load_dialogs()
    dialogs = {d["dialog_id"]: d for d in dialogs_list}
    players = load_players()
    dm = {d["dialog_id"]: d for d in sig["dialogs"]}
    ps = {p["player_id"]: p for p in sig["players"]}

    sources = {}
    for src in scoring.available_sources():
        analyses, model = scoring.load_analysis(src)
        ev = OUT_DIR / EVAL_FILES[src]
        sources[src] = {
            "label": scoring.SOURCES[src][0], "model": model, "note": SOURCE_NOTE[src],
            "metrics": json.loads(ev.read_text(encoding="utf-8"))["metrics"] if ev.exists() else None,
            **build_source(sig, analyses, dialogs),
        }
    sources["data"] = {"label": "Только данные CRM", "model": "", "note": "Без разбора переписок",
                       "metrics": None, **build_source(sig, {}, dialogs)}

    data = {
        "meta": {"as_of": as_of.date().isoformat(), "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "sla_min": THRESHOLDS["sla_response_min"], "default_source": next(s for s in ("claude", "ollama", "manual", "data") if s in sources)},
        "thresholds": THRESHOLDS,
        "players": {pid: {**{k: _val(v) for k, v in row.items()},
                          "deposit_change_pct": ps[pid]["deposit_change_pct"],
                          "days_since_login": ps[pid]["days_since_login"],
                          "value_60d_usd": ps[pid]["value_60d_usd"],
                          "dialog_ids": ps[pid]["dialog_ids"]}
                    for pid, row in players.to_dict("index").items()},
        "dialogs": {did: {"dialog_id": did, "player_id": d["player_id"], "manager": d["manager"],
                          "channel": d["channel"], "response_times_min": dm[did]["response_times_min"],
                          "messages": [{"from": m["from"], "text": m["text"],
                                        "at": m["sent_at"].strftime("%Y-%m-%d %H:%M")} for m in d["messages"]]}
                    for did, d in dialogs.items()},
        "sources": sources,
    }
    DOCS.mkdir(exist_ok=True)
    path = DOCS / "data.json"
    path.write_text(json.dumps(data, ensure_ascii=False, default=_val), encoding="utf-8")
    print(f"готово: {path} ({path.stat().st_size // 1024} КБ), источники: {', '.join(sources)}")


if __name__ == "__main__":
    main()
