"""Детерминированные сигналы: всё, что можно посчитать без LLM.

Два уровня:
  * dialog_metrics(dialog)  — скорость ответов, кто ждёт ответа, односторонние рассылки;
  * player_signals(row)     — тренды депозитов, отток, RG-паттерны, платёжные проблемы, ДР.

Пороги собраны в THRESHOLDS, чтобы их можно было менять без правки логики.
Запуск: python -m src.signals  → out/signals.json + сводка в консоль.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from .load import OUT_DIR, load_dialogs, load_players

THRESHOLDS = {
    "sla_response_min": 60,          # ответ менеджера на сообщение игрока дольше — медленно
    "player_waiting_h": 12,          # последнее слово за игроком и ответа нет дольше — ждёт
    "one_way_streak": 3,             # столько сообщений менеджера подряд без ответа — спам
    "failed_deposits_7d": 3,         # неудачных депозитов за неделю — платёжная проблема
    "deposit_drop_pct": -50,         # падение депозитов 30д к предыдущим 30д, %
    "inactive_days": 14,             # без логина
    "rg_count_ratio": 1.8,           # во столько раз выросло число депозитов…
    "rg_avg_size_ratio": 0.8,        # …а средний депозит уменьшился (≤ этой доли)
    "rg_bonus_share": 0.4,           # бонусы / депозиты за 30д
    "rg_bonus_count": 10,            # бонусов за 30д
    "birthday_window": (-3, 7),      # дней до/после ДР относительно as_of
    "upgrade_deposits_30d": 3000,    # pre-VIP с депозитами выше — кандидат в VIP
    "no_contact_value": 3000,        # нет диалога, а депозиты (30д или прошлые 30д) выше — нужен контакт
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


@dataclass
class Signal:
    code: str
    severity: str  # critical | high | medium | low | info
    detail: str


# ─────────────────────────── диалоги ───────────────────────────

def dialog_metrics(dialog: dict, as_of: datetime) -> dict:
    """Метрики по одному диалогу. Время ответа считается на «ход» игрока:
    от первого сообщения в серии подряд идущих сообщений игрока до ближайшего ответа менеджера."""
    msgs = dialog["messages"]
    response_min: list[float] = []
    waiting_since: datetime | None = None
    max_mgr_streak = streak = 0

    turn_start: datetime | None = None
    for m in msgs:
        if m["from"] == "player":
            streak = 0
            if turn_start is None:
                turn_start = m["sent_at"]
        else:
            streak += 1
            max_mgr_streak = max(max_mgr_streak, streak)
            if turn_start is not None:
                response_min.append((m["sent_at"] - turn_start).total_seconds() / 60)
                turn_start = None
    if turn_start is not None:
        waiting_since = turn_start

    last = msgs[-1]
    unanswered_tail = 0
    for m in reversed(msgs):
        if m["from"] != "player":
            break
        unanswered_tail += 1
    return {
        "dialog_id": dialog["dialog_id"],
        "player_id": dialog["player_id"],
        "manager": dialog["manager"],
        "channel": dialog["channel"],
        "n_messages": len(msgs),
        "n_player": sum(m["from"] == "player" for m in msgs),
        "n_manager": sum(m["from"] == "manager" for m in msgs),
        "started_by": msgs[0]["from"],
        "first_at": msgs[0]["sent_at"].isoformat(),
        "last_at": last["sent_at"].isoformat(),
        "last_from": last["from"],
        "response_times_min": [round(x) for x in response_min],
        "max_response_min": round(max(response_min)) if response_min else None,
        "median_response_min": round(float(pd.Series(response_min).median())) if response_min else None,
        "player_waiting_h": round((as_of - waiting_since).total_seconds() / 3600, 1) if waiting_since else None,
        "unanswered_player_msgs": unanswered_tail,
        "max_manager_streak": max_mgr_streak,
        "player_replied": any(m["from"] == "player" for m in msgs),
    }


def dialog_signals(dm: dict) -> list[Signal]:
    t = THRESHOLDS
    out: list[Signal] = []
    slow = [x for x in dm["response_times_min"] if x > t["sla_response_min"]]
    if slow:
        out.append(Signal("SLOW_RESPONSE", "medium",
                          f"{len(slow)} ответ(а) дольше {t['sla_response_min']} мин, максимум {fmt_minutes(max(slow))}"))
    waiting = dm["player_waiting_h"]
    if waiting is not None and waiting >= t["player_waiting_h"] and dm["unanswered_player_msgs"] >= 2:
        # Игрок пишет повторно и не получает ответа — это уже игнор, а не вежливое «спасибо».
        out.append(Signal("PLAYER_IGNORED", "high",
                          f"{dm['unanswered_player_msgs']} сообщения игрока подряд без ответа, ждёт {fmt_hours(waiting)}"))
    elif waiting is not None and waiting >= t["player_waiting_h"]:
        # Не все «последние слова» требуют ответа («спасибо», «понятно») — это решит LLM.
        out.append(Signal("PLAYER_LAST_WORD", "low",
                          f"последнее сообщение от игрока, без ответа {fmt_hours(dm['player_waiting_h'])}"))
    if dm["max_manager_streak"] >= t["one_way_streak"]:
        sev = "medium" if not dm["player_replied"] else "low"
        out.append(Signal("ONE_WAY_OUTREACH", sev,
                          f"{dm['max_manager_streak']} сообщений менеджера подряд без ответа игрока"))
    return out


# ─────────────────────────── игроки ───────────────────────────

def player_metrics(p: pd.Series, as_of: datetime) -> dict:
    dep, prev = p.deposits_30d_usd, p.deposits_prev_30d_usd
    cnt, prev_cnt = p.deposits_30d_count, p.deposits_prev_30d_count
    avg = dep / cnt if cnt else 0.0
    prev_avg = prev / prev_cnt if prev_cnt else 0.0
    return {
        "deposit_change_pct": round((dep - prev) / prev * 100) if prev else None,
        "deposit_count_ratio": round(cnt / prev_cnt, 2) if prev_cnt else None,
        "avg_deposit": round(avg),
        "prev_avg_deposit": round(prev_avg),
        "bonus_share": round(p.bonuses_30d_usd / dep, 2) if dep else None,
        "days_since_login": days_between(p.last_login_at, as_of),
        "days_since_deposit": days_between(p.last_deposit_at, as_of),
        "birthday_offset_days": birthday_offset(p.birthday, as_of),
        "value_60d_usd": int(dep + prev),
    }


def player_signals(p: pd.Series, pm: dict, has_dialog: bool) -> list[Signal]:
    t = THRESHOLDS
    out: list[Signal] = []
    status = p.account_status
    protected = status in ("self_excluded", "limit_set")

    # Ограничения аккаунта — не проблема, а контекст: с такими игроками никаких промо и давления.
    if status == "self_excluded":
        out.append(Signal("SELF_EXCLUDED", "info", "самоисключён: никаких промо и контактов с офферами"))
    elif status == "limit_set":
        out.append(Signal("LIMIT_SET", "info", "игрок сам поставил лимит: не предлагать повышение"))

    # Деньги игрока застряли.
    if p.failed_deposits_7d >= t["failed_deposits_7d"]:
        out.append(Signal("PAYMENT_FAILURES", "high", f"{p.failed_deposits_7d} неудачных депозитов за 7 дней"))
    if p.pending_withdrawal_usd > 0:
        out.append(Signal("PENDING_WITHDRAWAL", "high", f"вывод {money(p.pending_withdrawal_usd)} в ожидании"))

    # Признаки проблемной игры: чаще и мельче + зависимость от бонусов.
    ratio = pm["deposit_count_ratio"]
    if ratio and ratio >= t["rg_count_ratio"] and pm["prev_avg_deposit"] and \
            pm["avg_deposit"] <= pm["prev_avg_deposit"] * t["rg_avg_size_ratio"]:
        out.append(Signal("RG_DEPOSIT_PATTERN", "high",
                          f"депозитов {p.deposits_30d_count} против {p.deposits_prev_30d_count} (×{ratio}), "
                          f"средний {money(pm['avg_deposit'])} против {money(pm['prev_avg_deposit'])}"))
    if (pm["bonus_share"] or 0) >= t["rg_bonus_share"] or p.bonuses_30d_count >= t["rg_bonus_count"]:
        out.append(Signal("RG_BONUS_DEPENDENCE", "high",
                          f"{p.bonuses_30d_count} бонусов на {money(p.bonuses_30d_usd)} "
                          f"= {round((pm['bonus_share'] or 0) * 100)}% от депозитов"))

    # Отток (не считаем оттоком игроков, которые сами ограничили игру).
    if not protected:
        if p.deposits_30d_usd == 0 and p.deposits_prev_30d_usd > 0:
            out.append(Signal("CHURNED", "high",
                              f"депозитов 0 за 30д (было {money(p.deposits_prev_30d_usd)}), "
                              f"не заходил {pm['days_since_login']} дн."))
        else:
            if pm["deposit_change_pct"] is not None and pm["deposit_change_pct"] <= t["deposit_drop_pct"]:
                out.append(Signal("DEPOSIT_DROP", "medium",
                                  f"депозиты {money(p.deposits_prev_30d_usd)} → {money(p.deposits_30d_usd)} "
                                  f"({pm['deposit_change_pct']}%)"))
            if pm["days_since_login"] is not None and pm["days_since_login"] >= t["inactive_days"]:
                out.append(Signal("INACTIVE", "medium", f"не заходил {pm['days_since_login']} дн."))

    # Поводы для контакта.
    lo, hi = t["birthday_window"]
    off = pm["birthday_offset_days"]
    if off is not None and lo <= off <= hi and status != "self_excluded":
        when = "сегодня" if off == 0 else (f"через {off} дн." if off > 0 else f"{-off} дн. назад")
        out.append(Signal("BIRTHDAY", "low", f"день рождения {when} ({p.birthday:%d.%m})"))
    if p.status == "pre-VIP" and p.deposits_30d_usd >= t["upgrade_deposits_30d"]:
        out.append(Signal("UPGRADE_CANDIDATE", "low",
                          f"pre-VIP, депозиты {money(p.deposits_prev_30d_usd)} → {money(p.deposits_30d_usd)}"))

    if not has_dialog and status != "self_excluded":
        value = max(p.deposits_30d_usd, p.deposits_prev_30d_usd)
        urgent = any(s.severity in ("critical", "high") for s in out)
        if urgent or value >= t["no_contact_value"]:
            out.append(Signal("NO_CONTACT", "high" if urgent else "medium",
                              "нет ни одного диалога с менеджером"
                              + (" при активных проблемах" if urgent else "")))
    return out


# ─────────────────────────── сборка ───────────────────────────

def build(as_of: datetime | None = None) -> dict:
    players = load_players()
    dialogs, data_as_of = load_dialogs()
    as_of = as_of or data_as_of

    by_player: dict[str, list[dict]] = {}
    dialog_rows = []
    for d in dialogs:
        dm = dialog_metrics(d, as_of)
        dm["signals"] = [asdict(s) for s in dialog_signals(dm)]
        dialog_rows.append(dm)
        by_player.setdefault(d["player_id"], []).append(dm)

    player_rows = []
    for pid, p in players.iterrows():
        pm = player_metrics(p, as_of)
        sigs = player_signals(p, pm, has_dialog=pid in by_player)
        # сигналы диалогов поднимаем на уровень игрока — очередь строится по игрокам
        for dm in by_player.get(pid, []):
            sigs += [Signal(**s) for s in dm["signals"]]
        sigs.sort(key=lambda s: SEVERITY_ORDER[s.severity])
        player_rows.append({
            "player_id": pid,
            "manager": p.manager,
            "brand": p.brand,
            "geo": p.geo,
            "status": p.status,
            "account_status": p.account_status,
            "dialog_ids": [dm["dialog_id"] for dm in by_player.get(pid, [])],
            **pm,
            "signals": [asdict(s) for s in sigs],
            "top_severity": sigs[0].severity if sigs else None,
        })

    return {"as_of": as_of.isoformat(), "thresholds": THRESHOLDS, "players": player_rows, "dialogs": dialog_rows}


# ─────────────────────────── утилиты ───────────────────────────

def days_between(d, as_of: datetime) -> int | None:
    return None if pd.isna(d) else (as_of.date() - d.date()).days


def birthday_offset(bday, as_of: datetime) -> int | None:
    """Сколько дней до ближайшего ДР (отрицательное — ДР уже прошёл). Ближайший по модулю."""
    if pd.isna(bday):
        return None
    today = as_of.date()
    best = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            delta = (bday.replace(year=year).date() - today).days
        except ValueError:  # 29 февраля в невисокосный год
            delta = (bday.replace(year=year, day=28).date() - today).days
        if best is None or abs(delta) < abs(best):
            best = delta
    return best


def money(x) -> str:
    return f"${int(x):,}".replace(",", " ")


def fmt_minutes(m: float) -> str:
    return f"{int(m)} мин" if m < 120 else f"{m / 60:.1f} ч"


def fmt_hours(h: float) -> str:
    return f"{h:.0f} ч" if h < 48 else f"{h / 24:.1f} дн."


def main() -> None:
    result = build()
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "signals.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = sorted(result["players"], key=lambda r: SEVERITY_ORDER.get(r["top_severity"], 9))
    print(f"as_of {result['as_of']}  ·  игроков {len(rows)}  ·  диалогов {len(result['dialogs'])}\n")
    for r in rows:
        if not r["signals"]:
            continue
        ds = ",".join(r["dialog_ids"]) or "—"
        print(f"{r['player_id']}  {r['manager']:<7} {ds:<5}")
        for s in r["signals"]:
            print(f"    [{s['severity']:<8}] {s['code']:<20} {s['detail']}")
    quiet = [r["player_id"] for r in rows if not r["signals"]]
    print(f"\nбез сигналов: {len(quiet)} — {', '.join(quiet)}")


if __name__ == "__main__":
    main()
