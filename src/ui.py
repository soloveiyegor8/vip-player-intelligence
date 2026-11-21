"""HTML-компоненты интерфейса. Весь пользовательский текст проходит через esc()."""
from __future__ import annotations

from html import escape
from urllib.parse import urlencode

SEV_TEXT = {"critical": "Критично", "high": "Высокий", "medium": "Средний", "low": "Низкий", "info": "Инфо"}
OWNER = {"manager": "Менеджер", "teamlead": "Тимлид", "payments": "Платежи", "compliance": "Комплаенс",
         "support": "Саппорт", "product": "Продукт"}
DEADLINE = {"now": "в течение часа", "today": "сегодня", "this_week": "на неделе", "none": ""}
SCORE_LABEL = {"responsiveness": "Скорость", "problem_solving": "Решение вопроса", "accuracy": "Точность",
               "personalization": "Персонализация", "tone": "Тон", "responsible_gambling": "Ответственная игра"}
OVERALL = {"critical": ("Критично", "critical"), "poor": ("Плохо", "high"), "ok": ("Нормально", "medium"),
           "good": ("Хорошо", "good"), "excellent": ("Образцово", "good")}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ink: #1C1D1F; --muted: #6B6C70; --faint: #9A9B9F; --line: #E4E2DB; --card: #FFFFFF; --bg: #FAFAF7;
  --accent: #0F766E; --accent-soft: #E6F2F0;
  --crit: #B42318; --crit-bg: #FDECEA; --high: #B54708; --high-bg: #FDF1E3;
  --med: #8A6A00; --med-bg: #FBF5DC; --low: #5D6168; --low-bg: #EFEEEA; --good: #2B6B3F; --good-bg: #E7F2EA;
}
html, body, [class*="css"] { font-family: 'IBM Plex Sans', system-ui, sans-serif; }
.block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1320px; }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }
.mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-size: 0.92em; }

/* шапка */
.topbar { display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
          border-bottom: 1px solid var(--line); padding-bottom: 14px; margin-bottom: 18px; }
.brand { font-weight: 600; font-size: 1.15rem; color: var(--ink); }
.brand span { color: var(--muted); font-weight: 400; margin-left: 10px; font-size: 0.95rem; }
.meta { color: var(--muted); font-size: 0.85rem; }

/* показатели */
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 4px 0 20px; }
.kpi { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
.kpi .label { color: var(--muted); font-size: 0.8rem; margin-bottom: 6px; }
.kpi .value { font-size: 1.6rem; font-weight: 600; line-height: 1.1; color: var(--ink); }
.kpi .sub { color: var(--faint); font-size: 0.78rem; margin-top: 4px; }
.kpi.crit { border-left: 3px solid var(--crit); }
.kpi.high { border-left: 3px solid var(--high); }

/* метки */
.pill { display: inline-block; font-size: 0.72rem; font-weight: 500; padding: 2px 8px; border-radius: 4px;
        white-space: nowrap; line-height: 1.5; }
.pill.critical { color: var(--crit); background: var(--crit-bg); }
.pill.high { color: var(--high); background: var(--high-bg); }
.pill.medium { color: var(--med); background: var(--med-bg); }
.pill.low, .pill.info { color: var(--low); background: var(--low-bg); }
.pill.good { color: var(--good); background: var(--good-bg); }
.pill.outline { color: var(--muted); background: transparent; border: 1px solid var(--line); }
.pill.accent { color: var(--accent); background: var(--accent-soft); }

/* таблицы */
table.q { width: 100%; border-collapse: separate; border-spacing: 0; background: var(--card);
          border: 1px solid var(--line); border-radius: 8px; overflow: hidden; font-size: 0.88rem; }
table.q th { text-align: left; font-weight: 500; color: var(--muted); font-size: 0.76rem; text-transform: none;
             padding: 10px 12px; border-bottom: 1px solid var(--line); background: #F6F5F1; }
table.q td { padding: 12px; border-bottom: 1px solid var(--line); vertical-align: top; color: var(--ink); }
table.q tr:last-child td { border-bottom: none; }
table.q tr:hover td { background: #FBFBF8; }
table.q .who { font-weight: 500; }
table.q .sub { color: var(--muted); font-size: 0.78rem; margin-top: 2px; }
table.q .quote { color: var(--muted); font-size: 0.8rem; margin-top: 4px; font-style: italic; }
table.q a.open { color: var(--accent); text-decoration: none; font-weight: 500; white-space: nowrap; }
table.q a.open:hover { text-decoration: underline; }
.act-owner { font-weight: 500; }
.act-when { color: var(--muted); }

/* карточка игрока */
.p-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 4px; }
.p-id { font-size: 1.45rem; font-weight: 600; }
.notice { border: 1px solid var(--line); border-left: 3px solid var(--crit); background: var(--card);
          padding: 10px 14px; border-radius: 6px; margin: 10px 0; font-size: 0.9rem; }
.stats { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0; border: 1px solid var(--line);
         border-radius: 8px; background: var(--card); margin: 14px 0 20px; }
.stat { padding: 12px 14px; border-right: 1px solid var(--line); }
.stat:last-child { border-right: none; }
.stat .label { color: var(--muted); font-size: 0.76rem; }
.stat .value { font-weight: 600; font-size: 1.05rem; margin-top: 4px; }
.stat .delta { font-size: 0.76rem; margin-top: 2px; color: var(--muted); }
.stat .delta.bad { color: var(--crit); }
.section { font-size: 0.78rem; font-weight: 600; color: var(--muted); text-transform: uppercase;
           letter-spacing: 0.05em; margin: 22px 0 10px; }
.sig { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px;
       margin-bottom: 8px; }
.sig.critical { border-left: 3px solid var(--crit); }
.sig.high { border-left: 3px solid var(--high); }
.sig.medium { border-left: 3px solid #D4B106; }
.sig .row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap; }
.sig .code { font-family: 'IBM Plex Mono', monospace; font-size: 0.74rem; color: var(--faint); }
.sig .src { margin-left: auto; font-size: 0.72rem; color: var(--faint); }
.sig .text { font-size: 0.9rem; }
.sig .quote { margin-top: 6px; padding-left: 10px; border-left: 2px solid var(--line); color: var(--muted);
              font-size: 0.85rem; }
.action { background: var(--accent-soft); border-radius: 8px; padding: 12px 14px; font-size: 0.92rem; }
.action .who { font-weight: 600; color: var(--accent); margin-right: 8px; }
.summary { font-size: 0.95rem; line-height: 1.55; }
.scores { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 24px; margin: 10px 0; }
.score { display: flex; align-items: center; justify-content: space-between; font-size: 0.85rem; }
.dots { display: inline-flex; gap: 3px; }
.dots i { width: 18px; height: 6px; border-radius: 2px; background: var(--line); display: inline-block; }
.dots i.on { background: var(--ink); }
.dots.bad i.on { background: var(--crit); }
.feedback { font-size: 0.9rem; color: var(--ink); line-height: 1.5; }
.draft { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px;
         font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap; }

/* переписка */
.chat { background: #F3F2ED; border: 1px solid var(--line); border-radius: 10px; padding: 14px;
        max-height: 640px; overflow-y: auto; }
.chat-head { display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--muted);
             margin-bottom: 10px; }
.msg { max-width: 82%; padding: 8px 12px; border-radius: 10px; margin: 4px 0; font-size: 0.88rem;
       line-height: 1.45; }
.msg .t { font-size: 0.7rem; color: var(--faint); margin-top: 3px; }
.msg.player { background: var(--card); border: 1px solid var(--line); border-top-left-radius: 3px; }
.msg.manager { background: #DDEDEA; margin-left: auto; border-top-right-radius: 3px; }
.gap { text-align: center; font-size: 0.7rem; color: var(--faint); margin: 8px 0; }
.gap.late { color: var(--crit); }
.empty { color: var(--muted); font-size: 0.9rem; padding: 14px 0; }

/* менеджеры */
.mgrs { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 18px; }
.mgr { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px; }
.mgr .name { font-weight: 600; margin-bottom: 10px; }
.mgr .line { display: flex; justify-content: space-between; font-size: 0.82rem; padding: 3px 0;
             color: var(--muted); }
.mgr .line b { color: var(--ink); font-weight: 500; white-space: nowrap; margin-left: 8px; }
.mgr .line span { min-width: 0; }
.mgr .line b.bad { color: var(--crit); }

/* мелочи streamlit */
.score .n { font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--muted); margin-left: 8px;
            width: 26px; text-align: right; display: inline-block; }
.score .n.bad { color: var(--crit); font-weight: 500; }
[data-testid="stCode"] pre, [data-testid="stCode"] code { font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
  font-size: 0.9rem !important; line-height: 1.55 !important; background: var(--card) !important; }
[data-testid="stCode"] pre { border: 1px solid var(--line); border-radius: 8px; }
[data-baseweb="tag"] { background: var(--accent-soft) !important; color: var(--accent) !important; }
[data-baseweb="tag"] span { color: var(--accent) !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }
[data-testid="stSidebar"] { border-right: 1px solid var(--line); }
div[data-testid="stExpander"] details { border-color: var(--line); background: var(--card); }
</style>
"""


def esc(x) -> str:
    return escape("" if x is None else str(x))


def money(x) -> str:
    return f"${int(x):,}".replace(",", " ")


def link(params: dict) -> str:
    return "?" + urlencode(params)


def pill(text: str, kind: str) -> str:
    return f'<span class="pill {kind}">{esc(text)}</span>'


def sev_pill(sev: str | None) -> str:
    return pill(SEV_TEXT.get(sev, "—"), sev or "low")


def action_html(a) -> str:
    if not a:
        return '<span class="act-when">—</span>'
    owner, what, deadline = a
    when = DEADLINE.get(deadline, "")
    return (f'<span class="act-owner">{esc(OWNER.get(owner, owner))}</span>'
            + (f' <span class="act-when">· {esc(when)}</span>' if when else "")
            + f'<div class="sub">{esc(what)}</div>')


def kpis(items: list[tuple[str, str, str, str]]) -> str:
    """items: (подпись, значение, подстрочник, класс)."""
    cells = "".join(f'<div class="kpi {cls}"><div class="label">{esc(l)}</div><div class="value">{esc(v)}</div>'
                    f'<div class="sub">{esc(s)}</div></div>' for l, v, s, cls in items)
    return f'<div class="kpis">{cells}</div>'


def dots(v: int, bad: bool = False) -> str:
    bars = "".join(f'<i class="{"on" if k < v else ""}"></i>' for k in range(3))
    return (f'<span><span class="dots{" bad" if bad else ""}">{bars}</span>'
            f'<span class="n{" bad" if bad else ""}">{v}/3</span></span>')


def chat(dialog: dict, sla_min: int) -> str:
    out = [f'<div class="chat"><div class="chat-head"><span>{esc(dialog["dialog_id"])} · '
           f'{esc(dialog["channel"].capitalize())}</span><span>{esc(dialog["manager"])}</span></div>']
    prev = None
    for m in dialog["messages"]:
        if prev is not None and prev["from"] == "player" and m["from"] == "manager":
            mins = int((m["sent_at"] - prev["sent_at"]).total_seconds() // 60)
            label = f"ответ через {mins} мин" if mins < 120 else f"ответ через {mins / 60:.1f} ч"
            out.append(f'<div class="gap{" late" if mins > sla_min else ""}">{esc(label)}</div>')
        elif prev is not None and (m["sent_at"] - prev["sent_at"]).total_seconds() > 6 * 3600:
            out.append(f'<div class="gap">{esc(m["sent_at"].strftime("%d.%m"))}</div>')
        who = "player" if m["from"] == "player" else "manager"
        out.append(f'<div class="msg {who}">{esc(m["text"])}'
                   f'<div class="t">{esc(m["sent_at"].strftime("%d.%m %H:%M"))}</div></div>')
        prev = m
    out.append("</div>")
    return "".join(out)
