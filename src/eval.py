"""Сравнение LLM-разбора (out/analysis.json) с ручной разметкой (golden.json).

Главная метрика — полнота по критичным флагам: пропустить нарушение ответственной игры
хуже, чем поднять ложную тревогу. Поэтому recall считается отдельно от precision.

Запуск:
    python -m src.eval              # оценить текущий out/analysis.json
    python -m src.eval --self-test  # проверить сам eval: разметка против самой себя (должно быть 100%)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from .llm import FLAG_SEVERITY, INTENTS
from .load import OUT_DIR, ROOT, load_dialogs

GOLDEN_PATH = ROOT / "golden.json"
OVERALLS = {"critical", "poor", "ok", "good", "excellent"}
RESOLVED = {"yes", "partially", "no", "not_applicable"}


def load_golden() -> dict[str, dict]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["dialogs"]
    dialog_ids = {d["dialog_id"] for d in load_dialogs()[0]}
    problems = []
    if set(golden) != dialog_ids:
        problems.append(f"разметка не совпадает с диалогами: {sorted(set(golden) ^ dialog_ids)}")
    for did, g in golden.items():
        for code in g["must_flags"] + g["ok_flags"]:
            if code not in FLAG_SEVERITY:
                problems.append(f"{did}: неизвестный флаг {code}")
        if set(g["must_flags"]) & set(g["ok_flags"]):
            problems.append(f"{did}: флаг одновременно в must и ok")
        if not set(g["overall"]) <= OVERALLS:
            problems.append(f"{did}: неизвестный overall {g['overall']}")
        if not set(g["intent"]) <= set(INTENTS):
            problems.append(f"{did}: неизвестный intent {g['intent']}")
        if g["resolved"] is not None and not set(g["resolved"]) <= RESOLVED:
            problems.append(f"{did}: неизвестный resolved {g['resolved']}")
    if problems:
        raise ValueError("golden.json некорректен:\n  " + "\n  ".join(problems))
    return golden


def load_predictions() -> dict[str, dict]:
    path = OUT_DIR / "analysis.json"
    if not path.exists():
        return {}
    return {r["dialog_id"]: r["analysis"] for r in json.loads(path.read_text(encoding="utf-8"))["results"]}


def fake_from_golden(golden: dict[str, dict]) -> dict[str, dict]:
    """Идеальный «ответ модели», собранный из разметки, — для самопроверки eval."""
    return {did: {
        "player_intent": g["intent"][0],
        "resolved": (g["resolved"] or ["not_applicable"])[0],
        "needs_reply": bool(g["needs_reply"]),
        "overall": g["overall"][0],
        "flags": [{"code": c} for c in g["must_flags"]],
    } for did, g in golden.items()}


def evaluate(golden: dict[str, dict], preds: dict[str, dict]) -> dict:
    c = Counter()
    per_dialog = []
    for did, g in golden.items():
        if did not in preds:
            continue
        a = preds[did]
        c["dialogs"] += 1
        got = {f["code"] for f in a["flags"]}
        must, allowed = set(g["must_flags"]), set(g["must_flags"]) | set(g["ok_flags"])
        good_dialog = bool({"good", "excellent"} & set(g["overall"]))

        missed = sorted(must - got)
        # GOOD_PRACTICE не считаем ложным на хороших диалогах; на плохих — считаем.
        unexpected = sorted(x for x in got - allowed if not (x == "GOOD_PRACTICE" and good_dialog))

        for code in must:
            sev = FLAG_SEVERITY[code]
            c["must_total"] += 1
            c["must_found"] += code in got
            if sev == "critical":
                c["crit_total"] += 1
                c["crit_found"] += code in got
        scored = [x for x in got if x != "GOOD_PRACTICE" or not good_dialog]
        c["pred_flags"] += len(scored)
        c["pred_flags_ok"] += len(scored) - len(unexpected)

        overall_ok = a["overall"] in g["overall"]
        c["overall_ok"] += overall_ok
        if g["overall"] == ["critical"]:
            c["crit_dialogs"] += 1
            c["crit_dialogs_found"] += a["overall"] == "critical"
        if "critical" not in g["overall"]:
            c["noncrit_dialogs"] += 1
            c["false_alarms"] += a["overall"] == "critical"

        c["intent_ok"] += a["player_intent"] in g["intent"]
        if g["resolved"] is not None:
            c["resolved_total"] += 1
            c["resolved_ok"] += a["resolved"] in g["resolved"]
        if g["needs_reply"] is not None:
            c["reply_total"] += 1
            c["reply_ok"] += a["needs_reply"] == g["needs_reply"]

        if missed or unexpected or not overall_ok:
            per_dialog.append({"dialog_id": did, "missed": missed, "unexpected": unexpected,
                               "overall": a["overall"], "expected_overall": g["overall"], "note": g["note"]})

    def ratio(a, b):
        return {"value": round(c[a] / c[b], 3) if c[b] else None, "num": c[a], "den": c[b]}

    return {
        "coverage": {"evaluated": c["dialogs"], "total": len(golden)},
        "metrics": {
            "critical_flag_recall": ratio("crit_found", "crit_total"),
            "must_flag_recall": ratio("must_found", "must_total"),
            "flag_precision": ratio("pred_flags_ok", "pred_flags"),
            "critical_dialog_recall": ratio("crit_dialogs_found", "crit_dialogs"),
            "critical_false_alarms": {"value": c["false_alarms"], "den": c["noncrit_dialogs"]},
            "overall_accuracy": ratio("overall_ok", "dialogs"),
            "intent_accuracy": ratio("intent_ok", "dialogs"),
            "resolved_accuracy": ratio("resolved_ok", "resolved_total"),
            "needs_reply_accuracy": ratio("reply_ok", "reply_total"),
        },
        "errors": per_dialog,
    }


LABELS = {
    "critical_flag_recall": "Полнота по критичным флагам (RG/комплаенс)",
    "must_flag_recall": "Полнота по всем обязательным флагам",
    "flag_precision": "Точность флагов (доля не ложных)",
    "critical_dialog_recall": "Критичные диалоги помечены critical",
    "critical_false_alarms": "Ложные critical на некритичных диалогах",
    "overall_accuracy": "Итоговая оценка в допустимом диапазоне",
    "intent_accuracy": "Тема диалога",
    "resolved_accuracy": "Решён ли вопрос",
    "needs_reply_accuracy": "Нужен ли ответ",
}


def to_markdown(report: dict, title: str) -> str:
    cov = report["coverage"]
    lines = [f"# {title}", "", f"Оценено диалогов: {cov['evaluated']} из {cov['total']}", "",
             "| Метрика | Значение |", "|---|---|"]
    for key, m in report["metrics"].items():
        if key == "critical_false_alarms":
            val = f"{m['value']} из {m['den']}"
        elif m["value"] is None:
            val = "—"
        else:
            val = f"{m['value'] * 100:.0f}% ({m['num']}/{m['den']})"
        lines.append(f"| {LABELS[key]} | {val} |")
    if report["errors"]:
        lines += ["", "## Расхождения", "", "| Диалог | Пропущено | Лишнее | Оценка (ожидалось) |", "|---|---|---|---|"]
        for e in report["errors"]:
            lines.append(f"| {e['dialog_id']} | {', '.join(e['missed']) or '—'} | {', '.join(e['unexpected']) or '—'} "
                         f"| {e['overall']} ({'/'.join(e['expected_overall'])}) |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="оценить разметку против самой себя")
    args = ap.parse_args()

    golden = load_golden()
    if args.self_test:
        preds, title = fake_from_golden(golden), "Самопроверка eval (разметка против самой себя)"
    else:
        preds, title = load_predictions(), "Качество LLM-разбора против ручной разметки"
        if not preds:
            print(f"golden.json валиден ({len(golden)} диалогов). LLM-разбора ещё нет: "
                  "запустите python -m src.llm, затем python -m src.eval")
            return

    report = evaluate(golden, preds)
    md = to_markdown(report, title)
    print(md)
    if not args.self_test:
        OUT_DIR.mkdir(exist_ok=True)
        (OUT_DIR / "eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (OUT_DIR / "eval.md").write_text(md, encoding="utf-8")


if __name__ == "__main__":
    main()
