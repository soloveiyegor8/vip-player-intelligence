"""Загрузка и нормализация исходных данных: players.csv и dialogs.json."""
from __future__ import annotations

import json
from datetime import datetime, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"

DATE_COLS = ["vip_since", "last_deposit_at", "last_withdrawal_at", "last_login_at", "birthday"]


def load_players(path: Path = DATA_DIR / "players.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df.set_index("player_id", drop=False)


def load_dialogs(path: Path = DATA_DIR / "dialogs.json") -> tuple[list[dict], datetime]:
    """Возвращает список диалогов и момент среза (конец дня as_of).

    Время в сообщениях приводится к datetime. Сообщения сортируются по времени.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    as_of = datetime.combine(datetime.fromisoformat(raw["as_of"]).date(), time(23, 59, 59))
    dialogs = []
    for d in raw["dialogs"]:
        msgs = sorted(
            ({**m, "sent_at": datetime.fromisoformat(m["sent_at"])} for m in d["messages"]),
            key=lambda m: m["sent_at"],
        )
        dialogs.append({**d, "messages": msgs})
    return dialogs, as_of


def messages_frame(dialogs: list[dict]) -> pd.DataFrame:
    """Плоская таблица всех сообщений — удобно для агрегатов и UI."""
    rows = [
        {
            "dialog_id": d["dialog_id"],
            "player_id": d["player_id"],
            "manager": d["manager"],
            "channel": d["channel"],
            **m,
        }
        for d in dialogs
        for m in d["messages"]
    ]
    return pd.DataFrame(rows)
