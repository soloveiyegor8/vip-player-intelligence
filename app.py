"""VIP Player Intelligence — интерфейс для тимлида VIP-отдела.

Запуск: .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import statistics

import pandas as pd
import streamlit as st

from src import scoring
from src.load import load_dialogs, load_players
from src.scoring import DEADLINE_LABEL, OWNER_LABEL, SEVERITY_LABEL
from src.signals import SEVERITY_ORDER, THRESHOLDS, build

st.set_page_config(page_title="VIP Player Intelligence", page_icon="💎", layout="wide")


@st.cache_data
def load_all():
    sig = build()
    analyses = scoring.load_analysis()
    queue = scoring.build_queue(sig, analyses)
    dialogs, _ = load_dialogs()
    players = load_players()
    return sig, analyses, queue, {d["dialog_id"]: d for d in dialogs}, players


sig, analyses, queue, dialogs, players = load_all()
by_id = {r["player_id"]: r for r in queue}
dm_by_id = {d["dialog_id"]: d for d in sig["dialogs"]}
managers = sorted({r["manager"] for r in queue})


def fmt_action(a) -> str:
    if not a:
        return "—"
    owner, what, deadline = a
    return f"{OWNER_LABEL.get(owner, owner)} · {DEADLINE_LABEL.get(deadline, deadline)} · {what}"


def md(text: str) -> str:
    """Экранирует $, иначе Streamlit рендерит текст между двумя $ как формулу."""
    return str(text).replace("$", "\\$")


def money(x) -> str:
    return f"${int(x):,}".replace(",", " ")


# ─────────────────────────── шапка ───────────────────────────

st.title("💎 VIP Player Intelligence")
st.caption(f"Срез данных: {sig['as_of'][:10]} · игроков: {len(queue)} · диалогов: {len(dialogs)} · "
           f"LLM-разбор: {len(analyses)} из {len(dialogs)} диалогов")
if not analyses:
    st.info("LLM-разбор ещё не запускался, поэтому очередь построена только на сигналах из данных: деньги, "
            "активность, скорость ответов. Нарушения, которые видны только по смыслу переписки (отговаривание "
            "от самоисключения, «отыграйся», мультиаккаунт), появятся после `python -m src.llm`.", icon="ℹ️")

with st.sidebar:
    st.header("Фильтры")
    sel_managers = st.multiselect("Менеджер", managers, default=managers)
    min_sev = st.select_slider("Минимальный уровень", options=["critical", "high", "medium", "low"], value="medium",
                               format_func=lambda s: SEVERITY_LABEL[s])

tab_queue, tab_player, tab_managers = st.tabs(["🔥 Что горит", "👤 Карточка игрока", "📊 Менеджеры"])

# ─────────────────────────── очередь ───────────────────────────

with tab_queue:
    visible = [r for r in queue
               if r["manager"] in sel_managers and r["top_severity"]
               and SEVERITY_ORDER[r["top_severity"]] <= SEVERITY_ORDER[min_sev]]

    c1, c2, c3, c4 = st.columns(4)
    count = lambda sev: sum(r["top_severity"] == sev for r in visible)
    c1.metric("🔴 Критично", count("critical"))
    c2.metric("🟠 Высокий", count("high"))
    c3.metric("🟡 Средний", count("medium"))
    c4.metric("Без контакта с менеджером", sum(any(i["code"] == "NO_CONTACT" for i in r["items"]) for r in visible))

    table = pd.DataFrame([{
        "Уровень": SEVERITY_LABEL[r["top_severity"]],
        "Игрок": r["player_id"],
        "Менеджер": r["manager"],
        "Диалог": ", ".join(r["dialog_ids"]) or "—",
        "Почему": r["reason"],
        "Что сделать": fmt_action(r["action"]),
        "Сигналов": sum(i["severity"] not in ("info",) for i in r["items"]),
        "Приоритет": r["priority"],
    } for r in visible])

    st.caption("Отсортировано по приоритету: серьёзность сигналов, их количество и ценность игрока. "
               "Выберите строку, чтобы открыть карточку.")
    event = st.dataframe(table, hide_index=True, use_container_width=True, on_select="rerun",
                         selection_mode="single-row", height=min(38 * (len(table) + 1), 720),
                         column_config={"Почему": st.column_config.TextColumn(width="large"),
                                        "Что сделать": st.column_config.TextColumn(width="large"),
                                        "Приоритет": st.column_config.NumberColumn(format="%.0f")})
    if event.selection.rows:
        st.session_state["player"] = table.iloc[event.selection.rows[0]]["Игрок"]
        st.success(f"Открыта карточка {st.session_state['player']} — перейдите на вкладку «Карточка игрока».")

# ─────────────────────────── карточка ───────────────────────────

with tab_player:
    ids = [r["player_id"] for r in queue]
    st.session_state.setdefault("player", ids[0])
    pid = st.selectbox(
        "Игрок", ids, key="player",  # общий ключ: выбор строки в очереди сразу меняет карточку
        format_func=lambda i: f"{i} · {by_id[i]['manager']} · "
                              f"{SEVERITY_LABEL.get(by_id[i]['top_severity'], 'без сигналов')}")
    r = by_id[pid]
    p = players.loc[pid]

    st.subheader(f"{pid} · {p.brand} · {p.geo} · {p.status} · менеджер {p.manager}")
    if p.account_status != "active":
        st.warning({"self_excluded": "Игрок самоисключён — никаких офферов и промо.",
                    "limit_set": "Игрок сам поставил лимит — не предлагать повышение."}[p.account_status])

    m = st.columns(3)
    m[0].metric("Депозиты 30д", money(p.deposits_30d_usd),
                f"{r['deposit_change_pct']}% к прошлым 30д" if r["deposit_change_pct"] is not None else None)
    m[1].metric("Число депозитов 30д", f"{int(p.deposits_30d_count)} (было {int(p.deposits_prev_30d_count)})")
    m[2].metric("Бонусы 30д", f"{money(p.bonuses_30d_usd)} · {int(p.bonuses_30d_count)} шт.")
    m = st.columns(3)
    m[0].metric("Вывод в ожидании", money(p.pending_withdrawal_usd))
    m[1].metric("Неудачных депозитов 7д", int(p.failed_deposits_7d))
    m[2].metric("Последний вход", f"{r['days_since_login']} дн. назад")

    left, right = st.columns([3, 2])
    with left:
        st.markdown("#### Сигналы")
        if not r["items"]:
            st.write("Сигналов нет.")
        for i in r["items"]:
            src = "🤖 LLM" if i["source"] == "llm" else "📈 данные"
            st.markdown(f"**{SEVERITY_LABEL[i['severity']]}** · `{i['code']}` · {src}  \n{md(i['detail'])}")
            if i.get("evidence"):
                st.caption(md(f"«{i['evidence']}»"))
        st.markdown("#### Что сделать")
        st.write(md(fmt_action(r["action"])))

        a = r["llm"]
        if a:
            st.markdown("#### Разбор LLM")
            st.write(md(a["summary"]))
            scores = pd.DataFrame([a["scores"]]).rename(columns={
                "responsiveness": "Скорость", "problem_solving": "Решение", "accuracy": "Точность",
                "personalization": "Персонализация", "tone": "Тон", "responsible_gambling": "Отв. игра"})
            st.dataframe(scores, hide_index=True, use_container_width=True)
            st.markdown(f"**Обратная связь менеджеру.** {md(a['manager_feedback'])}")
            if a["draft_message"]:
                st.text_area("Черновик сообщения игроку", a["draft_message"], height=140)
        elif r["dialog_ids"]:
            st.caption("LLM-разбор этого диалога ещё не запускался.")

    with right:
        st.markdown("#### Переписка")
        if not r["dialog_ids"]:
            st.write("Диалогов с менеджером нет.")
        for did in r["dialog_ids"]:
            d, dm = dialogs[did], dm_by_id[did]
            rt = dm["response_times_min"]
            st.caption(f"{did} · {d['channel']} · время ответов, мин: {', '.join(map(str, rt)) or '—'}")
            with st.container(height=520):
                for msg in d["messages"]:
                    is_player = msg["from"] == "player"
                    with st.chat_message("user" if is_player else "assistant", avatar="🧑" if is_player else "💼"):
                        st.caption(f"{'Игрок' if is_player else d['manager']} · {msg['sent_at']:%d.%m %H:%M}")
                        st.write(md(msg["text"]))

# ─────────────────────────── менеджеры ───────────────────────────

with tab_managers:
    st.caption(f"SLA ответа: {THRESHOLDS['sla_response_min']} мин. Оценки LLM — среднее по шкале 0–3, "
               "появятся после LLM-разбора.")
    rows = []
    for mgr in managers:
        mdlg = [d for d in sig["dialogs"] if d["manager"] == mgr]
        times = [t for d in mdlg for t in d["response_times_min"]]
        mq = [r for r in queue if r["manager"] == mgr]
        codes = [i["code"] for r in mq for i in r["items"]]
        mllm = [analyses[d["dialog_id"]] for d in mdlg if d["dialog_id"] in analyses]
        row = {
            "Менеджер": mgr,
            "Игроков": len(mq),
            "Диалогов": len(mdlg),
            "Медиана ответа, мин": round(statistics.median(times)) if times else None,
            "Ответов дольше SLA": f"{sum(t > THRESHOLDS['sla_response_min'] for t in times)} из {len(times)}",
            "Игнор игрока": codes.count("PLAYER_IGNORED"),
            "Игроков 🔴/🟠": sum(r["top_severity"] in ("critical", "high") for r in mq),
            "Без контакта": codes.count("NO_CONTACT"),
        }
        if mllm:
            row["RG-нарушений (LLM)"] = sum(f["code"].startswith("RG_") for a in mllm for f in a["flags"])
            row["Средняя оценка (LLM)"] = round(statistics.mean(a["score_total"] / 6 for a in mllm), 2)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    for mgr in managers:
        mq = [r for r in queue if r["manager"] == mgr and r["top_severity"] in ("critical", "high")]
        with st.expander(f"{mgr}: игроки с высоким приоритетом ({len(mq)})"):
            for r in mq:
                st.markdown(f"**{r['player_id']}** · {SEVERITY_LABEL[r['top_severity']]} · {md(r['reason'])}  \n"
                            f"→ {md(fmt_action(r['action']))}")
