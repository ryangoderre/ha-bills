# Bills for Home Assistant

Track recurring bills in Home Assistant: due dates, reminders on your phone,
payment history, and what you're spending by category, month and year.
Everything stays on your Home Assistant; nothing is sent to an outside service.

- **Bills panel** in the sidebar to add, edit, pay, retire and restore bills
- **Categories** with icons, and cost summaries for this month, this year and
  previous years (paid, upcoming, total, by category and by month)
- **Payment history** per bill, with a chart and whether it's going up or down
- **Reminders** each morning for bills that are due soon or overdue, with a
  *Pay bill* button that opens the payment form
- **Sensors and a calendar** for dashboards and phone widgets
- **Daily backups** of your bills, with one-step restore

## Requirements

Home Assistant 2024.11 or newer.

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ryangoderre&repository=ha-bills&category=integration)

Or by hand:

1. In HACS, open the **⋮** menu → **Custom repositories**.
2. Add `https://github.com/ryangoderre/ha-bills` with the type **Integration**.
3. Find **Bills** in HACS, download it, and restart Home Assistant.

### Manual

Copy `custom_components/bills` into your Home Assistant `config/custom_components/`
folder and restart Home Assistant.

## Setup

[![Open your Home Assistant instance and start setting up Bills.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=bills)

Or go to **Settings → Devices & services → Add integration** and search for
**Bills**. There are no options to fill in. A **Bills** item appears in the sidebar.

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
- **Categories** (top of the panel): name and icon for each. Deleting a category
  makes its bills uncategorized.

### How costs are counted

The **This month**, **This year** and **Previous years** sections count bills by
**due date**: a bill due in December counts in December even if you paid it in
November. *Paid* is what you actually paid; *Upcoming* (or *Unpaid* for periods
that are over) uses each bill's estimate. Due dates without an amount are listed
separately rather than guessed. Bars show how much of each total is paid.

Autopay bills behave like any other bill: they're reminded and stay due until
you record the payment, so you can confirm the charge went through.

## Reminders on your phone

Bills fires a `bills_reminder` event each day at 9:00 for every bill that's
overdue, due today, or inside its reminder window. If Home Assistant was off at
9:00, the reminders are sent once it has started up again (once per day, so a
restart won't repeat them).

The included blueprint turns these into phone notifications with a **Pay bill**
button (and a **Biller site** button if the bill has a payment website). It
clears the notification when the bill is paid.

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fryangoderre%2Fha-bills%2Fblob%2Fmain%2Fblueprints%2Fbill_reminders.yaml)

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

## Phone widgets

**Android** (Home Assistant app → home screen widgets → **Template**):

- One line: `{{ states('sensor.bills_summary') }}`
- Bills due this week (bold when overdue):
  `{{ state_attr('sensor.bills_summary','widget') }}`

The Android template widget can't open a page when tapped. To get to the panel
in one tap, add a shortcut to `/bills` (Companion app settings → **Manage
shortcuts**) and pin it next to the widget.

**iPhone, iPad and Mac** (Home Assistant app widgets):

- **Sensors** → *Bills Summary* for the one-line summary
- **Calendar** → *Bills* for upcoming due dates
- **Open Page** → *Bills* to open the panel in one tap

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
| `backup`, `list_backups`, `restore_backup` | See below. |

Bills can be referred to by id or by name; categories by id or name too.

Events: `bills_reminder` (one per bill to remind about) and `bills_paid`
(after a payment, with `bill_id`, `bill_name` and `next_due`).

## Backups

Your bills live in `.storage/bills.data`, which Home Assistant's own backups
include. In addition, Bills writes a readable copy to `config/bills_backups/`
every day (the latest 14 are kept):

- `bills.backup` saves a copy now (`bills-manual-….json`, never removed automatically).
- `bills.list_backups` shows the files.
- `bills.restore_backup` with `file: bills-2026-11-18.json` replaces all bills,
  payments and categories with that copy. A `bills-before-restore-….json` copy
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

The schedule, summary and backup logic is plain Python and tested without Home
Assistant:

```sh
pip install pytest
pytest
```

## License

[MIT](LICENSE)
