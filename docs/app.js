/* VIP Intelligence — статический интерфейс поверх docs/data.json (его собирает python -m src.export). */
"use strict";

const SEV = { critical: "Критично", high: "Высокий", medium: "Средний", low: "Низкий", info: "Инфо" };
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
const OWNER = { manager: "Менеджер", teamlead: "Тимлид", payments: "Платежи", compliance: "Комплаенс",
                support: "Саппорт", product: "Продукт" };
const DEADLINE = { now: "в течение часа", today: "сегодня", this_week: "на этой неделе", none: "" };
const SCORE = { responsiveness: "Скорость", problem_solving: "Решение вопроса", accuracy: "Точность",
                personalization: "Персонализация", tone: "Тон", responsible_gambling: "Ответственная игра" };
const OVERALL = { critical: ["Критично", "crit"], poor: ["Плохо", "high"], ok: ["Нормально", ""],
                  good: ["Хорошо", "ok"], excellent: ["Образцово", "ok"] };
const CODE = {
  RG_SELF_EXCLUSION_DISCOURAGED: "Отговаривание от самоисключения", RG_LOSS_CHASING_ENCOURAGED: "Поощрение отыгрыша",
  RG_LIMIT_INCREASE_PUSHED: "Предложение поднять лимит", RG_WITHDRAWAL_DISCOURAGED: "Отговаривание от вывода",
  RG_RISK_SIGNS_IGNORED: "Игнор признаков риска", OPT_OUT_REQUEST: "Просьба об отписке", MULTI_ACCOUNT: "Мультиаккаунт",
  JURISDICTION_CHANGE: "Смена юрисдикции", MISLEADING_INFO: "Неверная информация", PRESSURE_TACTICS: "Давление",
  ISSUE_IGNORED: "Проблема проигнорирована", PROMISE_NOT_KEPT: "Обещание не выполнено", UNRESOLVED_PAYMENT: "Платёж не решён",
  RUDE_TONE: "Грубость", CHURN_THREAT: "Угроза ухода", PASSED_THE_BUCK: "Перекинул в другой отдел",
  SLOW_RESPONSE: "Медленный ответ", VAGUE_ANSWER: "Отписка вместо ответа", WRONG_NAME: "Ошибка в имени",
  LATE_GREETING: "Поздравление с опозданием", FEEDBACK_NOT_ESCALATED: "Фидбек не передан", GENERIC_OUTREACH: "Шаблонная рассылка",
  GOOD_PRACTICE: "Хорошая практика",
  PAYMENT_FAILURES: "Неудачные депозиты", PENDING_WITHDRAWAL: "Вывод в ожидании", RG_DEPOSIT_PATTERN: "Паттерн погони за проигрышем",
  RG_BONUS_DEPENDENCE: "Зависимость от бонусов", PLAYER_IGNORED: "Игрок без ответа", CHURNED: "Перестал играть",
  NO_CONTACT: "Нет контакта с менеджером", DEPOSIT_DROP: "Падение депозитов", INACTIVE: "Давно не заходил",
  ONE_WAY_OUTREACH: "Сообщения без ответа игрока", PLAYER_LAST_WORD: "Последнее слово за игроком", BIRTHDAY: "День рождения",
  UPGRADE_CANDIDATE: "Кандидат в VIP", SELF_EXCLUDED: "Самоисключён", LIMIT_SET: "Свой лимит",
};
const METRICS = [
  ["critical_flag_recall", "Критичные нарушения найдены"], ["critical_false_alarms", "Ложные «критично» на нормальных диалогах"],
  ["must_flag_recall", "Все обязательные флаги найдены"], ["flag_precision", "Точность флагов"],
  ["overall_accuracy", "Итоговая оценка в допустимом диапазоне"], ["intent_accuracy", "Тема диалога"],
  ["resolved_accuracy", "Решён ли вопрос"], ["needs_reply_accuracy", "Нужен ли ответ"],
];

const S = { data: null, src: null, view: "queue", pid: null, dtab: "overview",
            f: { manager: "", level: "medium", q: "" } };
const $ = (sel) => document.querySelector(sel);

function esc(x) {
  return String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const money = (x) => "$" + Math.round(x || 0).toLocaleString("ru-RU");
const lvl = (s) => s ? `<span class="lvl ${s}">${SEV[s]}</span>` : `<span class="lvl low">Нет сигналов</span>`;
const tag = (t, cls = "") => `<span class="tag ${cls}">${esc(t)}</span>`;
const src = () => S.data.sources[S.src];
const fmtDate = (s) => { const [y, m, d] = s.split("-"); return `${d}.${m}.${y}`; };

function action(a, compact = false) {
  if (!a) return `<span class="muted">—</span>`;
  const [owner, what, deadline] = a;
  const when = DEADLINE[deadline] ? ` · ${DEADLINE[deadline]}` : "";
  if (compact) return `<b>${esc(OWNER[owner] || owner)}</b><span class="muted">${esc(when)}</span>`;
  return `<span class="who">${esc(OWNER[owner] || owner)}</span><span class="when">${esc(when)}</span><div class="what">${esc(what)}</div>`;
}

/* ───────────── роутинг ───────────── */

function route() {
  const parts = location.hash.replace(/^#\/?/, "").split("/");
  S.view = ["queue", "retention", "team", "quality"].includes(parts[0]) ? parts[0] : "queue";
  if (parts[1]) { if (parts[1] !== S.pid) S.dtab = "overview"; S.pid = parts[1]; }
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("on", a.dataset.view === S.view));
  render();
}

function render() {
  const views = { queue: viewQueue, retention: viewRetention, team: viewTeam, quality: viewQuality };
  $("#app").innerHTML = views[S.view]();
  bind();
}

/* ───────────── очередь ───────────── */

function filteredQueue() {
  const { manager, level, q } = S.f;
  const max = level === "all" ? 3 : SEV_ORDER[level];
  return src().queue.filter((r) => r.top_severity && SEV_ORDER[r.top_severity] <= max
    && (!manager || r.manager === manager)
    && (!q || (r.player_id + " " + r.reason + " " + r.manager).toLowerCase().includes(q.toLowerCase())));
}

function viewQueue() {
  const all = src().queue.filter((r) => !S.f.manager || r.manager === S.f.manager);
  const rows = filteredQueue();
  if (!S.pid || !src().queue.some((r) => r.player_id === S.pid)) S.pid = rows[0]?.player_id || src().queue[0].player_id;
  const cnt = (s) => all.filter((r) => r.top_severity === s).length;
  const ret = src().retention.filter((x) => !S.f.manager || x.manager === S.f.manager);
  const noContact = all.filter((r) => r.items.some((i) => i.code === "NO_CONTACT")).length;
  const managers = [...new Set(src().queue.map((r) => r.manager))].sort();
  const seg = [["critical", "Критично"], ["high", "+ Высокий"], ["medium", "+ Средний"], ["all", "Все"]];

  return `
  <div class="head"><div><h1>Очередь</h1>
    <p>Кому и что нужно сделать сегодня. Порядок: серьёзность сигналов, их число и ценность игрока.</p></div></div>
  <div class="summary">
    <div><div class="k">Критично</div><div class="v crit">${cnt("critical")}</div><div class="s">нарушения RG и комплаенса</div></div>
    <div><div class="k">Высокий приоритет</div><div class="v high">${cnt("high")}</div><div class="s">деньги, игнор, отток</div></div>
    <div><div class="k">Средний</div><div class="v">${cnt("medium")}</div><div class="s">сервис и активность</div></div>
    <div><div class="k">Без контакта с менеджером</div><div class="v">${noContact}</div><div class="s">ценные игроки без диалога</div></div>
    <div><div class="k">Депозиты под риском оттока</div><div class="v">${money(ret.reduce((a, x) => a + x.value_60d_usd, 0))}</div>
      <div class="s">${ret.length} игроков, 60 дней</div></div>
  </div>
  <div class="split">
    <section class="panel">
      <div class="panel-head filters">
        <select id="f-manager"><option value="">Все менеджеры</option>${managers.map((m) =>
          `<option ${m === S.f.manager ? "selected" : ""}>${esc(m)}</option>`).join("")}</select>
        <div class="seg">${seg.map(([k, t]) => `<button data-level="${k}" class="${S.f.level === k ? "on" : ""}">${t}</button>`).join("")}</div>
        <input id="f-q" type="search" placeholder="Игрок или причина" value="${esc(S.f.q)}">
        <span class="count">${rows.length} из ${src().queue.length}</span>
      </div>
      <div class="list">
        <table class="t"><thead><tr><th>Уровень</th><th>Игрок</th><th>Менеджер</th><th>Причина</th>
          <th class="hide-sm">Кто · срок</th><th class="r hide-sm">Депозиты 60д</th></tr></thead><tbody>
        ${rows.map((r) => `<tr data-pid="${r.player_id}" class="${r.player_id === S.pid ? "on" : ""}">
          <td>${lvl(r.top_severity)}</td>
          <td><span class="mono">${r.player_id}</span><div class="sub">${esc(S.data.players[r.player_id].brand)} · ${esc(S.data.players[r.player_id].geo)}</div></td>
          <td>${esc(r.manager)}</td>
          <td><div class="clip">${esc(r.reason)}</div></td>
          <td class="hide-sm">${action(r.action, true)}</td>
          <td class="r num hide-sm">${money(r.value_60d_usd)}</td></tr>`).join("")
          || `<tr><td colspan="6" class="empty">Нет игроков с такими условиями</td></tr>`}
        </tbody></table>
      </div>
    </section>
    <aside class="panel detail">${detail(S.pid)}</aside>
  </div>`;
}

function detail(pid) {
  const p = S.data.players[pid];
  const r = src().queue.find((x) => x.player_id === pid);
  const an = (p.dialog_ids || []).map((d) => src().analyses?.[d]).filter(Boolean);
  const a = an[0];
  const status = p.account_status === "self_excluded" ? tag("Самоисключён", "crit")
    : p.account_status === "limit_set" ? tag("Свой лимит", "high") : tag("Активен");
  const tabs = [["overview", "Обзор"], ["chat", `Переписка${p.dialog_ids.length ? "" : " · нет"}`]];
  if (a) tabs.push(["analysis", "Разбор"]);
  if (!tabs.some(([k]) => k === S.dtab)) S.dtab = "overview";
  const body = { overview: () => detailOverview(p, r), chat: () => detailChat(p), analysis: () => detailAnalysis(a) }[S.dtab]();
  return `
    <div class="d-head">
      <div class="d-title"><span class="id">${pid}</span>${lvl(r.top_severity)}${status}${tag(p.status)}</div>
      <div class="d-meta">${esc(p.brand)} · ${esc(p.geo)} · менеджер ${esc(p.manager)} · любимая игра ${esc(p.favorite_game)}</div>
    </div>
    <div class="d-tabs">${tabs.map(([k, t]) => `<button data-dtab="${k}" class="${S.dtab === k ? "on" : ""}">${t}</button>`).join("")}</div>
    <div class="d-body">${body}</div>`;
}

function detailOverview(p, r) {
  const chg = p.deposit_change_pct;
  const ratio = p.deposits_30d_count / Math.max(p.deposits_prev_30d_count, 1);
  const st = (k, v, s = "", bad = false) => `<div><div class="k">${k}</div><div class="v ${bad ? "bad" : ""}">${v}</div><div class="s ${bad ? "bad" : ""}">${s}</div></div>`;
  const alert = p.account_status === "self_excluded" ? `<div class="alert">Игрок самоисключён: никаких офферов, промо и инициативных контактов.</div>`
    : p.account_status === "limit_set" ? `<div class="alert">Игрок сам поставил лимит: не предлагать повышение и депозитные бонусы.</div>` : "";
  return `${alert}
    <div class="stats">
      ${st("Депозиты 30д", money(p.deposits_30d_usd), chg == null ? "" : `${chg > 0 ? "+" : ""}${chg}% к прошлым 30д`, chg != null && chg <= -50)}
      ${st("Число депозитов", p.deposits_30d_count, `было ${p.deposits_prev_30d_count}`, ratio >= S.data.thresholds.rg_count_ratio)}
      ${st("Бонусы 30д", money(p.bonuses_30d_usd), `${p.bonuses_30d_count} шт.`)}
      ${st("Вывод в ожидании", money(p.pending_withdrawal_usd), "", p.pending_withdrawal_usd > 0)}
      ${st("Неудачных депозитов", p.failed_deposits_7d, "за 7 дней", p.failed_deposits_7d >= 3)}
      ${st("Последний вход", `${p.days_since_login} дн.`, "назад", p.days_since_login >= 14)}
    </div>
    <div class="sec">Что сделать<span class="line"></span></div>
    ${r.action ? `<div class="todo">${action(r.action)}</div>` : `<div class="muted">Действий не требуется.</div>`}
    <div class="sec">Сигналы · ${r.items.length}<span class="line"></span></div>
    ${r.items.map((i) => `<div class="sig">
      <div class="top">${lvl(i.severity)}<b>${esc(CODE[i.code] || i.code)}</b><span class="src">${i.source === "llm" ? "переписка" : "данные CRM"}</span></div>
      <div class="txt">${esc(i.detail)}</div>${i.evidence ? `<div class="q">«${esc(i.evidence)}»</div>` : ""}</div>`).join("")
      || `<div class="muted">Сигналов нет.</div>`}`;
}

function detailChat(p) {
  if (!p.dialog_ids.length) return `<div class="empty">Диалогов с менеджером нет — игрок виден только по данным CRM.</div>`;
  const sla = S.data.meta.sla_min;
  return p.dialog_ids.map((did) => {
    const d = S.data.dialogs[did];
    let prev = null;
    const out = d.messages.map((m) => {
      let gap = "";
      if (prev && prev.from === "player" && m.from === "manager") {
        const mins = Math.round((new Date(m.at.replace(" ", "T")) - new Date(prev.at.replace(" ", "T"))) / 60000);
        const t = mins < 120 ? `ответ через ${mins} мин` : `ответ через ${(mins / 60).toFixed(1)} ч`;
        gap = `<div class="gap ${mins > sla ? "late" : ""}">${t}${mins > sla ? " · дольше SLA" : ""}</div>`;
      }
      prev = m;
      return `${gap}<div class="msg ${m.from}">${esc(m.text)}<div class="t">${m.from === "player" ? "Игрок" : esc(d.manager)} · ${m.at.slice(8, 10)}.${m.at.slice(5, 7)} ${m.at.slice(11)}</div></div>`;
    }).join("");
    return `<div class="chat"><div class="chat-h"><span class="mono">${did}</span><span>${esc(d.channel)} · ${esc(d.manager)}</span></div>${out}</div>`;
  }).join("");
}

function detailAnalysis(a) {
  const [label, cls] = OVERALL[a.overall];
  const scores = Object.entries(a.scores).map(([k, v]) => `<div class="score"><span>${SCORE[k]}</span>
    <span class="bars ${v === 0 ? "bad" : ""}">${[0, 1, 2].map((i) => `<i class="${i < v ? "on" : ""}"></i>`).join("")}<b>${v}/3</b></span></div>`).join("");
  const review = (a.review_flags || []).length ? `<details class="review"><summary>На проверку человеком: ${a.review_flags.length}</summary>
    ${a.review_flags.map((f) => `<div class="sig"><div class="top"><b>${esc(CODE[f.code] || f.code)}</b></div>
      <div class="txt">${esc(f.review_reason)}</div><div class="q">«${esc(f.evidence)}»</div></div>`).join("")}</details>` : "";
  return `
    <div class="sec">Итог ${tag(label, cls)}<span class="line"></span></div>
    <div class="prose">${esc(a.summary)}</div>
    <div class="sec">Оценка менеджера<span class="line"></span></div>
    <div class="scores">${scores}</div>
    <div class="sec">Обратная связь менеджеру<span class="line"></span></div>
    <div class="prose">${esc(a.manager_feedback)}</div>
    ${a.draft_message ? `<div class="sec">Черновик ответа игроку<span class="line"></span><button class="copy" data-copy>Копировать</button></div>
      <div class="draft" id="draft">${esc(a.draft_message)}</div>` : ""}
    ${review}`;
}

/* ───────────── риск оттока ───────────── */

function viewRetention() {
  const ret = src().retention;
  const hold = ret.filter((x) => x.rg_hold).length;
  return `
  <div class="head"><div><h1>Риск оттока</h1>
    <p>Кто может уйти и сколько за ним стоит. Сначала деньги и сервис, потом предложение.</p></div></div>
  <div class="summary" style="grid-template-columns:repeat(4,1fr)">
    <div><div class="k">Игроков под риском</div><div class="v high">${ret.length}</div><div class="s">есть хотя бы одна причина уйти</div></div>
    <div><div class="k">Депозиты под риском</div><div class="v">${money(ret.reduce((a, x) => a + x.value_60d_usd, 0))}</div><div class="s">за последние 60 дней</div></div>
    <div><div class="k">Удерживать только сервисом</div><div class="v">${hold}</div><div class="s">признаки риска: без бонусов и промо</div></div>
    <div><div class="k">Можно с предложением</div><div class="v">${ret.length - hold}</div><div class="s">после решения проблемы</div></div>
  </div>
  <section class="panel"><div class="panel-head"><span class="panel-title">Игроки под риском</span>
    <span class="count">по сумме под риском: депозиты 60 дней × число причин</span></div>
    <table class="t"><thead><tr><th>Игрок</th><th>Менеджер</th><th class="r">Депозиты 60д</th><th>Почему может уйти</th><th>Режим</th><th>Что сделать</th></tr></thead><tbody>
    ${ret.map((x) => `<tr data-pid="${x.player_id}">
      <td class="mono">${x.player_id}</td><td>${esc(x.manager)}</td><td class="r num">${money(x.value_60d_usd)}</td>
      <td>${x.reasons.slice(0, 3).map(esc).join("<br>")}${x.reasons.length > 3 ? `<div class="sub">и ещё ${x.reasons.length - 3}</div>` : ""}</td>
      <td>${x.rg_hold ? tag("Только сервис") : tag("Можно оффер", "blue")}</td>
      <td>${esc(x.action)}</td></tr>`).join("")}
    </tbody></table></section>
  <p class="note">Игроку с признаками проблемной игры или самоограничениями бонус — нарушение, а не удержание: его удерживают быстрым выводом, ответом по существу и вниманием.</p>
  ${src().practices.length ? `<section class="panel" style="margin-top:16px"><div class="panel-head"><span class="panel-title">Как удерживают лучшие</span>
    <span class="count">моменты из переписок для обучения команды</span></div><div class="panel-body">
    ${src().practices.map((b) => `<div class="practice"><div class="h"><b>${esc(b.manager)}</b><span class="mono">${b.dialog_id}</span><span>${esc(b.situation)}</span></div>
      <div class="q">«${esc(b.evidence)}»</div><div class="w">${esc(b.why)}</div></div>`).join("")}
  </div></section>` : ""}`;
}

/* ───────────── команда ───────────── */

function viewTeam() {
  const sla = S.data.meta.sla_min;
  const m = src().managers;
  const val = (v, bad) => v == null ? `<span class="muted">—</span>` : `<span class="${bad ? "bad" : ""}">${v}</span>`;
  return `
  <div class="head"><div><h1>Команда</h1>
    <p>Материал для еженедельного разговора с менеджером. SLA ответа — ${sla} мин.</p></div></div>
  <section class="panel"><table class="t static"><thead><tr>
    <th>Менеджер</th><th class="r">Игроков</th><th class="r">Диалогов</th><th class="r">Медиана ответа</th><th class="r">Дольше SLA</th>
    <th class="r">Игнор</th><th class="r">Критично</th><th class="r">Высокий</th><th class="r">Нарушений RG</th><th class="r">Образцовых</th>
    <th class="r">Средняя оценка</th><th class="r">Депозиты игроков 60д</th></tr></thead><tbody>
    ${m.map((x) => `<tr><td><b>${esc(x.manager)}</b></td><td class="r num">${x.players}</td><td class="r num">${x.dialogs}</td>
      <td class="r num">${val(x.median_response_min == null ? null : x.median_response_min + " мин", x.median_response_min > sla)}</td>
      <td class="r num">${val(`${x.late} из ${x.responses}`, x.late > 0)}</td><td class="r num">${val(x.ignored, x.ignored > 0)}</td>
      <td class="r num">${val(x.critical, x.critical > 0)}</td><td class="r num">${x.high}</td><td class="r num">${val(x.rg_violations, x.rg_violations > 0)}</td>
      <td class="r num">${val(x.good_practice)}</td><td class="r num">${val(x.avg_score == null ? null : x.avg_score.toFixed(1) + " из 3")}</td>
      <td class="r num">${money(x.value_60d_usd)}</td></tr>`).join("")}
  </tbody></table></section>
  <div class="grid2" style="margin-top:16px">
    ${m.map((x) => {
      const rows = src().queue.filter((r) => r.manager === x.manager && ["critical", "high"].includes(r.top_severity));
      return `<section class="panel"><div class="panel-head"><span class="panel-title">${esc(x.manager)}</span>
        <span class="count">игроки с высоким приоритетом: ${rows.length}</span></div>
        <table class="t"><tbody>${rows.map((r) => `<tr data-pid="${r.player_id}"><td style="width:96px">${lvl(r.top_severity)}</td>
          <td class="mono" style="width:70px">${r.player_id}</td><td><div class="clip">${esc(r.reason)}</div></td></tr>`).join("")
          || `<tr><td class="empty">Нет</td></tr>`}</tbody></table></section>`;
    }).join("")}
  </div>`;
}

/* ───────────── качество ───────────── */

function viewQuality() {
  const srcs = Object.entries(S.data.sources).filter(([, s]) => s.metrics);
  const cell = (m, key) => {
    if (!m) return "—";
    if (key === "critical_false_alarms") return `<span class="${m.value ? "bad" : "okc"}">${m.value} из ${m.den}</span>`;
    if (m.value == null) return "—";
    const pct = Math.round(m.value * 100);
    return `<b class="num">${pct}%</b> <span class="muted num">${m.num}/${m.den}</span>`;
  };
  return `
  <div class="head"><div><h1>Качество разбора</h1>
    <p>Сравнение с ручной разметкой всех 40 диалогов. Главная метрика — найденные критичные нарушения: пропуск хуже ложной тревоги.</p></div></div>
  <section class="panel"><table class="t static"><thead><tr><th>Метрика</th>
    ${srcs.map(([, s]) => `<th class="r">${esc(s.label)}<div class="sub">${esc(s.model)}</div></th>`).join("")}</tr></thead><tbody>
    ${METRICS.map(([k, t]) => `<tr><td>${t}</td>${srcs.map(([, s]) => `<td class="r">${cell(s.metrics[k], k)}</td>`).join("")}</tr>`).join("")}
  </tbody></table></section>
  <div class="grid2" style="margin-top:16px">
    <section class="panel"><div class="panel-head"><span class="panel-title">Как устроен разбор</span></div><div class="panel-body">
      <ol class="method">
        <li><b>Сигналы считает код</b><span class="muted">Время ответа, падение депозитов, частые мелкие депозиты, висящие выводы — детерминированно, из CRM и переписки.</span></li>
        <li><b>Модель разбирает смысл</b><span class="muted">По рубрике и строгой схеме: тема, флаги с цитатой, оценки менеджера, действие, черновик ответа.</span></li>
        <li><b>Второй проход проверяет критичное</b><span class="muted">Каждое нарушение — узкий вопрос «что сказал игрок → что ответил менеджер». Модель приводит цитаты, решение принимает код: автор, порядок, признак действия.</span></li>
        <li><b>Код назначает серьёзность и приоритет</b><span class="muted">Сомнительные флаги уходят на проверку человеком и не попадают в очередь.</span></li>
      </ol></div></section>
    <section class="panel"><div class="panel-head"><span class="panel-title">Оговорки</span></div><div class="panel-body prose">
      ${srcs.map(([, s]) => `<p><b>${esc(s.label)}.</b> <span class="muted">${esc(s.note)}.</span></p>`).join("")}
      <p class="muted">Правила промпта и словарь признаков действий выводились на этих же 40 диалогах. Для независимой оценки нужен новый размеченный набор переписок.</p>
    </div></section>
  </div>`;
}

/* ───────────── события ───────────── */

function bind() {
  document.querySelectorAll("tr[data-pid]").forEach((tr) => tr.addEventListener("click", () => {
    location.hash = `#/queue/${tr.dataset.pid}`;
  }));
  document.querySelectorAll("[data-level]").forEach((b) => b.addEventListener("click", () => { S.f.level = b.dataset.level; render(); }));
  document.querySelectorAll("[data-dtab]").forEach((b) => b.addEventListener("click", () => { S.dtab = b.dataset.dtab; render(); }));
  const m = $("#f-manager"); if (m) m.addEventListener("change", () => { S.f.manager = m.value; render(); });
  const q = $("#f-q");
  if (q) q.addEventListener("input", () => {
    S.f.q = q.value; const pos = q.selectionStart; render();
    const nq = $("#f-q"); nq.focus(); nq.setSelectionRange(pos, pos);
  });
  const c = document.querySelector("[data-copy]");
  if (c) c.addEventListener("click", () => {
    navigator.clipboard.writeText($("#draft").textContent).then(() => { c.textContent = "Скопировано"; setTimeout(() => (c.textContent = "Копировать"), 1500); });
  });
  // Прокручиваем только список, а не всю страницу.
  const sel = $("tr.on"), list = $(".list");
  if (sel && list && S.view === "queue") {
    const top = sel.offsetTop - list.querySelector("thead").offsetHeight;
    if (top < list.scrollTop || sel.offsetTop + sel.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = top - 8;
  }
}

async function init() {
  const res = await fetch("data.json", { cache: "no-cache" });
  S.data = await res.json();
  let saved = null;
  try { saved = localStorage.getItem("vip-source"); } catch (e) { /* приватный режим */ }
  S.src = saved && S.data.sources[saved] ? saved : S.data.meta.default_source;
  const sel = $("#source");
  sel.innerHTML = Object.entries(S.data.sources).map(([k, s]) =>
    `<option value="${k}" ${k === S.src ? "selected" : ""}>${esc(s.label)}</option>`).join("");
  sel.addEventListener("change", () => {
    S.src = sel.value; try { localStorage.setItem("vip-source", S.src); } catch (e) { /* ничего */ }
    render();
  });
  $("#asof").textContent = `Срез данных ${fmtDate(S.data.meta.as_of)} · ${Object.keys(S.data.players).length} игроков · ${Object.keys(S.data.dialogs).length} диалогов`;
  $("#gen").textContent = `Данные собраны ${S.data.meta.generated}`;
  window.addEventListener("hashchange", route);
  route();
}

init().catch((e) => { $("#app").innerHTML = `<div class="empty">Не удалось загрузить данные: ${esc(e.message)}</div>`; });
