# Bills & Budget for Home Assistant

Track recurring bills and a daily spending budget in Home Assistant: due dates,
reminders on your phone, payment history, what you're spending by category,
and how much you can spend today. Everything stays on your Home Assistant;
nothing is sent to an outside service.

- **Bills panel** in the sidebar to add, edit, pay, retire and restore bills
- **Categories** with icons, and cost summaries for this month, this year and
  previous years (paid, upcoming, total, by category and by month)
- **Payment history** per bill, with a chart and whether it's going up or down
- **Reminders** each morning for bills that are due soon or overdue, with a
  *Pay bill* button that opens the payment form
- **Sensors and a calendar** for dashboards and phone widgets
- **Daily budget**: how much you can spend today, worked out from your income,
  bills and savings, with over- or underspending carried to the next day
- **Savings** plans and one-off moves, with an all-time total
- **Daily backups** of everything, with one-step restore

## Requirements

Home Assistant 2024.11 or newer.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ryangoderre&repository=ha-bills-budget&category=integration)

Or by hand:

1. In HACS, open the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/ryangoderre/ha-bills-budget` with the type **Integration**.
3. Find **Bills** in HACS, download it, and restart Home Assistant.

### Manual

Copy `custom_components/bills` into your Home Assistant `config/custom_components/`
folder and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Bills.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bills)

Or go to **Settings → Devices & services → Add integration** and search for
**Bills & Budget**. There are no options to fill in. A **Bills & Budget** item
appears in the sidebar, with **Bills**, **Budget** and **Categories** tabs.

## Using the Bills panel

- **Add bill**: name, category, amount (leave it blank if it varies), first due
  date, how often it repeats (weekly, monthly or yearly, every *n*), an optional
  end date, how many days before to remind you, autopay, payment website and notes.
- **Pay**: records a payment for the current due date and moves the bill to its
  next one. If the amount differs from the estimate, tick *Use this as the new
  estimate* to update it.
- **Edit**: changing the due date or how often it repeats restarts the schedule
  from the new due date. **Retire…** (inside Edit) stops tracking a bill but
  keeps its payment history; retired bills can be restored from the **Retired**
  section.
- **Tap a bill's name** to see its payment history: last payment and change,
  average, range, trend, year over year, a chart and the list of payments.
- **Categories** (its own tab, shared by bills and the budget): name and icon
  for each. Deleting a category makes its bills uncategorized.

### How costs are counted

The **This month**, **This year** and **Previous years** sections count bills by
**due date**: a bill due in December counts in December even if you paid it in
November. *Paid* is what you actually paid; *Upcoming* (or *Unpaid* for periods
that are over) uses each bill's estimate. Due dates without an amount are listed
separately rather than guessed. Bars show how much of each total is paid.

Autopay bills behave like any other bill: they're reminded and stay due until
you record the payment, so you can confirm the charge went through.

## Budget

The **Budget** tab works out how much you can spend today.

**Set up** (and **Budget reset** at the bottom of the tab later): pick a start date (today by default), what spending money you're
starting with, and any savings you already have. Then add your recurring income.

**How the daily number works.** Each day earns an allowance:

> recurring income per day − bills per day − savings plans per day

A $2,400 paycheck every 2 weeks adds $171.43 to every day; $1,500 rent a month
takes $49.28 a day; $150 to savings every 2 weeks takes $10.71 a day. Bills use
their estimates (bills without an amount aren't counted); one-time bills come
out on the day you pay them.

**When a bill costs more or less than its estimate**, the difference is settled
on the day you pay it: paying $52 for a $40 water bill takes $12 out of that
day's budget, and paying $35 gives $5 back. These show in Transactions as
*Water: $12.00 over estimate*. Each payment remembers the estimate it was
measured against, so changing a bill's estimate later never changes past
adjustments.

**Today's budget** = what carried over + today's allowance + one-off income
today − expenses today. It updates as soon as you add something. Spend less
and the rest carries to tomorrow; spend more and tomorrow starts lower. The top
of the tab shows today and the next two days.

At midnight each finished day is locked in, so changing a paycheck, a savings
plan or a bill's estimate only changes today onward, never the past. (A
**Budget reset** starts over from its new start date, so days from then on are
worked out again with the current amounts.)

**Adding things** (**+ Add**):

- **Expense**: amount, category, optional note (it uses the category name if
  you leave it empty), date.
- **Income**: *One-off* adds it to that day's budget (e.g. card rewards).
  *Every week / Every 2 weeks / Monthly / Yearly* adds recurring income with a
  start date and an optional end date (leave it empty if it's open-ended and
  add one later with **Edit**).

**Savings**: add plans (e.g. $150 every 2 weeks) that come out before the
daily number, and **Move to savings** / **Take from savings** for one-off
amounts. *All-time savings* is what you started with plus everything set aside
since.

**Quick add from your phone**: open the panel at `/bills?add=expense` (or
`?add=income`) to go straight to the form; see *Phone widgets* below. The panel
also remembers which tab you used last.

## Reminders on your phone

Bills fires a `bills_reminder` event each day at 9:00 for every bill that's
overdue, due today, or inside its reminder window. If Home Assistant was off at
9:00, the reminders are sent once it has started up again (once per day, so a
restart won't repeat them).

The included blueprint turns these into phone notifications with a **Pay bill**
button (and a **Biller site** button if the bill has a payment website). It
clears the notification when the bill is paid.

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fryangoderre%2Fha-bills-budget%2Fblob%2Fmain%2Fblueprints%2Fbill_reminders.yaml)

After importing, create an automation from it and enter:

- **Notify service**: your phone's, e.g. `notify.mobile_app_your_phone`
- **Bills panel path**: `/bills` (the default)

## Entities

| Entity | State | Useful attributes |
|---|---|---|
| `sensor.bills_summary` | One line, e.g. *Phone due in 2 days · 2 more this week* | `lines` (one per bill due this week), `widget` (ready-made text for Android widgets) |
| `sensor.bills_next_due` | Date of the next bill | name, amount, days until, `summary` |
| `sensor.bills_due_soon` | How many bills are inside their reminder window | `bills` |
| `sensor.bills_overdue` | How many bills are overdue | `bills` |
| `sensor.bills_due_this_month` | Unpaid amount due by the end of the month | `bills_without_amount` |
| `calendar.bills` | Every upcoming due date | Each event's description has the category, amount and autopay |
| `sensor.bills_budget_today` | Today's budget | `tomorrow`, `day_after`, `days`, `daily_allowance`, `spent_today`, `summary` (e.g. *Today $42.10 · Tomorrow $101.36 · Fri $160.62*), `widget` (for Android) |
| `sensor.bills_savings_total` | All-time savings | `per_month` from regular plans |

## Phone widgets

**Android** (Home Assistant app → home screen widgets → **Template**):

- Today's budget and the next two days:
  `{{ state_attr('sensor.bills_budget_today','widget') }}`
- Bills, one line: `{{ states('sensor.bills_summary') }}`
- Bills due this week (bold when overdue):
  `{{ state_attr('sensor.bills_summary','widget') }}`

The Android template widget can't open a page when tapped. For one-tap adding,
create shortcuts (Companion app settings → **Manage shortcuts**) to
`/bills?add=expense` and `/bills` and pin them next to the widget.

**iPhone, iPad and Mac** (Home Assistant app widgets):

- **Sensors** → *Bills Budget today* (and *Bills Savings total*) for the budget
- **Sensors** → *Bills Summary* for the one-line bills summary
- **Calendar** → *Bills* for upcoming due dates
- **Open Page** → *Bills & Budget* to open the panel in one tap (it opens on
  the tab you used last)

## Services

All services are under `bills.` and can be used in scripts and automations.
Ones marked *returns* give back data (use *Developer tools → Actions* with
*Return response* to see it).

| Service | What it does |
|---|---|
| `add_bill` | Add a bill. Returns its id and first due date. |
| `update_bill` | Change a bill. Set `amount`, `end_date`, `biller_url`, `notes` or `category` to `null` to clear them. |
| `retire_bill` / `restore_bill` | Stop tracking a bill / bring it back (optionally with a new `due_date`). |
| `mark_paid` | Record a payment and move to the next due date. `update_amount: true` makes the amount paid the new estimate. |
| `list_bills`, `list_payments` | *Returns* bills / payments. |
| `bill_history` | *Returns* one bill's payments and stats (average, range, change, trend, year over year). |
| `cost_summary` | *Returns* this month, this year (with months) and previous years, by category. |
| `add_category`, `update_category`, `delete_category`, `list_categories` | Manage categories. |
| `send_reminders` | Fire reminder events now (doesn't affect the daily run). |
| `budget_setup` | Start or restart the budget (start date, starting amount, starting savings). |
| `add_expense`, `add_income` | Record spending / one-off income (amount, optional category, note, date). *Returns* today's budget. |
| `move_to_savings`, `take_from_savings` | One-off savings moves. |
| `delete_transaction` | Remove an expense, income or savings move. |
| `add_recurring`, `update_recurring`, `delete_recurring` | Recurring income (`type: income`) or savings plans (`type: savings`). Every 2 weeks is `frequency: weekly`, `interval: 2`. |
| `budget_summary` | *Returns* today's budget, the next days, the allowance, savings, recurring items and recent transactions. |
| `backup`, `list_backups`, `restore_backup` | See below. |

Bills can be referred to by id or by name; categories by id or name too.

Events: `bills_reminder` (one per bill to remind about) and `bills_paid`
(after a payment, with `bill_id`, `bill_name` and `next_due`).

## Backups

Your bills and budget live in `.storage/bills.data`, which Home Assistant's own backups
include. In addition, Bills writes a readable copy to `config/bills_backups/`
every day (the latest 14 are kept):

- `bills.backup` saves a copy now (`bills-manual-….json`, never removed automatically).
- `bills.list_backups` shows the files.
- `bills.restore_backup` with `file: bills-2026-11-18.json` replaces all bills,
  payments, categories and the budget with that copy. A `bills-before-restore-….json` copy
  of the current data is saved first.

These copies sit on the same disk as Home Assistant. For protection against a
failed SD card or disk, turn on Home Assistant's automatic backups with an
off-device location (**Settings → System → Backups**).

**Moving to another Home Assistant:** run `bills.backup` on the old one, copy
the file into the new one's `config/bills_backups/`, then run
`bills.restore_backup` with its name.

## Development

`docker-compose.yml` runs a test Home Assistant on port 8123 with this
integration and the blueprint mounted in:

```sh
docker compose up -d
```

The schedule, summary, budget and backup logic is plain Python and tested without Home
Assistant:

```sh
pip install pytest
pytest
```

## License

[MIT](LICENSE)
