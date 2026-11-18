import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN, REMINDER_HOUR
from .coordinator import BillsCoordinator
from .reminders import fire_reminders
from .services import async_register_services, async_unload_services
from .store import BillStore
from .panel import async_register_panel, async_remove_panel


_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = BillStore(hass)
    await store.async_load()
    coordinator = BillsCoordinator(hass, entry, store)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(store.async_add_listener(coordinator.async_recompute))
    entry.async_on_unload(
        async_track_time_change(
            hass, coordinator.async_recompute, hour=0, minute=0, second=5
        )
    )

    @callback
    def _daily_reminders(_now) -> None:
        fire_reminders(hass, store)

    entry.async_on_unload(
        async_track_time_change(
            hass, _daily_reminders, hour=REMINDER_HOUR, minute=0, second=0
        )
    )

    async_register_services(hass, store)
    await async_register_panel(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Bills loaded: %d bills", len(store.bills))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        async_unload_services(hass)
        async_remove_panel(hass)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok