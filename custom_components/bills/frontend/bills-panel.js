const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));

class BillsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._bills = [];
    this._payments = [];
    this._payId = new URLSearchParams(window.location.search).get("pay");
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
      const [b, p] = await Promise.all([
        this._call("list_bills"),
        this._call("list_payments"),
      ]);
      this._bills = b.bills;
      this._payments = p.payments.slice(0, 10);
      this._error = "";
      if (initial && this._payId && !this._bills.some((x) => x.id === this._payId)) {
        this._flash("That bill isn't active anymore.");
        this._payId = null;
      }
    } catch (e) {
      this._error = e.message || String(e);
    }
    this._render();
  }

  _money(n) {
    if (n === null || n === undefined) return "—";
    const cur = (this._hass && this._hass.config.currency) || "USD";
    return new Intl.NumberFormat(undefined, { style: "currency", currency: cur }).format(n);
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

  _billsList() {
    if (!this._bills.length) return `<p class="muted">No active bills.</p>`;
    return this._bills.map((b) => {
      const w = this._when(b.next_due);
      return `<div class="row">
        <div class="grow">
          <div class="name">${esc(b.name)}${b.autopay ? ' <span class="tag">autopay</span>' : ""}</div>
          <div class="muted ${w.cls}">${esc(b.next_due)} · ${w.text}</div>
        </div>
        <div class="amt">${this._money(b.amount)}</div>
        <button data-pay="${esc(b.id)}">Pay</button>
      </div>`;
    }).join("");
  }

  _paymentsList() {
    if (!this._payments.length) return `<p class="muted">No payments yet.</p>`;
    return this._payments.map((p) => `<div class="row">
        <div class="grow">
          <div class="name">${esc(p.bill_name)}</div>
          <div class="muted">paid ${esc(p.paid_date)} for ${esc(p.due_date)}${
            p.confirmation ? " · #" + esc(p.confirmation) : ""}</div>
        </div>
        <div class="amt">${this._money(p.amount_paid)}</div>
      </div>`).join("");
  }

  _payForm(b) {
    const today = new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD, local time
    const w = this._when(b.next_due);
    return `<form id="payform" class="card">
      <h2>Pay ${esc(b.name)}</h2>
      <p class="muted ${w.cls}">Due ${esc(b.next_due)} · ${w.text}</p>
      <label>Amount paid
        <input name="amount" type="number" step="0.01" min="0" inputmode="decimal"
               value="${b.amount ?? ""}" placeholder="0.00" autofocus></label>
      <label>Date paid
        <input name="paid_date" type="date" value="${today}" required></label>
      <label>Confirmation number (optional)
        <input name="confirmation" type="text"></label>
      <label>Note (optional)
        <input name="note" type="text"></label>
      <div class="actions">
        <button type="button" id="cancel" class="secondary">Cancel</button>
        <button type="submit">Record payment</button>
      </div>
    </form>`;
  }

  _render() {
    const pay = this._bills.find((b) => b.id === this._payId);
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; background: var(--primary-background-color); min-height: 100vh; }
        .wrap { max-width: 640px; margin: 0 auto; padding: 16px; color: var(--primary-text-color); }
        h1 { font-size: 24px; margin: 8px 0 16px; }
        h2 { font-size: 18px; margin: 24px 0 8px; }
        .card { background: var(--card-background-color); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
        .card h2 { margin-top: 0; }
        .row { display: flex; align-items: center; gap: 12px; padding: 10px 0;
               border-bottom: 1px solid var(--divider-color); }
        .grow { flex: 1; min-width: 0; }
        .name { font-weight: 500; }
        .amt { white-space: nowrap; }
        .muted { color: var(--secondary-text-color); font-size: 14px; }
        .late { color: var(--error-color); }
        .soon { color: var(--warning-color); }
        .tag { font-size: 11px; border: 1px solid var(--divider-color); border-radius: 8px; padding: 1px 6px; }
        label { display: block; margin: 12px 0; font-size: 14px; color: var(--secondary-text-color); }
        input { display: block; width: 100%; box-sizing: border-box; margin-top: 4px; padding: 10px;
                font-size: 16px; border-radius: 8px; border: 1px solid var(--divider-color);
                background: var(--card-background-color); color: var(--primary-text-color); }
        button { font-size: 14px; padding: 8px 16px; border-radius: 8px; border: 0; cursor: pointer;
                 background: var(--primary-color); color: var(--text-primary-color, #fff); }
        button.secondary { background: transparent; color: var(--primary-text-color);
                           border: 1px solid var(--divider-color); }
        button:disabled { opacity: .5; }
        .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
        .ok, .err { padding: 10px 12px; border-radius: 8px; margin-bottom: 12px; }
        .ok { background: var(--success-color, #2e7d32); color: #fff; transition: opacity .4s; }
        .ok.hide { opacity: 0; }
        .err { background: var(--error-color); color: #fff; }
      </style>
      <div class="wrap">
        <h1>Bills</h1>
        ${this._error ? `<div class="err">${esc(this._error)}</div>` : ""}
        ${this._msg ? `<div class="ok">${esc(this._msg)}</div>` : ""}
        ${pay ? this._payForm(pay) : ""}
        <h2>Upcoming</h2>
        <div class="card">${this._billsList()}</div>
        <h2>Recent payments</h2>
        <div class="card">${this._paymentsList()}</div>
      </div>`;
    this._bind(pay);
  }

  _bind(pay) {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-pay]").forEach((btn) =>
      btn.addEventListener("click", () => {
        this._payId = btn.dataset.pay;
        this._msg = "";
        this._render();
        window.scrollTo(0, 0);
      })
    );
    const cancel = root.getElementById("cancel");
    if (cancel) {
      cancel.addEventListener("click", () => {
        this._payId = null;
        history.replaceState(null, "", window.location.pathname);
        this._render();
      });
    }
    const form = root.getElementById("payform");
    if (form && pay) {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const f = form.elements;
        const data = { bill: pay.id, paid_date: f.paid_date.value };
        if (f.amount.value !== "") data.amount = parseFloat(f.amount.value);
        if (f.confirmation.value.trim()) data.confirmation = f.confirmation.value.trim();
        if (f.note.value.trim()) data.note = f.note.value.trim();
        form.querySelector('button[type="submit"]').disabled = true;
        try {
          const r = await this._call("mark_paid", data);
          this._flash(`Recorded ${pay.name}.` +
            (r.next_due ? ` Next due ${r.next_due}.` : " No further due dates."));
          this._payId = null;
          history.replaceState(null, "", window.location.pathname);
        } catch (e) {
          this._error = e.message || String(e);
        }
        await this._refresh();
      });
    }
  }
}

customElements.define("bills-panel", BillsPanel);