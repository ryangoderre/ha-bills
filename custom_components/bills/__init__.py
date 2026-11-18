import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

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

    async def _daily_reminders(*_) -> None:
        """Send today's reminders once; a restart later the same day won't repeat them."""
        if not hass.is_running:
            return  # still starting up; _on_started sends them once automations load
        today = dt_util.now().date().isoformat()
        if store.meta.get("last_reminder_date") == today:
            return
        sent = fire_reminders(hass, store)
        await store.async_set_meta("last_reminder_date", today)
        _LOGGER.info("Sent %d bill reminder(s)", len(sent))

    async def _daily_backup(*_) -> None:
        try:
            name = await store.async_daily_backup()
        except OSError as err:
            _LOGGER.error("Bills daily backup failed: %s", err)
            return
        if name:
            _LOGGER.info("Bills backup written: %s", name)

    @callback
    def _midnight(now) -> None:
        coordinator.async_recompute()
        hass.async_create_task(_daily_backup())

    async def _on_started(_hass: HomeAssistant) -> None:
        # Runs once HA has fully started, so automations (the reminder
        # blueprint) are loaded before any catch-up reminders fire.
        await _daily_backup()
        if dt_util.now().hour >= REMINDER_HOUR:
            await _daily_reminders()  # HA was down or restarting at reminder time

    entry.async_on_unload(store.async_add_listener(coordinator.async_recompute))
    entry.async_on_unload(
        async_track_time_change(hass, _midnight, hour=0, minute=0, second=5)
    )
    entry.async_on_unload(
        async_track_time_change(
            hass, _daily_reminders, hour=REMINDER_HOUR, minute=0, second=0
        )
    )
    entry.async_on_unload(async_at_started(hass, _on_started))

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
