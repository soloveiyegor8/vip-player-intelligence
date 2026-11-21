"""VIP Player Intelligence — рабочая консоль тимлида VIP-отдела.

Запуск: .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import statistics

import streamlit as st

from src import scoring, ui
from src.load import load_dialogs, load_players
from src.signals import SEVERITY_ORDER, THRESHOLDS, build
from src.ui import esc, money, pill, sev_pill

st.set_page_config(page_title="VIP Player Intelligence", layout="wide", initial_sidebar_state="expanded")
st.html(ui.CSS)

VIEWS = {"queue": "Что горит", "retention": "Риск оттока", "player": "Игрок", "managers": "Менеджеры"}
SLA = THRESHOLDS["sla_response_min"]

# ─────────────────────────── данные ───────────────────────────

sources = scoring.available_sources()
qp = st.query_params

with st.sidebar:
    st.markdown("**Источник разбора**")
    source = st.selectbox("Источник разбора", sources, label_visibility="collapsed",
                          index=sources.index(qp["src"]) if qp.get("src") in sources else 0,
                          format_func=lambda s: scoring.SOURCES[s][0]) if sources else None


@st.cache_data
def load_all(source, mtime):  # mtime — чтобы кэш сбрасывался, когда файл разбора обновился
    sig = build()
    analyses, model = scoring.load_analysis(source)
    queue = scoring.build_queue(sig, analyses)
    dialogs, _ = load_dialogs()
    return sig, analyses, model, queue, {d["dialog_id"]: d for d in dialogs}, load_players()


sig, analyses, model, queue, dialogs, players = load_all(
    source, scoring.SOURCES[source][1].stat().st_mtime if source else 0)
by_id = {r["player_id"]: r for r in queue}
managers = sorted({r["manager"] for r in queue})

with st.sidebar:
    st.markdown("**Менеджеры**")
    sel_managers = st.multiselect("Менеджеры", managers, default=managers, label_visibility="collapsed")
    st.markdown("**Показывать от уровня**")
    min_sev = st.radio("Уровень", ["critical", "high", "medium", "low"], index=2, label_visibility="collapsed",
                       format_func=lambda s: ui.SEV_TEXT[s])
    st.divider()
    st.caption(f"Срез данных {sig['as_of'][:10]}. SLA ответа {SLA} мин. Разбор: "
               + (f"{len(analyses)} из {len(dialogs)} диалогов, {model}." if analyses else "не запускался."))

# ─────────────────────────── навигация ───────────────────────────

view = qp.get("view", "queue") if qp.get("view") in VIEWS else "queue"
st.html(f'<div class="topbar"><div class="brand">VIP Player Intelligence<span>консоль тимлида</span></div>'
        f'<div class="meta">{len(queue)} игроков · {len(dialogs)} диалогов · срез {esc(sig["as_of"][:10])}</div></div>')
chosen = st.segmented_control("Раздел", list(VIEWS), default=view, format_func=VIEWS.get,
                              label_visibility="collapsed", key=f"nav_{view}")
if chosen and chosen != view:
    qp["view"] = chosen
    st.rerun()


def player_link(pid: str) -> str:
    params = {"view": "player", "player": pid}
    if source:
        params["src"] = source
    return ui.link(params)


if not analyses:
    st.info("Разбор переписок ещё не запускался: очередь построена только на сигналах из данных. "
            "Нарушения, видные лишь по смыслу переписки, появятся после `python -m src.llm`.")

# ─────────────────────────── что горит ───────────────────────────

if view == "queue":
    visible = [r for r in queue if r["manager"] in sel_managers and r["top_severity"]
               and SEVERITY_ORDER[r["top_severity"]] <= SEVERITY_ORDER[min_sev]]
    count = lambda sev: sum(r["top_severity"] == sev for r in visible)
    ret = scoring.retention_view([r for r in queue if r["manager"] in sel_managers])
    st.html(ui.kpis([
        ("Критично", str(count("critical")), "нарушения RG и комплаенса", "crit"),
        ("Высокий приоритет", str(count("high")), "деньги, игнор, отток", "high"),
        ("Без контакта с менеджером", str(sum(any(i["code"] == "NO_CONTACT" for i in r["items"]) for r in visible)),
         "ценные игроки без диалога", ""),
        ("Депозиты под риском оттока", money(sum(x["value_60d_usd"] for x in ret)), f"{len(ret)} игроков, 60 дней", ""),
    ]))

    rows = []
    for r in visible:
        top = next((i for i in r["items"] if i["severity"] == r["top_severity"]), {})
        quote = f'<div class="quote">«{esc(top["evidence"])}»</div>' if top.get("evidence") else ""
        p = players.loc[r["player_id"]]
        rows.append(
            f'<tr><td>{sev_pill(r["top_severity"])}</td>'
            f'<td><div class="who mono">{esc(r["player_id"])}</div><div class="sub">{esc(p.brand)} · {esc(p.geo)} · '
            f'{money(r["value_60d_usd"])}</div></td>'
            f'<td>{esc(r["manager"])}<div class="sub">{esc(", ".join(r["dialog_ids"]) or "нет диалога")}</div></td>'
            f'<td>{esc(r["reason"])}{quote}</td>'
            f'<td>{ui.action_html(r["action"])}</td>'
            f'<td><a class="open" href="{player_link(r["player_id"])}" target="_self">Открыть</a></td></tr>')
    st.html('<table class="q"><thead><tr><th style="width:92px">Уровень</th><th style="width:150px">Игрок</th>'
            '<th style="width:110px">Менеджер</th><th>Почему</th><th style="width:300px">Что сделать</th><th></th>'
            '</tr></thead><tbody>' + "".join(rows) + "</tbody></table>"
            if rows else '<div class="empty">Нет игроков на этом уровне.</div>')
    st.caption("Порядок: серьёзность сигналов, их число и ценность игрока за 60 дней.")

# ─────────────────────────── риск оттока ───────────────────────────

elif view == "retention":
    ret = [x for x in scoring.retention_view(queue) if x["manager"] in sel_managers]
    st.html(ui.kpis([
        ("Игроков под риском", str(len(ret)), "есть хотя бы одна причина уйти", "high"),
        ("Депозиты под риском", money(sum(x["value_60d_usd"] for x in ret)), "за последние 60 дней", ""),
        ("Удерживать сервисом", str(sum(x["rg_hold"] for x in ret)), "признаки риска: без бонусов и промо", ""),
        ("Можно с предложением", str(sum(not x["rg_hold"] for x in ret)), "после решения проблемы", ""),
    ]))
    rows = []
    for x in ret:
        mode = pill("Только сервис", "outline") if x["rg_hold"] else pill("Можно оффер", "accent")
        reasons = "".join(f'<div>{esc(rs)}</div>' for rs in x["reasons"][:3])
        if len(x["reasons"]) > 3:
            reasons += f'<div class="sub">и ещё {len(x["reasons"]) - 3}</div>'
        rows.append(
            f'<tr><td><div class="who mono">{esc(x["player_id"])}</div><div class="sub">{esc(x["manager"])}</div></td>'
            f'<td class="who">{money(x["value_60d_usd"])}</td><td>{reasons}</td><td>{mode}</td>'
            f'<td>{esc(x["action"])}</td>'
            f'<td><a class="open" href="{player_link(x["player_id"])}" target="_self">Открыть</a></td></tr>')
    st.html('<table class="q"><thead><tr><th style="width:120px">Игрок</th><th style="width:100px">Депозиты 60д</th>'
            '<th style="width:260px">Почему может уйти</th><th style="width:130px">Режим</th><th>Что сделать</th>'
            '<th></th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>")
    st.caption("Сначала деньги и сервис, потом предложение. Игроку с признаками проблемной игры бонус — "
               "нарушение, а не удержание.")

    practices = [b for b in scoring.best_practices(analyses, dialogs) if b["manager"] in sel_managers]
    if practices:
        st.html('<div class="section">Как удерживают лучшие: моменты из переписок для команды</div>')
        for b in practices:
            with st.expander(f"{b['dialog_id']} · {b['manager']} — {b['situation']}".replace("$", "\\$")):
                st.html(f'<div class="sig"><div class="text">«{esc(b["evidence"])}»</div>'
                        f'<div class="quote">{esc(b["why"])}</div></div>')

# ─────────────────────────── карточка игрока ───────────────────────────

elif view == "player":
    ids = [r["player_id"] for r in queue]
    current = qp.get("player") if qp.get("player") in by_id else ids[0]
    pid = st.selectbox("Игрок", ids, index=ids.index(current), label_visibility="collapsed",
                       format_func=lambda i: f"{i} · {by_id[i]['manager']} · "
                                             f"{ui.SEV_TEXT.get(by_id[i]['top_severity'], 'без сигналов')}")
    if pid != current:
        qp["player"] = pid
        st.rerun()
    r, p = by_id[pid], players.loc[pid]

    status = {"self_excluded": pill("Самоисключён", "critical"), "limit_set": pill("Свой лимит", "high")}.get(
        p.account_status, pill("Активен", "outline"))
    st.html(f'<div class="p-head"><span class="p-id mono">{esc(pid)}</span>{sev_pill(r["top_severity"])}{status}'
            f'{pill(p.status, "outline")}{pill(f"{p.brand} · {p.geo}", "outline")}'
            f'<span class="meta">менеджер {esc(p.manager)} · любимая игра {esc(p.favorite_game)}</span></div>')
    if p.account_status == "self_excluded":
        st.html('<div class="notice">Игрок самоисключён: никаких офферов, промо и инициативных контактов.</div>')
    elif p.account_status == "limit_set":
        st.html('<div class="notice">Игрок сам поставил лимит: не предлагать повышение и депозитные бонусы.</div>')

    chg = r["deposit_change_pct"]
    cnt_ratio = p.deposits_30d_count / max(p.deposits_prev_30d_count, 1)
    stat = lambda l, v, d="", bad=False: (f'<div class="stat"><div class="label">{esc(l)}</div><div class="value">'
                                          f'{esc(v)}</div><div class="delta{" bad" if bad else ""}">{esc(d)}</div></div>')
    st.html('<div class="stats">'
            + stat("Депозиты 30д", money(p.deposits_30d_usd), f"{chg:+d}% к прошлым 30д" if chg is not None else "",
                   chg is not None and chg <= -50)
            + stat("Число депозитов", f"{int(p.deposits_30d_count)}", f"было {int(p.deposits_prev_30d_count)}",
                   cnt_ratio >= THRESHOLDS["rg_count_ratio"])
            + stat("Бонусы 30д", money(p.bonuses_30d_usd), f"{int(p.bonuses_30d_count)} шт.")
            + stat("Вывод в ожидании", money(p.pending_withdrawal_usd), "", p.pending_withdrawal_usd > 0)
            + stat("Неудачных депозитов", f"{int(p.failed_deposits_7d)}", "за 7 дней", p.failed_deposits_7d >= 3)
            + stat("Последний вход", f"{r['days_since_login']} дн. назад", "", r["days_since_login"] >= 14)
            + "</div>")

    left, right = st.columns([7, 5], gap="large")
    with left:
        st.html('<div class="section">Что сделать</div>')
        if r["action"]:
            owner, what, deadline = r["action"]
            when = ui.DEADLINE.get(deadline, "")
            st.html(f'<div class="action"><span class="who">{esc(ui.OWNER.get(owner, owner))}'
                    f'{" · " + esc(when) if when else ""}</span>{esc(what)}</div>')
        else:
            st.html('<div class="empty">Действий не требуется.</div>')

        st.html('<div class="section">Сигналы</div>')
        cards = []
        for i in r["items"]:
            src = "переписка" if i["source"] == "llm" else "данные CRM"
            q = f'<div class="quote">«{esc(i["evidence"])}»</div>' if i.get("evidence") else ""
            cards.append(f'<div class="sig {i["severity"]}"><div class="row">{sev_pill(i["severity"])}'
                         f'<span class="code">{esc(i["code"])}</span><span class="src">{src}</span></div>'
                         f'<div class="text">{esc(i["detail"])}</div>{q}</div>')
        st.html("".join(cards) or '<div class="empty">Сигналов нет.</div>')

        a = r["llm"]
        if a:
            label, kind = ui.OVERALL[a["overall"]]
            st.html(f'<div class="section">Разбор переписки {pill(label, kind)}</div>'
                    f'<div class="summary">{esc(a["summary"])}</div>')
            sc = "".join(f'<div class="score"><span>{esc(ui.SCORE_LABEL[k])}</span>{ui.dots(v, v == 0)}</div>'
                         for k, v in a["scores"].items())
            st.html(f'<div class="scores">{sc}</div>')
            st.html(f'<div class="section">Обратная связь менеджеру</div><div class="feedback">'
                    f'{esc(a["manager_feedback"])}</div>')
            if a["draft_message"]:
                st.html('<div class="section">Черновик ответа игроку</div>')
                st.code(a["draft_message"], language=None, wrap_lines=True)
            if a.get("review_flags"):
                with st.expander(f"На проверку человеком: {len(a['review_flags'])}"):
                    st.caption("Модель поставила эти флаги, но проверка кодом нашла противоречие, "
                               "поэтому в очередь они не попали.")
                    st.html("".join(
                        f'<div class="sig"><div class="row"><span class="code">{esc(f["code"])}</span></div>'
                        f'<div class="text">{esc(f["review_reason"])}</div>'
                        f'<div class="quote">«{esc(f["evidence"])}»</div></div>' for f in a["review_flags"]))
        elif r["dialog_ids"]:
            st.caption("Разбор этого диалога ещё не запускался.")

    with right:
        st.html('<div class="section">Переписка</div>')
        if not r["dialog_ids"]:
            st.html('<div class="empty">Диалогов с менеджером нет. Игрок виден только по данным CRM.</div>')
        for did in r["dialog_ids"]:
            st.html(ui.chat(dialogs[did], SLA))

# ─────────────────────────── менеджеры ───────────────────────────

elif view == "managers":
    cards, details = [], {}
    for mgr in [m for m in managers if m in sel_managers]:
        mdlg = [d for d in sig["dialogs"] if d["manager"] == mgr]
        times = [t for d in mdlg for t in d["response_times_min"]]
        mq = [r for r in queue if r["manager"] == mgr]
        codes = [i["code"] for r in mq for i in r["items"]]
        mllm = [analyses[d["dialog_id"]] for d in mdlg if d["dialog_id"] in analyses]
        late = sum(t > SLA for t in times)
        rg = sum(f["code"].startswith("RG_") for a in mllm for f in a["flags"])
        good = sum(any(f["code"] == "GOOD_PRACTICE" for f in a["flags"]) for a in mllm)
        line = lambda l, v, bad=False: (f'<div class="line"><span>{esc(l)}</span>'
                                        f'<b class="{"bad" if bad else ""}">{esc(v)}</b></div>')
        avg = f"{statistics.mean(a['score_total'] / 6 for a in mllm):.1f} из 3" if mllm else "—"
        cards.append(
            f'<div class="mgr"><div class="name">{esc(mgr)}</div>'
            + line("Игроков", f"{len(mq)}")
            + line("Медиана ответа", f"{round(statistics.median(times))} мин" if times else "—",
                   bool(times) and statistics.median(times) > SLA)
            + line("Дольше SLA", f"{late} из {len(times)}", late > 0)
            + line("Игнор игрока", str(codes.count("PLAYER_IGNORED")), codes.count("PLAYER_IGNORED") > 0)
            + line("Нарушений RG", str(rg) if mllm else "—", rg > 0)
            + line("Образцовых диалогов", str(good) if mllm else "—")
            + line("Средняя оценка", avg)
            + "</div>")
        details[mgr] = [r for r in mq if r["top_severity"] in ("critical", "high")]
    st.html(f'<div class="mgrs">{"".join(cards)}</div>')
    st.caption("Материал для еженедельного разговора с менеджером: скорость и игнор считает код, "
               "нарушения и оценки — разбор переписок.")

    for mgr, rows in details.items():
        with st.expander(f"{mgr}: игроки с высоким приоритетом — {len(rows)}"):
            st.html('<table class="q"><tbody>' + "".join(
                f'<tr><td style="width:92px">{sev_pill(r["top_severity"])}</td>'
                f'<td style="width:90px" class="mono">{esc(r["player_id"])}</td><td>{esc(r["reason"])}</td>'
                f'<td style="width:280px">{ui.action_html(r["action"])}</td>'
                f'<td><a class="open" href="{player_link(r["player_id"])}" target="_self">Открыть</a></td></tr>'
                for r in rows) + "</tbody></table>" if rows else '<div class="empty">Нет.</div>')
