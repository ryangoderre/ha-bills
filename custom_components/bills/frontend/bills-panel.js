const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

const todayIso = () => new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD, local time

const FREQUENCIES = [
  ["once", "Doesn't repeat"],
  ["weekly", "Weekly"],
  ["monthly", "Monthly"],
  ["yearly", "Yearly"],
];
const UNITS = { weekly: "week", monthly: "month", yearly: "year" };

const NEW_BILL = {
  name: "", amount: null, next_due: null, frequency: "monthly", interval: 1,
  end_date: null, remind_days_before: 3, autopay: false, biller_url: null, notes: null,
  category_id: null,
};

const UPCOMING_LIMIT = 3;
const RECENT_PAYMENTS = 5;      // Recent payments shows this many until expanded
const RECENT_PAYMENTS_MAX = 25; // and at most this many when expanded
const BILL_ICON = "mdi:file-document-outline";      // bills without a category
const UNCATEGORIZED_ICON = "mdi:shape-outline";
const DEFAULT_CATEGORY_ICON = "mdi:tag";
const ICON_RE = /^[a-z0-9-]+:[a-z0-9-]+$/;
const SUGGESTED_ICONS = [
  "mdi:home", "mdi:flash", "mdi:water", "mdi:fire", "mdi:wifi", "mdi:cellphone",
  "mdi:television-classic", "mdi:cloud", "mdi:music", "mdi:car", "mdi:gas-station",
  "mdi:shield-check", "mdi:heart-pulse", "mdi:credit-card", "mdi:bank", "mdi:cart",
  "mdi:food", "mdi:dumbbell", "mdi:school", "mdi:paw", "mdi:baby-carriage",
  "mdi:tools", "mdi:trash-can", "mdi:gift",
];

class BillsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._bills = [];    // active
    this._retired = [];  // retired, most recently retired first
    this._showRetired = false;
    this._showAllBills = false;  // Upcoming shows UPCOMING_LIMIT until expanded
    this._showMorePayments = false;  // Recent payments: RECENT_PAYMENTS or up to RECENT_PAYMENTS_MAX
    this._payments = [];
    this._categories = [];
    this._costs = null;  // { today, month, year, previous_years } from bills.cost_summary
    this._history = null;  // { id, data, error, showAll } for the payment history view
    this._yearSel = {};  // year -> selected month index, -1 (or missing) for Total
    this._openYears = new Set();   // years (this one included) that are expanded
    this._showMonths = new Set();  // years showing their Jan … Dec chips
    // _form: null, or { kind, id } where kind is
    // "pay" | "edit" | "add" | "restore" | "categories" | "category"
    const payId = new URLSearchParams(window.location.search).get("pay");
    this._form = payId ? { kind: "pay", id: payId } : null;
    this._msg = "";
    this._error = "";
    this._loaded = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded) {
      this._loaded = true;
      this._refresh(true);
    }
  }
  set narrow(v) { this._narrow = v; }
  set panel(v) { this._panel = v; }

  disconnectedCallback() {
    clearTimeout(this._msgTimer);
  }

  _flash(msg) {
    this._msg = msg;
    clearTimeout(this._msgTimer);
    this._msgTimer = setTimeout(() => this._hideMsg(), 8000);
  }

  _hideMsg() {
    this._msg = "";
    const el = this.shadowRoot.querySelector(".ok");
    if (!el) return;
    el.classList.add("hide");
    setTimeout(() => el.remove(), 400);
  }

  async _call(service, data = {}) {
    const res = await this._hass.callWS({
      type: "call_service",
      domain: "bills",
      service,
      service_data: data,
      return_response: true,
    });
    return res.response;
  }

  async _refresh(initial = false) {
    try {
      const [b, p, c, costs] = await Promise.all([
        this._call("list_bills", { include_retired: true }),
        this._call("list_payments"),
        this._call("list_categories"),
        this._call("cost_summary"),
      ]);
      this._bills = b.bills.filter((x) => x.active);
      this._retired = b.bills.filter((x) => !x.active).sort((x, y) =>
        (y.retired_on || "").localeCompare(x.retired_on || ""));
      this._payments = p.payments.slice(0, RECENT_PAYMENTS_MAX);
      this._categories = c.categories;
      this._costs = costs;
      this._error = "";
      if (initial && this._form && !this._bill(this._form.id)) {
        this._flash("That bill isn't active anymore.");
        this._close(false);
      }
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._render();
  }

  _bill(id) {
    return this._bills.find((b) => b.id === id);
  }

  _retiredBill(id) {
    return this._retired.find((b) => b.id === id);
  }

  _category(id) {
    return id ? this._categories.find((c) => c.id === id) : undefined;
  }

  _open(kind, id = null) {
    this._form = { kind, id };
    this._msg = "";
    this._render();
    window.scrollTo(0, 0);
  }

  _close(render = true) {
    this._form = null;
    if (window.location.search) {
      history.replaceState(null, "", window.location.pathname);
    }
    if (render) this._render();
  }

  _money(n) {
    if (n === null || n === undefined) return "—";
    const cur = (this._hass && this._hass.config.currency) || "USD";
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(n);
  }

  _icon(name, cls = "") {
    return `<ha-icon class="${cls}" icon="${esc(name)}"></ha-icon>`;
  }

  _billIcon(b) {
    const c = b && this._category(b.category_id);
    return this._icon(c ? c.icon : BILL_ICON, "lead");
  }

  _daysUntil(iso) {
    const due = new Date(iso + "T00:00:00");
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return Math.round((due - today) / 86400000);
  }

  _when(iso) {
    const d = this._daysUntil(iso);
    if (d < 0) return { text: `overdue by ${-d} day${d === -1 ? "" : "s"}`, cls: "late" };
    if (d === 0) return { text: "due today", cls: "soon" };
    if (d === 1) return { text: "due tomorrow", cls: "soon" };
    return { text: `due in ${d} days`, cls: "" };
  }

  _repeats(b) {
    if (b.frequency === "once") return "one-time";
    const unit = UNITS[b.frequency];
    return b.interval === 1 ? `${b.frequency}` : `every ${b.interval} ${unit}s`;
  }

  // ---------- lists ----------

  _billsList() {
    if (!this._bills.length) {
      return `<p class="muted">No active bills. Use <b>Add bill</b> to create one.</p>`;
    }
    const hidden = this._bills.length - UPCOMING_LIMIT;
    const shown = this._showAllBills ? this._bills : this._bills.slice(0, UPCOMING_LIMIT);
    const toggle = hidden > 0
      ? `<button class="link showmore" id="toggle-bills" aria-expanded="${this._showAllBills}">${
          this._showAllBills ? "Show fewer" : `Show ${hidden} more`}</button>`
      : "";
    return shown.map((b) => {
      const w = this._when(b.next_due);
      return `<div class="row">
        ${this._billIcon(b)}
        <button class="rowlink grow" data-history="${esc(b.id)}" title="Payment history">
          <div class="name">${esc(b.name)}${b.autopay ? ' <span class="tag">autopay</span>' : ""}</div>
          <div class="muted ${w.cls}">${esc(b.next_due)} · ${w.text} · ${esc(this._repeats(b))}</div>
        </button>
        <div class="amt">${this._money(b.amount)}</div>
        <div class="btns">
          <button class="secondary" data-edit="${esc(b.id)}">Edit</button>
          <button data-pay="${esc(b.id)}">Pay</button>
        </div>
      </div>`;
    }).join("") + toggle;
  }

  _retiredSection() {
    if (!this._retired.length) return "";
    const n = this._retired.length;
    const rows = this._retired.map((b) => `<div class="row">
        ${this._billIcon(b)}
        <button class="rowlink grow" data-history="${esc(b.id)}" title="Payment history">
          <div class="name">${esc(b.name)}</div>
          <div class="muted">${b.retired_on ? "retired " + esc(b.retired_on) + " · " : ""}${
            esc(this._repeats(b))}</div>
        </button>
        <div class="amt muted">${this._money(b.amount)}</div>
        <div class="btns">
          <button class="secondary" data-restore="${esc(b.id)}">Restore</button>
        </div>
      </div>`).join("");
    return `<div class="section-head">
        <h2>Retired</h2>
        <button class="link" id="toggle-retired" aria-expanded="${this._showRetired}">
          ${this._showRetired ? "Hide" : `Show ${n} retired bill${n === 1 ? "" : "s"}`}</button>
      </div>
      ${this._showRetired ? `<div class="card">${rows}</div>` : ""}`;
  }

  _paymentsList() {
    if (!this._payments.length) return `<p class="muted">No payments yet.</p>`;
    const hidden = this._payments.length - RECENT_PAYMENTS;
    const shown = this._showMorePayments ? this._payments : this._payments.slice(0, RECENT_PAYMENTS);
    const toggle = hidden > 0
      ? `<button class="link showmore" id="toggle-payments" aria-expanded="${this._showMorePayments}">${
          this._showMorePayments ? "Show fewer" : `Show ${hidden} more`}</button>`
      : "";
    return shown.map((p) => {
      const bill = this._bill(p.bill_id) || this._retiredBill(p.bill_id);
      return `<div class="row">
        ${this._billIcon(bill)}
        <button class="rowlink grow" data-history="${esc(p.bill_id)}" title="Payment history">
          <div class="name">${esc(p.bill_name)}</div>
          <div class="muted">paid ${esc(p.paid_date)} for ${esc(p.due_date)}${
            p.confirmation ? " · #" + esc(p.confirmation) : ""}</div>
        </button>
        <div class="amt">${this._money(p.amount_paid)}</div>
      </div>`;
    }).join("") + toggle;
  }

  // ---------- cost summaries ----------

  _monthLabel(iso, style = "long") {
    return new Date(iso + "T00:00:00").toLocaleDateString(undefined,
      style === "long" ? { month: "long", year: "numeric" } : { month: "short" });
  }

  // "$130.00 paid · $40.00 upcoming · 1 without amount"
  _splitText(x, dueWord, fullWord) {
    const parts = [];
    if (x.paid && !x.upcoming && !x.unpriced) parts.push(fullWord);
    else if (x.paid) parts.push(`${this._money(x.paid)} paid`);
    if (x.upcoming) parts.push(`${this._money(x.upcoming)} ${dueWord}`);
    if (x.unpriced) parts.push(`${x.unpriced} without amount`);
    return parts.join(" · ") || "—";
  }

  // Totals, a paid meter and the categories of one breakdown (from
  // bills.cost_summary). With showBills, each category lists its bills.
  _breakdown(s, { emptyText, showBills = false }) {
    if (!s.categories.length) return `<p class="muted">${esc(emptyText)}</p>`;
    // A period that's over has nothing upcoming, only unpaid.
    const past = this._costs && s.end < this._costs.today;
    const dueWord = past ? "unpaid" : "upcoming";
    const pctPaid = (x) => (x.total > 0 ? Math.round((x.paid / x.total) * 100) : 0);
    const paidPct = pctPaid(s);
    // Every bar shows how much is paid: the top one for the whole period,
    // each category's for that category.
    const rows = s.categories.map((c) => {
      const pct = pctPaid(c);
      const lines = showBills && c.bills ? `<div class="billlines">${c.bills.map((b) => `
          <div class="billline">
            <span>${esc(b.name)}${b.count > 1 ? ` <span class="muted">×${b.count}</span>` : ""}</span>
            <span>${this._splitText(b, dueWord, `${this._money(b.paid)} paid`)}</span>
          </div>`).join("")}</div>` : "";
      return `<div class="row cat">
        ${this._icon(c.icon || (c.id ? DEFAULT_CATEGORY_ICON : UNCATEGORIZED_ICON), "lead")}
        <div class="grow">
          <div class="name">${esc(c.name)}</div>
          <div class="muted small">${this._splitText(c, dueWord, "paid in full")}</div>
          <div class="minibar" title="${pct}% paid"><span style="width:${pct}%"></span></div>
          ${lines}
        </div>
        <div class="amt">${this._money(c.total)}</div>
      </div>`;
    }).join("");
    return `<div class="stats">
          <div><div class="muted small">Paid</div><div class="big">${this._money(s.paid)}</div></div>
          <div><div class="muted small">${past ? "Unpaid" : "Upcoming"}</div><div class="big">${
            this._money(s.upcoming)}</div></div>
          <div><div class="muted small">Total</div><div class="big">${this._money(s.total)}</div></div>
        </div>
        <div class="meter" title="${paidPct}% paid"><span style="width:${paidPct}%"></span></div>
        <div class="muted small meter-label">${paidPct}% paid</div>
        ${rows}
        ${s.unpriced ? `<p class="muted small note">${s.unpriced} due date${
          s.unpriced === 1 ? "" : "s"} without an amount ${
          s.unpriced === 1 ? "isn't" : "aren't"} included in the totals.</p>` : ""}`;
  }

  // The Total chip (plus Jan … Dec once "Show months" is on), then the
  // selected one's breakdown.
  _yearBody(y) {
    const showMonths = this._showMonths.has(y.year);
    const sel = showMonths ? (this._yearSel[y.year] ?? -1) : -1;
    const options = [[-1, "Total", y.total]];
    if (showMonths) {
      y.months.forEach((m, i) => options.push([i, this._monthLabel(m.start, "short"), m.total]));
    }
    const chips = options.map(([i, label, total]) => `<button class="chip ${i === sel ? "sel" : ""}"
          data-ysel="${y.year}:${i}" aria-pressed="${i === sel}">
        <span>${esc(label)}</span><b>${total ? this._money(total) : "—"}</b>
      </button>`).join("");
    const s = sel < 0 ? y : y.months[sel];
    const label = sel < 0 ? String(y.year) : this._monthLabel(s.start);
    return `<div class="chips">${chips}</div>
      <div class="selbar">
        <span class="selhead">${sel < 0 ? `All of ${y.year}` : esc(label)}</span>
        <button class="link monthstoggle" data-monthstoggle="${y.year}" aria-expanded="${showMonths}">
          ${showMonths ? "Hide months" : "Show months"}
          ${this._icon(showMonths ? "mdi:chevron-up" : "mdi:chevron-down", "tiny")}</button>
      </div>
      ${this._breakdown(s, { emptyText: `No bills due in ${label}.`, showBills: sel >= 0 })}`;
  }

  _costs_html() {
    if (!this._costs) return "";
    const { month, year } = this._costs;
    const prev = this._costs.previous_years || [];
    const yearCard = (y) => {
      const open = this._openYears.has(y.year);
      return `<div class="card yearcard">
        <button class="yearhead" data-yeartoggle="${y.year}" aria-expanded="${open}">
          ${this._icon(open ? "mdi:chevron-down" : "mdi:chevron-right", "lead")}
          <span class="grow name">${y.year}</span>
          <span class="amt">${this._money(y.total)}</span>
        </button>
        ${open ? `<div class="yearbody">${this._yearBody(y)}</div>` : ""}
      </div>`;
    };
    return `
      <h2>This month <span class="muted h-sub">· ${esc(this._monthLabel(month.start))}</span></h2>
      <div class="card">${this._breakdown(month, { emptyText: "No bills due this month." })}</div>
      <h2>This year</h2>
      ${yearCard(year)}
      <h2>Previous years</h2>
      ${prev.length ? prev.map(yearCard).join("") : `<div class="card"><p class="muted">
        No historical yearly data to display here yet. Years show up once they have
        payments.</p></div>`}`;
  }

  // ---------- payment history ----------

  async _openHistory(id) {
    this._history = { id, data: null, error: "", showAll: false };
    this._open("history", id);
    try {
      const data = await this._call("bill_history", { bill: id });
      if (this._history && this._history.id === id) this._history.data = data;
    } catch (e) {
      if (this._history && this._history.id === id) this._history.error = e.message || String(e);
    }
    if (this._form && this._form.kind === "history" && this._form.id === id) this._render();
  }

  _arrow(change, pct) {
    if (change === null || change === undefined) return "";
    if (Math.abs(pct ?? 0) < 2 && Math.abs(change) < 0.005) return "same as before";
    const sign = change > 0 ? "▲" : change < 0 ? "▼" : "=";
    return `${sign} ${this._money(Math.abs(change))}${pct !== null && pct !== undefined ? ` (${Math.abs(pct)}%)` : ""}`;
  }

  _trendWords(t) {
    if (!t) return null;
    return { up: "Going up", down: "Going down", steady: "Steady" }[t.direction];
  }

  // Clean axis maximum: 1, 2, 2.5 or 5 times a power of ten.
  _niceMax(v) {
    if (!(v > 0)) return 1;
    const mag = Math.pow(10, Math.floor(Math.log10(v)));
    for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * mag) return m * mag;
    return 10 * mag;
  }

  _axisMoney(n, max) {
    const cur = (this._hass && this._hass.config.currency) || "USD";
    return new Intl.NumberFormat(undefined, {
      style: "currency", currency: cur, maximumFractionDigits: max >= 10 ? 0 : 2,
    }).format(n);
  }

  // Column chart of the latest payments, oldest on the left. Plain HTML so
  // text stays readable at any width; the payments list below is the table view.
  _historyChart(rows, estimate) {
    const MAX_BARS = 24;
    const shown = rows.slice(-MAX_BARS);
    const top = this._niceMax(Math.max(...shown.map((p) => p.amount_paid), estimate || 0));
    const pct = (v) => Math.max(0, Math.min(100, (v / top) * 100));
    const ticks = [0, top / 2, top].map((t) => `<div class="gl" style="bottom:${pct(t)}%">
        <span>${this._axisMoney(t, top)}</span></div>`).join("");
    const est = estimate ? `<div class="est" style="bottom:${pct(estimate)}%">
        <span>estimate ${this._money(estimate)}</span></div>` : "";
    const cols = shown.map((p, i) => {
      const label = this._monthLabel(p.due_date) + " · " + this._money(p.amount_paid);
      const last = i === shown.length - 1;
      return `<button class="col${last ? " on" : ""}" data-tip="${esc(label)}" aria-label="${esc(label)}"
          style="--h:${pct(p.amount_paid)}%">
          ${last ? `<span class="cap">${this._money(p.amount_paid)}</span>` : ""}
          <span class="bar"></span></button>`;
    }).join("");
    const first = this._monthLabel(shown[0].due_date);
    const lastLabel = this._monthLabel(shown[shown.length - 1].due_date);
    return `<div class="chart">
        <div class="plot">${ticks}${est}<div class="cols">${cols}</div></div>
        <div class="xlabels"><span>${esc(first)}</span><span>${
          rows.length > MAX_BARS ? `last ${MAX_BARS} payments` : ""}</span><span>${esc(lastLabel)}</span></div>
        <div class="muted small charttip" id="charttip">${esc(
          this._monthLabel(shown[shown.length - 1].due_date) + " · " +
          this._money(shown[shown.length - 1].amount_paid))}</div>
      </div>`;
  }

  _historyView() {
    const h = this._history;
    const b = h && h.data ? h.data.bill : (this._bill(h && h.id) || this._retiredBill(h && h.id));
    const cat = b && this._category(b.category_id);
    const sub = b ? [cat ? cat.name : "Uncategorized", this._repeats(b),
      b.active ? `estimate ${this._money(b.amount)}` : "retired"].join(" · ") : "";
    const actions = `<div class="actions">
        <button type="button" class="secondary" data-cancel>Close</button>
        ${b && b.active ? `<button type="button" class="secondary" data-edit="${esc(b.id)}">Edit</button>
          <button type="button" data-pay="${esc(b.id)}">Pay</button>` : ""}
        ${b && !b.active ? `<button type="button" class="secondary" data-restore="${esc(b.id)}">Restore</button>` : ""}
      </div>`;
    const head = `<div class="histhead">
        ${this._billIcon(b)}
        <div class="grow">
          <h2>${esc(b ? b.name : "Payment history")}</h2>
          <div class="muted small">${esc(sub)}</div>
        </div>
      </div>`;
    let body;
    if (h.error) body = `<div class="err">${esc(h.error)}</div>`;
    else if (!h.data) body = `<p class="muted">Loading payment history…</p>`;
    else body = this._historyBody(h.data, b);
    return `<div class="card" id="history">${head}${body}${actions}</div>`;
  }

  _historyBody(data, b) {
    const st = data.stats;
    // Oldest first for the chart and the change-from-previous column.
    const rows = data.payments.filter((p) => p.amount_paid !== null && p.amount_paid !== undefined)
      .slice().reverse();
    if (!data.payments.length) {
      return `<p class="muted">No payments recorded yet. They'll show here once you pay this bill.</p>`;
    }
    const tiles = [
      ["Last payment", st.last !== null ? this._money(st.last) : "—",
        st.change !== null ? this._arrow(st.change, st.change_pct) + " vs previous" : "first payment"],
      ["Average", st.average !== null ? this._money(st.average) : "—",
        `over ${st.count} payment${st.count === 1 ? "" : "s"}`],
      ["Lowest – highest", st.min !== null ? `${this._money(st.min)} – ${this._money(st.max)}` : "—",
        st.first_due ? `since ${this._monthLabel(st.first_due)}` : ""],
      ["Trend", this._trendWords(st.trend) || "Not enough yet",
        st.trend ? `${st.trend.pct > 0 ? "+" : ""}${st.trend.pct ?? 0}% · last ${st.trend.window} vs ${
          st.trend.window} before` : "needs 4 payments"],
    ].map(([label, value, delta]) => `<div class="tile">
        <div class="muted small">${label}</div>
        <div class="tilev">${esc(value)}</div>
        <div class="muted small">${esc(delta)}</div>
      </div>`).join("");
    const yoy = st.year_over_year ? `<p class="muted small yoy">Last 12 months averaged
        <b>${this._money(st.year_over_year.recent_avg)}</b> a payment vs
        ${this._money(st.year_over_year.prior_avg)} the 12 months before
        (${this._arrow(st.year_over_year.recent_avg - st.year_over_year.prior_avg,
          st.year_over_year.pct)}).</p>` : "";

    // Change from the previous payment, keyed by payment id.
    const delta = {};
    rows.forEach((p, i) => {
      if (i === 0) return;
      const d = p.amount_paid - rows[i - 1].amount_paid;
      delta[p.id] = Math.abs(d) < 0.005 ? "=" : `${d > 0 ? "▲" : "▼"} ${this._money(Math.abs(d))}`;
    });
    const LIMIT = 4;  // the chart above still shows the full range
    const list = this._history.showAll ? data.payments : data.payments.slice(0, LIMIT);
    const items = list.map((p) => `<div class="row hist">
        <div class="grow">
          <div class="name">${esc(this._monthLabel(p.due_date))}</div>
          <div class="muted small">due ${esc(p.due_date)} · paid ${esc(p.paid_date)}${
            p.confirmation ? " · #" + esc(p.confirmation) : ""}${p.note ? " · " + esc(p.note) : ""}</div>
        </div>
        <div class="delta muted small">${delta[p.id] || ""}</div>
        <div class="amt">${this._money(p.amount_paid)}</div>
      </div>`).join("");
    const more = data.payments.length > LIMIT
      ? `<button class="link showmore" id="hist-all">${this._history.showAll
          ? "Show fewer" : `Show all ${data.payments.length} payments`}</button>` : "";
    return `<div class="tiles">${tiles}</div>
      ${yoy}
      ${rows.length ? this._historyChart(rows, b && b.active ? b.amount : null) : ""}
      <h3>Payments</h3>
      ${items}${more}`;
  }

  // ---------- forms ----------

  _payForm(b) {
    const w = this._when(b.next_due);
    const current = b.amount === null || b.amount === undefined
      ? "no estimate yet" : `currently ${this._money(b.amount)}`;
    return `<form id="payform" class="card">
      <h2>Pay ${esc(b.name)}</h2>
      <p class="muted ${w.cls}">Due ${esc(b.next_due)} · ${w.text}</p>
      <div class="err" data-formerr hidden></div>
      <label>Amount paid
        <input name="amount" type="number" step="0.01" min="0" inputmode="decimal"
               value="${b.amount ?? ""}" placeholder="0.00" autofocus></label>
      <label class="check" id="estrow" hidden>
        <input name="update_amount" type="checkbox">
        <span>Use this as the new estimate <span class="muted">(${esc(current)})</span></span></label>
      <label>Date paid
        <input name="paid_date" type="date" value="${todayIso()}" required></label>
      <label>Confirmation number (optional)
        <input name="confirmation" type="text"></label>
      <label>Note (optional)
        <input name="note" type="text"></label>
      <div class="actions">
        <button type="button" class="secondary" data-cancel>Cancel</button>
        <button type="submit">Record payment</button>
      </div>
    </form>`;
  }

  _restoreForm(b) {
    const ended = !b.restore_due;
    return `<form id="restoreform" class="card">
      <h2>Restore ${esc(b.name)}</h2>
      <div class="err" data-formerr hidden></div>
      <p class="muted">${ended
        ? "Its schedule has no dates left, so pick when it's next due."
        : "It goes back on the list with reminders. Check the next due date."}</p>
      <label>Next due
        <input name="due_date" type="date" required value="${esc(b.restore_due ?? "")}"></label>
      ${b.end_date ? `<p class="muted small">If the end date (${esc(b.end_date)}) is before this,
        it's removed.</p>` : ""}
      <div class="actions">
        <button type="button" class="secondary" data-cancel>Cancel</button>
        <button type="submit">Restore bill</button>
      </div>
    </form>`;
  }

  _billForm(b) {
    const edit = !!b;
    const v = b || { ...NEW_BILL, next_due: todayIso() };
    const opts = FREQUENCIES.map(([val, label]) =>
      `<option value="${val}" ${v.frequency === val ? "selected" : ""}>${label}</option>`
    ).join("");
    const catOpts = [`<option value="">Uncategorized</option>`].concat(
      this._categories.map((c) =>
        `<option value="${esc(c.id)}" ${v.category_id === c.id ? "selected" : ""}>${esc(c.name)}</option>`)
    ).join("");
    return `<form id="billform" class="card" novalidate>
      <h2>${edit ? "Edit " + esc(v.name) : "Add a bill"}</h2>
      ${edit ? `<button type="button" class="link histlink" data-history="${esc(v.id)}">
        ${this._icon("mdi:chart-bar", "tiny")} Payment history</button>` : ""}
      <div class="err" data-formerr hidden></div>
      <label>Name
        <input name="name" type="text" required autocomplete="off" value="${esc(v.name)}"
               placeholder="e.g. Phone" ${edit ? "" : "autofocus"}></label>
      <label>Category
        <span class="inline">
          <span id="caticon">${this._billIcon(v)}</span>
          <select name="category">${catOpts}</select>
        </span></label>
      ${this._categories.length ? "" : `<p class="muted small hint">Make categories with the
        <b>Categories</b> button at the top.</p>`}
      <div class="two">
        <label>Amount
          <input name="amount" type="number" step="0.01" min="0" inputmode="decimal"
                 value="${v.amount ?? ""}" placeholder="Varies"></label>
        <label>${edit ? "Next due" : "First due date"}
          <input name="due_date" type="date" required value="${esc(v.next_due)}"></label>
      </div>
      <div class="two">
        <label>Repeats
          <select name="frequency">${opts}</select></label>
        <label data-repeat>Every
          <span class="inline">
            <input name="interval" type="number" min="1" step="1" inputmode="numeric"
                   value="${v.interval}">
            <span id="unit"></span>
          </span></label>
      </div>
      <label data-repeat>Ends (optional)
        <input name="end_date" type="date" value="${esc(v.end_date ?? "")}"></label>
      <label>Remind me this many days before
        <input name="remind_days_before" type="number" min="0" step="1" inputmode="numeric"
               value="${v.remind_days_before}"></label>
      <label class="check">
        <input name="autopay" type="checkbox" ${v.autopay ? "checked" : ""}>
        <span>Autopay</span></label>
      <label>Payment website (optional)
        <input name="biller_url" type="text" inputmode="url" autocomplete="off"
               placeholder="https://" value="${esc(v.biller_url ?? "")}"></label>
      <label>Notes (optional)
        <input name="notes" type="text" value="${esc(v.notes ?? "")}"></label>
      ${edit ? `<p class="muted small">Changing the due date or how often it repeats
        restarts the schedule from the new due date.</p>` : ""}
      <div class="actions">
        ${edit ? `<button type="button" class="link danger-text" id="retire">Retire…</button>
                  <span class="spacer"></span>` : ""}
        <button type="button" class="secondary" data-cancel>Cancel</button>
        <button type="submit">${edit ? "Save" : "Add bill"}</button>
      </div>
      ${edit ? `<div id="confirm" class="confirm" hidden>
        <p>Retire <b>${esc(v.name)}</b>? It disappears from the list and reminders stop.
           Its payment history is kept.</p>
        <div class="actions">
          <button type="button" class="secondary" id="keep">Keep it</button>
          <button type="button" class="danger" id="doretire">Retire bill</button>
        </div>
      </div>` : ""}
    </form>`;
  }

  _categoriesView() {
    const rows = this._categories.length
      ? this._categories.map((c) => `<div class="row">
          ${this._icon(c.icon, "lead")}
          <div class="grow">
            <div class="name">${esc(c.name)}</div>
            <div class="muted small">${c.bill_count} active bill${c.bill_count === 1 ? "" : "s"}</div>
          </div>
          <div class="btns">
            <button class="secondary" data-editcat="${esc(c.id)}">Edit</button>
          </div>
        </div>`).join("")
      : `<p class="muted">No categories yet. Add one, then pick it when you add or edit a bill.</p>`;
    return `<div class="card">
      <h2>Categories</h2>
      ${rows}
      <div class="actions">
        <button type="button" class="secondary" data-cancel>Done</button>
        <button type="button" id="newcat">New category</button>
      </div>
    </div>`;
  }

  _categoryForm(c) {
    const edit = !!c;
    const icon = c ? c.icon : DEFAULT_CATEGORY_ICON;
    const grid = SUGGESTED_ICONS.map((i) =>
      `<button type="button" class="iconbtn ${i === icon ? "sel" : ""}" data-icon="${i}"
               title="${i}" aria-label="${i}">${this._icon(i)}</button>`).join("");
    return `<form id="catform" class="card" novalidate>
      <h2>${edit ? "Edit category" : "New category"}</h2>
      <div class="err" data-formerr hidden></div>
      <label>Name
        <input name="name" type="text" required autocomplete="off" value="${esc(c ? c.name : "")}"
               placeholder="e.g. Utilities" ${edit ? "" : "autofocus"}></label>
      <label>Icon
        <span class="inline">
          <span id="iconpreview">${this._icon(icon, "lead")}</span>
          <input name="icon" type="text" autocomplete="off" autocapitalize="off"
                 spellcheck="false" value="${esc(icon)}" placeholder="mdi:tag">
        </span></label>
      <p class="muted small hint">Tap one below, or type any icon name from
        Home Assistant (e.g. <code>mdi:lightning-bolt</code>).</p>
      <div class="icongrid">${grid}</div>
      <div class="actions">
        ${edit ? `<button type="button" class="link danger-text" id="delcat">Delete…</button>
                  <span class="spacer"></span>` : ""}
        <button type="button" class="secondary" id="catback">Cancel</button>
        <button type="submit">${edit ? "Save" : "Add category"}</button>
      </div>
      ${edit ? `<div id="confirm" class="confirm" hidden>
        <p>Delete <b>${esc(c.name)}</b>? ${c.bill_count
          ? `Its ${c.bill_count} bill${c.bill_count === 1 ? "" : "s"} become uncategorized.`
          : "No bills use it."}</p>
        <div class="actions">
          <button type="button" class="secondary" id="keep">Keep it</button>
          <button type="button" class="danger" id="dodelete">Delete category</button>
        </div>
      </div>` : ""}
    </form>`;
  }

  // Read the bill form into service fields. Returns { data } or { error }.
  _readBillForm(form) {
    const f = form.elements;
    const name = f.name.value.trim();
    if (!name) return { error: "Give the bill a name." };
    if (!f.due_date.value) return { error: "Pick a due date." };
    const frequency = f.frequency.value;
    const interval = parseInt(f.interval.value, 10);
    if (frequency !== "once" && !(interval >= 1)) {
      return { error: "“Every” must be 1 or more." };
    }
    const remind = parseInt(f.remind_days_before.value, 10);
    if (!(remind >= 0)) return { error: "Reminder days must be 0 or more." };
    let amount = null;
    if (f.amount.value !== "") {
      amount = parseFloat(f.amount.value);
      if (!(amount >= 0)) return { error: "Amount must be 0 or more." };
    }
    const end = frequency === "once" ? null : (f.end_date.value || null);
    if (end && end < f.due_date.value) {
      return { error: "The end date can't be before the due date." };
    }
    let url = f.biller_url.value.trim() || null;
    if (url && !/^[a-z][a-z0-9+.-]*:/i.test(url)) url = "https://" + url;
    return {
      data: {
        name,
        category: f.category.value || null,
        amount,
        due_date: f.due_date.value,
        frequency,
        interval: frequency === "once" ? 1 : interval,
        end_date: end,
        remind_days_before: remind,
        autopay: f.autopay.checked,
        biller_url: url,
        notes: f.notes.value.trim() || null,
      },
    };
  }

  // ---------- render ----------

  _render() {
    const k = this._form && this._form.kind;
    const id = this._form && this._form.id;
    let b = null;
    if (id && k === "restore") b = this._retiredBill(id);
    else if (id && k === "category") b = this._category(id);
    else if (id) b = this._bill(id);
    let formHtml = "";
    if (k === "restore" && b) formHtml = this._restoreForm(b);
    else if (k === "pay" && b) formHtml = this._payForm(b);
    else if (k === "edit" && b) formHtml = this._billForm(b);
    else if (k === "add") formHtml = this._billForm(null);
    else if (k === "categories") formHtml = this._categoriesView();
    else if (k === "category") formHtml = this._categoryForm(b);
    else if (k === "history") formHtml = this._historyView();

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; background: var(--primary-background-color); min-height: 100vh; }
        [hidden] { display: none !important; }
        .wrap { max-width: 640px; margin: 0 auto; padding: 16px; color: var(--primary-text-color); }
        header { display: flex; align-items: center; gap: 8px; }
        header h1 { flex: 1; }
        h1 { font-size: 24px; margin: 8px 0 16px; }
        h2 { font-size: 18px; margin: 24px 0 8px; }
        .h-sub { font-size: 15px; font-weight: 400; }
        .card { background: var(--card-background-color); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        .card h2 { margin-top: 0; }
        .row { display: flex; align-items: center; gap: 12px; padding: 10px 0;
               border-bottom: 1px solid var(--divider-color); }
        .row:last-child { border-bottom: 0; }
        .grow { flex: 1; min-width: 0; }
        .name { font-weight: 500; overflow-wrap: anywhere; }
        .amt { white-space: nowrap; }
        .btns { display: flex; gap: 6px; }
        .btns button { padding: 8px 12px; }
        ha-icon { --mdc-icon-size: 22px; color: var(--state-icon-color, var(--secondary-text-color)); }
        ha-icon.lead { flex: none; }
        .muted { color: var(--secondary-text-color); font-size: 14px; }
        .small { font-size: 13px; }
        .hint { margin: -6px 0 8px; }
        .late { color: var(--error-color); }
        .soon { color: var(--warning-color); }
        .tag { font-size: 11px; border: 1px solid var(--divider-color); border-radius: 8px; padding: 1px 6px; font-weight: 400; }
        label { display: block; margin: 12px 0; font-size: 14px; color: var(--secondary-text-color); }
        input, select { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 10px;
                font-size: 16px; border-radius: 8px; border: 1px solid var(--divider-color);
                background: var(--card-background-color); color: var(--primary-text-color); font-family: inherit; }
        label.check { display: flex; align-items: center; gap: 10px; color: var(--primary-text-color); font-size: 15px; }
        label.check input { width: 20px; height: 20px; margin: 0; flex: none; }
        .two { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
        .two label { min-width: 0; }
        .inline { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
        .inline input, .inline select { margin-top: 0; }
        .inline input[name="interval"] { width: 5em; flex: none; }
        .inline span { color: var(--primary-text-color); }
        .inline > span:first-child { display: flex; }
        .icongrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(44px, 1fr)); gap: 6px; }
        .iconbtn { background: transparent; border: 1px solid var(--divider-color); padding: 8px;
                   display: flex; align-items: center; justify-content: center; }
        .iconbtn.sel { border: 2px solid var(--primary-color); padding: 7px; }
        .iconbtn.sel ha-icon { color: var(--primary-color); }
        code { font-size: 12px; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
        .big { font-size: 20px; font-weight: 500; white-space: nowrap; }
        .meter, .minibar { background: var(--divider-color); border-radius: 4px; overflow: hidden; }
        .meter { height: 8px; margin: 12px 0 4px; }
        .meter-label { text-align: right; margin-bottom: 4px; }
        .showmore { width: 100%; margin-top: 4px; color: var(--primary-color); }
        .chips { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
                 gap: 6px; margin-bottom: 14px; }
        .chip { background: transparent; color: var(--primary-text-color); text-align: left;
                border: 1px solid var(--divider-color); padding: 6px 8px;
                display: flex; flex-direction: column; gap: 2px; }
        .chip span { font-size: 12px; color: var(--secondary-text-color); }
        .chip b { font-size: 13px; font-weight: 500; white-space: nowrap; }
        .chip.sel { border: 2px solid var(--primary-color); padding: 5px 7px; }
        .chip.sel span { color: var(--primary-color); }
        .selbar { display: flex; align-items: center; justify-content: space-between;
                  gap: 8px; margin: -6px 0 8px; }
        .selhead { font-weight: 500; }
        .monthstoggle { display: flex; align-items: center; gap: 2px; color: var(--primary-color);
                        white-space: nowrap; }
        ha-icon.tiny { --mdc-icon-size: 18px; color: var(--primary-color); }
        .yearhead { width: 100%; display: flex; align-items: center; gap: 12px; padding: 0;
                    background: transparent; color: var(--primary-text-color);
                    font-size: 16px; text-align: left; }
        .yearbody { margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--divider-color); }
        .billlines { margin-top: 8px; }
        .billline { display: flex; justify-content: space-between; gap: 8px; padding: 2px 0;
                    font-size: 13px; color: var(--secondary-text-color); }
        .billline > span:first-child { color: var(--primary-text-color); overflow-wrap: anywhere; }
        .billline > span:last-child { text-align: right; }
        button.rowlink { background: transparent; color: inherit; padding: 0; border: 0;
                         text-align: left; font: inherit; border-radius: 4px; }
        button.rowlink:hover .name { text-decoration: underline; }
        .histlink { display: flex; align-items: center; gap: 4px; color: var(--primary-color);
                    margin: -4px 0 4px; padding-left: 0; }
        .histhead { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
        .histhead h2 { margin: 0; }
        h3 { font-size: 15px; margin: 20px 0 4px; }
        .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; }
        .tile { min-width: 0; }
        .tilev { font-size: 18px; font-weight: 500; overflow-wrap: anywhere; }
        .yoy { margin: 12px 0 0; }
        .yoy b { color: var(--primary-text-color); font-weight: 500; }
        .chart { margin-top: 16px; }
        .plot { position: relative; height: 160px; margin-top: 20px; }
        .gl { position: absolute; left: 0; right: 0; border-top: 1px solid var(--divider-color); }
        .gl span { position: absolute; left: 0; width: 44px; transform: translateY(-50%);
                   background: var(--card-background-color); font-size: 11px;
                   color: var(--secondary-text-color); }
        .est { position: absolute; left: 48px; right: 0; border-top: 1px dashed var(--secondary-text-color); }
        .est span { position: absolute; left: 4px; bottom: 2px; font-size: 11px; z-index: 1;
                    color: var(--secondary-text-color); background: var(--card-background-color);
                    padding: 0 2px; }
        .cols { position: absolute; left: 48px; right: 0; top: 0; bottom: 0;
                display: flex; align-items: flex-end; gap: 2px; }
        .col { flex: 1; min-width: 0; height: 100%; position: relative; padding: 0;
               background: transparent; border-radius: 0; display: flex;
               align-items: flex-end; justify-content: center; }
        .col .bar { display: block; width: 100%; max-width: 24px; height: var(--h);
                    min-height: 2px; background: var(--primary-color); opacity: .75;
                    border-radius: 4px 4px 0 0; }
        .col.on .bar, .col:hover .bar, .col:focus-visible .bar { opacity: 1; }
        .col .cap { position: absolute; bottom: calc(var(--h) + 2px); font-size: 11px;
                    white-space: nowrap; color: var(--primary-text-color); right: 0; }
        .xlabels { display: flex; justify-content: space-between; margin-left: 48px;
                   font-size: 11px; color: var(--secondary-text-color); padding-top: 4px; }
        .charttip { margin-top: 6px; min-height: 18px; }
        .row.hist .delta { white-space: nowrap; text-align: right; min-width: 64px; }
        .minibar { height: 4px; margin-top: 6px; }
        .meter span, .minibar span { display: block; height: 100%; background: var(--primary-color); }
        .row.cat .amt { font-weight: 500; }
        .note { margin: 12px 0 0; }
        button { font-size: 14px; padding: 8px 16px; border-radius: 8px; border: 0; cursor: pointer;
                 background: var(--primary-color); color: var(--text-primary-color, #fff); font-family: inherit; }
        button.secondary { background: transparent; color: var(--primary-text-color);
                           border: 1px solid var(--divider-color); }
        button.danger { background: var(--error-color); color: #fff; }
        button.link { background: transparent; padding: 8px 4px; }
        .danger-text { color: var(--error-color); }
        button:disabled { opacity: .5; cursor: default; }
        .actions { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 16px; }
        .spacer { flex: 1; }
        .section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
        .section-head button.link { color: var(--primary-color); }
        .confirm { margin-top: 16px; padding: 12px; border-radius: 8px;
                   border: 1px solid var(--error-color); }
        .confirm p { margin: 0; }
        .confirm .actions { margin-top: 12px; }
        .ok, .err { padding: 10px 12px; border-radius: 8px; margin-bottom: 12px; }
        .ok { background: var(--success-color, #2e7d32); color: #fff; transition: opacity .4s; }
        .ok.hide { opacity: 0; }
        .err { background: var(--error-color); color: #fff; }
        @media (max-width: 420px) {
          .two { grid-template-columns: 1fr; }
          .big { font-size: 17px; }
        }
      </style>
      <div class="wrap">
        <header>
          <h1>Bills</h1>
          ${k === "categories" || k === "category" ? "" :
            `<button class="secondary" id="cats">Categories</button>`}
          ${k === "add" ? "" : `<button id="add">Add bill</button>`}
        </header>
        ${this._error ? `<div class="err">${esc(this._error)}</div>` : ""}
        ${this._msg ? `<div class="ok">${esc(this._msg)}</div>` : ""}
        ${formHtml}
        <h2>Upcoming</h2>
        <div class="card">${this._billsList()}</div>
        ${this._costs_html()}
        <h2>Recent payments</h2>
        <div class="card">${this._paymentsList()}</div>
        ${this._retiredSection()}
      </div>`;
    this._bind(k, b);
  }

  _bind(kind, item) {
    const root = this.shadowRoot;
    const on = (id, fn) => { const el = root.getElementById(id); if (el) el.addEventListener("click", fn); };
    on("add", () => this._open("add"));
    on("cats", () => this._open("categories"));
    on("newcat", () => this._open("category"));
    on("toggle-payments", () => {
      this._showMorePayments = !this._showMorePayments;
      this._render();
    });
    on("toggle-bills", () => {
      this._showAllBills = !this._showAllBills;
      this._render();
    });
    on("toggle-retired", () => {
      this._showRetired = !this._showRetired;
      this._render();
    });
    const each = (attr, fn) => root.querySelectorAll(`[data-${attr}]`).forEach((btn) =>
      btn.addEventListener("click", () => fn(btn.dataset[attr])));
    each("pay", (id) => this._open("pay", id));
    each("edit", (id) => this._open("edit", id));
    each("restore", (id) => this._open("restore", id));
    each("history", (id) => this._openHistory(id));
    on("hist-all", () => {
      this._history.showAll = !this._history.showAll;
      this._render();
    });
    root.querySelectorAll("[data-tip]").forEach((col) => {
      const show = () => {
        const tip = root.getElementById("charttip");
        if (tip) tip.textContent = col.dataset.tip;
        root.querySelectorAll(".col.on").forEach((c) => c.classList.remove("on"));
        col.classList.add("on");
      };
      col.addEventListener("mouseenter", show);
      col.addEventListener("focus", show);
      col.addEventListener("click", show);
    });
    each("editcat", (id) => this._open("category", id));
    each("ysel", (v) => {
      const [year, idx] = v.split(":").map(Number);
      this._yearSel[year] = idx;
      this._render();
    });
    each("monthstoggle", (v) => {
      const year = Number(v);
      if (this._showMonths.has(year)) {
        this._showMonths.delete(year);
        this._yearSel[year] = -1;  // back to the Total view
      } else {
        this._showMonths.add(year);
      }
      this._render();
    });
    each("yeartoggle", (v) => {
      const year = Number(v);
      if (this._openYears.has(year)) this._openYears.delete(year);
      else this._openYears.add(year);
      this._render();
    });
    root.querySelectorAll("[data-cancel]").forEach((btn) =>
      btn.addEventListener("click", () => this._close()));

    if (kind === "restore" && item) this._bindRestore(root.getElementById("restoreform"), item);
    if (kind === "pay" && item) this._bindPay(root.getElementById("payform"), item);
    if (kind === "add" || (kind === "edit" && item)) {
      this._bindBill(root.getElementById("billform"), kind === "edit" ? item : null);
    }
    if (kind === "category") this._bindCategory(root.getElementById("catform"), item);
  }

  // Run a service from a form; on failure keep the form (and what was typed)
  // and show the error inside it. `next` is the form to show afterwards.
  async _submit(form, service, data, onDone, next = null) {
    const btn = form.querySelector('button[type="submit"]');
    const errEl = form.querySelector("[data-formerr]");
    if (btn) btn.disabled = true;
    errEl.hidden = true;
    try {
      const r = await this._call(service, data);
      this._flash(onDone(r));
      this._close(false);
      this._form = next;
      await this._refresh();
    } catch (e) {
      if (btn) btn.disabled = false;
      this._formError(form, e.message || String(e));
    }
  }

  _formError(form, msg) {
    const errEl = form.querySelector("[data-formerr]");
    errEl.textContent = msg;
    errEl.hidden = false;
    errEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  // Shared "are you sure?" box: `trigger` reveals #confirm, #keep hides it,
  // `go` runs the action.
  _bindConfirm(form, triggerId, goId, action) {
    const confirm = form.querySelector("#confirm");
    const trigger = form.querySelector("#" + triggerId);
    trigger.addEventListener("click", () => {
      confirm.hidden = false;
      trigger.disabled = true;
      confirm.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    form.querySelector("#keep").addEventListener("click", () => {
      confirm.hidden = true;
      trigger.disabled = false;
    });
    form.querySelector("#" + goId).addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      try {
        await action();
      } catch (e) {
        ev.target.disabled = false;
        this._formError(form, e.message || String(e));
      }
    });
  }

  _bindRestore(form, b) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const due = form.elements.due_date.value;
      if (!due) return this._formError(form, "Pick a due date.");
      this._submit(form, "restore_bill", { bill: b.id, due_date: due }, (r) =>
        `Restored ${b.name}. Next due ${r.next_due}.`);
    });
  }

  _bindPay(form, b) {
    const f = form.elements;
    const estRow = form.querySelector("#estrow");
    const syncEst = () => {
      const v = f.amount.value;
      estRow.hidden = v === "" || parseFloat(v) === b.amount;
      if (estRow.hidden) f.update_amount.checked = false;
    };
    f.amount.addEventListener("input", syncEst);
    syncEst();

    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const data = { bill: b.id, paid_date: f.paid_date.value };
      if (f.amount.value !== "") data.amount = parseFloat(f.amount.value);
      if (f.confirmation.value.trim()) data.confirmation = f.confirmation.value.trim();
      if (f.note.value.trim()) data.note = f.note.value.trim();
      if (f.update_amount.checked && data.amount !== undefined) data.update_amount = true;
      this._submit(form, "mark_paid", data, (r) =>
        `Recorded ${b.name}.` +
        (r.next_due ? ` Next due ${r.next_due}.` : " No further due dates."));
    });
  }

  _bindBill(form, b) {
    const f = form.elements;
    const unit = form.querySelector("#unit");
    const syncRepeat = () => {
      const freq = f.frequency.value;
      form.querySelectorAll("[data-repeat]").forEach((el) => { el.hidden = freq === "once"; });
      if (UNITS[freq]) {
        const n = parseInt(f.interval.value, 10);
        unit.textContent = UNITS[freq] + (n === 1 ? "" : "s");
      }
    };
    f.frequency.addEventListener("change", syncRepeat);
    f.interval.addEventListener("input", syncRepeat);
    syncRepeat();
    f.category.addEventListener("change", () => {
      form.querySelector("#caticon").innerHTML =
        this._billIcon({ category_id: f.category.value || null });
    });

    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const { data, error } = this._readBillForm(form);
      if (error) return this._formError(form, error);

      if (!b) {
        // Leave out empty optional fields when adding.
        const add = Object.fromEntries(
          Object.entries(data).filter(([, v]) => v !== null));
        return this._submit(form, "add_bill", add, (r) =>
          `Added ${data.name}. First due ${r.next_due}.`);
      }

      // Editing: send only what changed (null clears a field).
      const before = {
        name: b.name, category: b.category_id ?? null, amount: b.amount ?? null,
        due_date: b.next_due, frequency: b.frequency, interval: b.interval,
        end_date: b.end_date ?? null, remind_days_before: b.remind_days_before,
        autopay: b.autopay, biller_url: b.biller_url ?? null, notes: b.notes ?? null,
      };
      const changes = {};
      for (const [key, val] of Object.entries(data)) {
        if (val !== before[key]) changes[key] = val;
      }
      if (!Object.keys(changes).length) {
        this._flash("No changes.");
        return this._close();
      }
      this._submit(form, "update_bill", { bill: b.id, ...changes }, (r) =>
        `Saved ${r.bill.name}. Next due ${r.bill.next_due}.`);
    });

    if (b) {
      this._bindConfirm(form, "retire", "doretire", async () => {
        await this._call("retire_bill", { bill: b.id });
        this._flash(`Retired ${b.name}. You can restore it from Retired at the bottom.`);
        this._close(false);
        await this._refresh();
      });
    }
  }

  _bindCategory(form, c) {
    const f = form.elements;
    const preview = form.querySelector("#iconpreview");
    const back = { kind: "categories", id: null };
    const sync = () => {
      const v = f.icon.value.trim();
      preview.innerHTML = this._icon(ICON_RE.test(v) ? v : DEFAULT_CATEGORY_ICON, "lead");
      form.querySelectorAll("[data-icon]").forEach((btn) =>
        btn.classList.toggle("sel", btn.dataset.icon === v));
    };
    f.icon.addEventListener("input", sync);
    form.querySelectorAll("[data-icon]").forEach((btn) =>
      btn.addEventListener("click", () => { f.icon.value = btn.dataset.icon; sync(); }));
    form.querySelector("#catback").addEventListener("click", () => this._open("categories"));

    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const name = f.name.value.trim();
      const icon = f.icon.value.trim().toLowerCase() || DEFAULT_CATEGORY_ICON;
      if (!name) return this._formError(form, "Give the category a name.");
      if (!ICON_RE.test(icon)) {
        return this._formError(form, "Icons look like mdi:home — a prefix, a colon, then the name.");
      }
      if (!c) {
        return this._submit(form, "add_category", { name, icon },
          () => `Added category ${name}.`, back);
      }
      const changes = {};
      if (name !== c.name) changes.name = name;
      if (icon !== c.icon) changes.icon = icon;
      if (!Object.keys(changes).length) return this._open("categories");
      this._submit(form, "update_category", { category: c.id, ...changes },
        () => `Saved category ${name}.`, back);
    });

    if (c) {
      this._bindConfirm(form, "delcat", "dodelete", async () => {
        const r = await this._call("delete_category", { category: c.id });
        this._flash(`Deleted ${c.name}.` + (r.bills_uncategorized
          ? ` ${r.bills_uncategorized} bill${r.bills_uncategorized === 1 ? " is" : "s are"} now uncategorized.`
          : ""));
        this._form = back;
        await this._refresh();
      });
    }
  }
}

// An open tab can load a newer version of this file after HA restarts;
// the element can only be defined once, so a full page reload picks it up.
if (!customElements.get("bills-panel")) {
  customElements.define("bills-panel", BillsPanel);
}
