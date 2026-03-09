"""Notify entity for WeCom Notify."""

from __future__ import annotations

from typing import Any

from homeassistant.components.notify import NotifyEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_BOT_ID, DEFAULT_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WeCom notify entity from config entry."""
    async_add_entities([WeComNotifyEntity(hass, entry)], True)


class WeComNotifyEntity(NotifyEntity):
    """WeCom notification entity."""

    _attr_has_entity_name = True
    _attr_name = DEFAULT_NAME

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}"

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
    def available(self) -> bool:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        return runtime is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id, {})
        paired_targets = runtime.get("paired_targets", set())
        return {
            "bot_id": self.entry.data.get(CONF_BOT_ID, ""),
            "paired_targets_count": len(paired_targets),
        }

    async def async_send_message(self, message: str = "", **kwargs: Any) -> None:
        runtime = self.hass.data.get(DOMAIN, {}).get(self.entry.entry_id)
        if runtime is None:
            return

        target = kwargs.get("target")
        if isinstance(target, list) and target:
            send_target = target[0]
        elif isinstance(target, str) and target:
            send_target = target
        else:
            send_target = "@all"

        await runtime["client"].send_markdown(send_target, message)
