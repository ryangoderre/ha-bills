import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change

from .const import DOMAIN
from .coordinator import BillsCoordinator
from .services import async_register_services, async_unload_services
from .store import BillStore

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = BillStore(hass)
    await store.async_load()
    coordinator = BillsCoordinator(hass, entry, store)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Refresh when bills change, and just after midnight so "days until" rolls over.
    entry.async_on_unload(store.async_add_listener(coordinator.async_recompute))
    entry.async_on_unload(
        async_track_time_change(
            hass, coordinator.async_recompute, hour=0, minute=0, second=5
        )
    )

    async_register_services(hass, store)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("Bills loaded: %d bills", len(store.bills))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        async_unload_services(hass)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok