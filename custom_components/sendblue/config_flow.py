"""Config flow for the Sendblue integration."""

import secrets
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlowWithReload,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME, CONF_WEBHOOK_ID
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    BooleanSelector,
    ConversationAgentSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SendblueAuthError, SendblueClient, SendblueError
from .const import (
    CONF_ADDRESS,
    CONF_API_KEY_ID,
    CONF_API_SECRET_KEY,
    CONF_ASSIST_ENABLED,
    CONF_CONVERSATION_AGENT_ID,
    CONF_LAST_LINE,
    CONF_WEBHOOK_BASE_URL,
    CONF_WEBHOOK_SECRET,
    DOMAIN,
    SUBENTRY_RECIPIENT,
)
from .phone import normalize_address
from .webhook import async_delete_remote_webhook

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
_CREDENTIALS_SCHEMA = {
    vol.Required(CONF_API_KEY_ID): str,
    vol.Required(CONF_API_SECRET_KEY): _PASSWORD,
}


def _clean_url(url: str) -> str | None:
    url = url.strip().rstrip("/")
    return url if url.startswith("https://") else None


class SendblueConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Sendblue."""

    VERSION = 1

    async def _validate(self, key_id: str, secret: str) -> str | None:
        client = SendblueClient(async_get_clientsession(self.hass), key_id, secret)
        try:
            lines = await client.get_lines()
        except SendblueAuthError:
            return "invalid_auth"
        except SendblueError:
            return "cannot_connect"
        return None if lines else "no_lines"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _clean_url(user_input[CONF_WEBHOOK_BASE_URL])
            if url is None:
                errors[CONF_WEBHOOK_BASE_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(user_input[CONF_API_KEY_ID])
                self._abort_if_unique_id_configured()
                error = await self._validate(
                    user_input[CONF_API_KEY_ID], user_input[CONF_API_SECRET_KEY]
                )
                if error:
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title="Sendblue",
                        data={
                            **user_input,
                            CONF_WEBHOOK_BASE_URL: url,
                            CONF_WEBHOOK_ID: webhook.async_generate_id(),
                            CONF_WEBHOOK_SECRET: secrets.token_hex(32),
                        },
                    )

        try:
            default_url = get_url(self.hass, allow_internal=False, allow_ip=False, require_ssl=True)
        except NoURLAvailableError:
            default_url = ""
        schema = vol.Schema(
            {
                **_CREDENTIALS_SCHEMA,
                vol.Required(CONF_WEBHOOK_BASE_URL, default=default_url): _URL,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._validate(
                user_input[CONF_API_KEY_ID], user_input[CONF_API_SECRET_KEY]
            )
            if error:
                errors["base"] = error
            else:
                # A rotated key has a new id, so the unique_id follows it.
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    unique_id=user_input[CONF_API_KEY_ID],
                    data_updates=user_input,
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(_CREDENTIALS_SCHEMA),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url = _clean_url(user_input[CONF_WEBHOOK_BASE_URL])
            if url is None:
                errors[CONF_WEBHOOK_BASE_URL] = "invalid_url"
            else:
                old_url = entry.data[CONF_WEBHOOK_BASE_URL]
                if url != old_url:
                    # Setup after the reload registers the new URL.
                    await async_delete_remote_webhook(self.hass, entry, old_url)
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_WEBHOOK_BASE_URL: url}
                )
        schema = vol.Schema(
            {vol.Required(CONF_WEBHOOK_BASE_URL, default=entry.data[CONF_WEBHOOK_BASE_URL]): _URL}
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        return SendblueOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_RECIPIENT: RecipientSubentryFlow}


class SendblueOptionsFlow(OptionsFlowWithReload):
    """Choose the conversation agent used for replies."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        # Left empty, replies use the preferred Assist pipeline.
        current = self.config_entry.options.get(CONF_CONVERSATION_AGENT_ID)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CONVERSATION_AGENT_ID,
                        description={"suggested_value": current},
                    ): ConversationAgentSelector()
                }
            ),
        )


class RecipientSubentryFlow(ConfigSubentryFlow):
    """Add or edit a recipient."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._async_step_form("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._async_step_form("reconfigure", user_input)

    async def _async_step_form(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> SubentryFlowResult:
        entry = self._get_entry()
        editing = self._get_reconfigure_subentry() if step_id == "reconfigure" else None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                address = normalize_address(user_input[CONF_ADDRESS], self.hass.config.country)
            except ValueError:
                errors[CONF_ADDRESS] = "invalid_address"
            else:
                if any(
                    sub.unique_id == address and sub is not editing
                    for sub in entry.subentries.values()
                ):
                    errors[CONF_ADDRESS] = "duplicate_address"
            if not errors:
                data = {
                    CONF_ADDRESS: address,
                    CONF_ASSIST_ENABLED: user_input.get(CONF_ASSIST_ENABLED, False),
                }
                if editing is not None:
                    return self.async_update_reload_and_abort(
                        entry,
                        editing,
                        title=user_input[CONF_NAME],
                        data=data,
                        unique_id=address,
                    )
                # New recipients need a reload to get their entities.
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=data, unique_id=address
                )

        defaults: dict[str, Any] = {}
        if editing is not None:
            defaults = {CONF_NAME: editing.title, **editing.data}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_ADDRESS): str,
                vol.Optional(CONF_ASSIST_ENABLED, default=False): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, user_input or defaults),
            errors=errors,
            description_placeholders={"number": entry.data.get(CONF_LAST_LINE, "-")},
        )
