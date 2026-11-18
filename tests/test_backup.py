import importlib.util
from datetime import date, datetime
from pathlib import Path

import pytest

# Load backup.py by path so the test doesn't need Home Assistant installed.
_path = Path(__file__).resolve().parent.parent / "custom_components" / "bills" / "backup.py"
_spec = importlib.util.spec_from_file_location("bills_backup", _path)
backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backup)

BILL = {"id": "b1", "name": "Phone", "amount": 85.0, "frequency": "monthly",
        "interval": 1, "anchor_date": "2026-11-19", "next_due": "2026-12-19",
        "end_date": None, "active": True, "remind_days_before": 3,
        "autopay": False}
PAYMENT = {"id": "p1", "bill_id": "b1", "bill_name": "Phone",
           "due_date": "2026-11-19", "paid_date": "2026-11-18", "amount_paid": 85.0}


def test_names():
    assert backup.daily_name(date(2026, 11, 18)) == "bills-2026-11-18.json"
    assert backup.stamped_name(datetime(2026, 11, 18, 9, 5, 7), "manual") \
        == "bills-manual-20261118-090507.json"


def test_prune_keeps_newest_daily_only():
    names = [f"bills-2026-11-{d:02d}.json" for d in range(1, 18)]
    names += ["bills-manual-20261101-000000.json", "notes.txt"]
    pruned = backup.daily_to_prune(names, keep=14)
    assert pruned == ["bills-2026-11-01.json", "bills-2026-11-02.json",
                      "bills-2026-11-03.json"]


def test_prune_nothing_when_under_limit():
    assert backup.daily_to_prune(["bills-2026-11-01.json"]) == []


@pytest.mark.parametrize("name", ["../secrets.yaml", "/config/x.json",
                                  "sub/bills.json", ".hidden.json", "bills.txt"])
def test_check_name_rejects_paths(name):
    with pytest.raises(ValueError):
        backup.check_name(name)


def test_check_name_accepts_backup_names():
    assert backup.check_name("bills-2026-11-18.json") == "bills-2026-11-18.json"


def test_round_trip():
    cats = {"c1": {"id": "c1", "name": "Utilities", "icon": "mdi:flash"}}
    data = backup.build({"b1": BILL}, [PAYMENT], cats,
                        {"last_reminder_date": "2026-11-18"}, datetime(2026, 11, 18), 1)
    out = backup.validate(data)
    assert out["bills"]["b1"]["name"] == "Phone"
    assert out["categories"]["c1"]["icon"] == "mdi:flash"
    assert out["meta"]["last_reminder_date"] == "2026-11-18"


@pytest.mark.parametrize("data", [
    [], {"bills": {}}, {"bills": [], "payments": []},
    {"bills": {"b1": {"id": "b1"}}, "payments": []},
    {"bills": {"other": BILL}, "payments": []},
    {"bills": {"b1": BILL}, "payments": [{"id": "p1"}]},
])
def test_validate_rejects_bad_data(data):
    with pytest.raises(ValueError):
        backup.validate(data)


def test_old_backup_without_categories_is_fine():
    out = backup.validate({"bills": {"b1": BILL}, "payments": []})
    assert out["categories"] == {}


def test_bad_category_rejected():
    with pytest.raises(ValueError):
        backup.validate({"bills": {}, "payments": [],
                         "categories": {"c1": {"id": "other", "name": "X"}}})
