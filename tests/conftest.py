import sys
import types
from pathlib import Path

_BILLS = Path(__file__).resolve().parent.parent / "custom_components" / "bills"
for _name, _path in (
    ("custom_components", _BILLS.parent),
    ("custom_components.bills", _BILLS),
):
    _mod = types.ModuleType(_name)
    _mod.__path__ = [str(_path)]
    sys.modules[_name] = _mod