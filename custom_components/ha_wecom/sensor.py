"""Sensor entities for ha_wecom."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up status sensor."""
    async_add_entities([WeComConnectionSensor(hass, entry)], True)


class WeComConnectionSensor(SensorEntity):
    """Expose websocket connection status."""

    _attr_has_entity_name = True
    _attr_name = "连接状态"
    _attr_icon = "mdi:web"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_connection"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name="企业微信",
            manufacturer="Tencent WeCom",
            model="WeCom Bot",
            entry_type="service",
        )

    @property
    def native_value(self) -> str:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        if runtime is None:
            return "disconnected"

        client = runtime["client"]
        if client.is_authenticated:
            return "authenticated"
        if client.is_connected:
            return "connected"
        return "disconnected"
