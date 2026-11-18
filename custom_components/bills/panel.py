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
    if not hass.data.get(_STATIC_KEY):
        folder = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(folder), cache_headers=False)]
        )
        hass.data[_STATIC_KEY] = True
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="bills-panel",
        frontend_url_path=PANEL_PATH,
        module_url=f"{URL_BASE}/bills-panel.js",
        sidebar_title="Bills",
        sidebar_icon="mdi:cash-multiple",
        require_admin=False,
        config={},
    )


def async_remove_panel(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, PANEL_PATH)