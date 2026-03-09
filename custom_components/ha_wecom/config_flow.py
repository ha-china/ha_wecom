"""Config flow for WeCom Notify integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AGENT_ID,
    CONF_BOT_ID,
    CONF_SECRET,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    We only validate non-empty required fields here.
    """
    if not data.get(CONF_BOT_ID) or not data.get(CONF_SECRET):
        raise ValueError("bot_id and secret are required")


async def _get_preferred_agent_id(hass: HomeAssistant) -> str:
    """Get preferred Assist pipeline conversation agent id."""
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipeline

        pipeline = async_get_pipeline(hass)
        if isinstance(pipeline.conversation_engine, str) and pipeline.conversation_engine:
            return pipeline.conversation_engine
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Unable to resolve preferred assist pipeline: %r", err)

    return ""


def _agent_selector(hass: HomeAssistant) -> selector.ConversationAgentSelector:
    """Return HA native conversation agent selector."""
    return selector.ConversationAgentSelector({"language": hass.config.language})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WeCom Notify."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "WeComOptionsFlowHandler":
        """Get the options flow for this handler."""
        return WeComOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        preferred_agent = await _get_preferred_agent_id(self.hass)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_BOT_ID): str,
                vol.Required(CONF_SECRET): str,
                vol.Optional(CONF_AGENT_ID, default=preferred_agent): _agent_selector(
                    self.hass
                ),
            }
        )

        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except ValueError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_BOT_ID])
                self._abort_if_unique_id_configured()
                if not user_input.get(CONF_AGENT_ID):
                    user_input.pop(CONF_AGENT_ID, None)
                return self.async_create_entry(title="企业微信", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


class WeComOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for WeCom Notify."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage WeCom Notify options."""
        if user_input is not None:
            if not user_input.get(CONF_AGENT_ID):
                user_input.pop(CONF_AGENT_ID, None)
            return self.async_create_entry(title="", data=user_input)

        preferred_agent = await _get_preferred_agent_id(self.hass)
        current_agent = self._config_entry.options.get(
            CONF_AGENT_ID,
            self._config_entry.data.get(CONF_AGENT_ID, preferred_agent),
        )

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AGENT_ID,
                    default=current_agent,
                ): _agent_selector(self.hass),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)
