"""Registers the Bills sidebar panel."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

URL_BASE = f"/{DOMAIN}_static"
PANEL_PATH = DOMAIN  # the panel lives at /bills
_STATIC_KEY = f"{DOMAIN}_static_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    folder = Path(__file__).parent / "frontend"
    if not hass.data.get(_STATIC_KEY):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(folder), cache_headers=False)]
        )
        hass.data[_STATIC_KEY] = True
    # Version the URL by the file's mtime so browsers and the Companion app
    # pick up a new panel after a restart instead of a cached copy.
    mtime = await hass.async_add_executor_job(
        lambda: int((folder / "bills-panel.js").stat().st_mtime)
    )
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="bills-panel",
        frontend_url_path=PANEL_PATH,
        module_url=f"{URL_BASE}/bills-panel.js?v={mtime}",
        sidebar_title="Bills & Budget",
        sidebar_icon="mdi:cash-multiple",
        require_admin=False,
        config={},
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_PATH)