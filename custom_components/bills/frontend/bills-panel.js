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
};

class BillsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._bills = [];    // active
    this._retired = [];  // retired, most recently retired first
    this._showRetired = false;
    this._payments = [];
    // _form: null, or { kind: "pay" | "edit" | "add" | "restore", id }
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
      const [b, p] = await Promise.all([
        this._call("list_bills", { include_retired: true }),
        this._call("list_payments"),
      ]);
      this._bills = b.bills.filter((x) => x.active);
      this._retired = b.bills.filter((x) => !x.active).sort((x, y) =>
        (y.retired_on || "").localeCompare(x.retired_on || ""));
      this._payments = p.payments.slice(0, 10);
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
    return this._bills.map((b) => {
      const w = this._when(b.next_due);
      return `<div class="row">
        <div class="grow">
          <div class="name">${esc(b.name)}${b.autopay ? ' <span class="tag">autopay</span>' : ""}</div>
          <div class="muted ${w.cls}">${esc(b.next_due)} · ${w.text} · ${esc(this._repeats(b))}</div>
        </div>
        <div class="amt">${this._money(b.amount)}</div>
        <div class="btns">
          <button class="secondary" data-edit="${esc(b.id)}">Edit</button>
          <button data-pay="${esc(b.id)}">Pay</button>
        </div>
      </div>`;
    }).join("");
  }

  _retiredSection() {
    if (!this._retired.length) return "";
    const n = this._retired.length;
    const rows = this._retired.map((b) => `<div class="row">
        <div class="grow">
          <div class="name">${esc(b.name)}</div>
          <div class="muted">${b.retired_on ? "retired " + esc(b.retired_on) + " · " : ""}${
            esc(this._repeats(b))}</div>
        </div>
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
    return this._payments.map((p) => `<div class="row">
        <div class="grow">
          <div class="name">${esc(p.bill_name)}</div>
          <div class="muted">paid ${esc(p.paid_date)} for ${esc(p.due_date)}${
            p.confirmation ? " · #" + esc(p.confirmation) : ""}</div>
        </div>
        <div class="amt">${this._money(p.amount_paid)}</div>
      </div>`).join("");
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
    return `<form id="billform" class="card" novalidate>
      <h2>${edit ? "Edit " + esc(v.name) : "Add a bill"}</h2>
      <div class="err" data-formerr hidden></div>
      <label>Name
        <input name="name" type="text" required autocomplete="off" value="${esc(v.name)}"
               placeholder="e.g. Phone" ${edit ? "" : "autofocus"}></label>
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
    const b = id ? (k === "restore" ? this._retiredBill(id) : this._bill(id)) : null;
    let formHtml = "";
    if (k === "restore" && b) formHtml = this._restoreForm(b);
    else if (k === "pay" && b) formHtml = this._payForm(b);
    else if (k === "edit" && b) formHtml = this._billForm(b);
    else if (k === "add") formHtml = this._billForm(null);

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; background: var(--primary-background-color); min-height: 100vh; }
        [hidden] { display: none !important; }
        .wrap { max-width: 640px; margin: 0 auto; padding: 16px; color: var(--primary-text-color); }
        header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        h1 { font-size: 24px; margin: 8px 0 16px; }
        h2 { font-size: 18px; margin: 24px 0 8px; }
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
        .muted { color: var(--secondary-text-color); font-size: 14px; }
        .small { font-size: 13px; }
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
        .inline input { margin-top: 0; width: 5em; flex: none; }
        .inline span { color: var(--primary-text-color); }
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
        }
      </style>
      <div class="wrap">
        <header>
          <h1>Bills</h1>
          ${k === "add" ? "" : `<button id="add">Add bill</button>`}
        </header>
        ${this._error ? `<div class="err">${esc(this._error)}</div>` : ""}
        ${this._msg ? `<div class="ok">${esc(this._msg)}</div>` : ""}
        ${formHtml}
        <h2>Upcoming</h2>
        <div class="card">${this._billsList()}</div>
        <h2>Recent payments</h2>
        <div class="card">${this._paymentsList()}</div>
        ${this._retiredSection()}
      </div>`;
    this._bind(k, b);
  }

  _bind(kind, bill) {
    const root = this.shadowRoot;
    const add = root.getElementById("add");
    if (add) add.addEventListener("click", () => this._open("add"));
    root.querySelectorAll("[data-pay]").forEach((btn) =>
      btn.addEventListener("click", () => this._open("pay", btn.dataset.pay)));
    root.querySelectorAll("[data-edit]").forEach((btn) =>
      btn.addEventListener("click", () => this._open("edit", btn.dataset.edit)));
    root.querySelectorAll("[data-restore]").forEach((btn) =>
      btn.addEventListener("click", () => this._open("restore", btn.dataset.restore)));
    root.querySelectorAll("[data-cancel]").forEach((btn) =>
      btn.addEventListener("click", () => this._close()));
    const toggle = root.getElementById("toggle-retired");
    if (toggle) {
      toggle.addEventListener("click", () => {
        this._showRetired = !this._showRetired;
        this._render();
      });
    }

    if (kind === "restore" && bill) this._bindRestore(root.getElementById("restoreform"), bill);
    if (kind === "pay" && bill) this._bindPay(root.getElementById("payform"), bill);
    if (kind === "add" || (kind === "edit" && bill)) {
      this._bindBill(root.getElementById("billform"), kind === "edit" ? bill : null);
    }
  }

  // Run a service from a form; on failure keep the form (and what was typed)
  // and show the error inside it.
  async _submit(form, service, data, onDone) {
    const btn = form.querySelector('button[type="submit"]');
    const errEl = form.querySelector("[data-formerr]");
    btn.disabled = true;
    errEl.hidden = true;
    try {
      const r = await this._call(service, data);
      this._flash(onDone(r));
      this._close(false);
      await this._refresh();
    } catch (e) {
      btn.disabled = false;
      this._formError(form, e.message || String(e));
    }
  }

  _formError(form, msg) {
    const errEl = form.querySelector("[data-formerr]");
    errEl.textContent = msg;
    errEl.hidden = false;
    errEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
        name: b.name, amount: b.amount ?? null, due_date: b.next_due,
        frequency: b.frequency, interval: b.interval, end_date: b.end_date ?? null,
        remind_days_before: b.remind_days_before, autopay: b.autopay,
        biller_url: b.biller_url ?? null, notes: b.notes ?? null,
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

    if (!b) return;
    const confirm = form.querySelector("#confirm");
    const retire = form.querySelector("#retire");
    retire.addEventListener("click", () => {
      confirm.hidden = false;
      retire.disabled = true;
      confirm.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    form.querySelector("#keep").addEventListener("click", () => {
      confirm.hidden = true;
      retire.disabled = false;
    });
    form.querySelector("#doretire").addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      try {
        await this._call("retire_bill", { bill: b.id });
        this._flash(`Retired ${b.name}. You can restore it from Retired at the bottom.`);
        this._close(false);
        await this._refresh();
      } catch (e) {
        ev.target.disabled = false;
        this._formError(form, e.message || String(e));
      }
    });
  }
}

// An open tab can load a newer version of this file after HA restarts;
// the element can only be defined once, so a full page reload picks it up.
if (!customElements.get("bills-panel")) {
  customElements.define("bills-panel", BillsPanel);
}
