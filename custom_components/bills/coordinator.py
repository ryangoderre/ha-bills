"""Recomputes the summary whenever bills change and again each midnight."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .store import BillStore
from .summary import compute_summary

_LOGGER = logging.getLogger(__name__)


class BillsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: BillStore):
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=None
        )
        self.store = store
        self.data = self._compute()

    def _compute(self) -> dict[str, Any]:
        data = compute_summary(self.store.list_bills(), dt_util.now().date())
        data["budget"] = self.store.budget_summary()
        return data

    async def _async_update_data(self) -> dict[str, Any]:
        return self._compute()

    @callback
    def async_recompute(self, *_: Any) -> None:
        self.async_set_updated_data(self._compute())