"""Re-authentication helpers for MS365 testing."""

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from ..const import CLIENT_SECRET, ENTITY_NAME
from ..integration.const_integration import (
    AUTH_CALLBACK_PATH_DEFAULT,
    BASE_TOKEN_PERMS,
    DOMAIN,
    RECONFIGURE_CONFIG_ENTRY,
)
from ..integration.helpers_integration.mocks import MS365MOCKS
from .utils import build_token_url, get_schema_default, mock_token


def reauth_flows(hass: HomeAssistant, entry):
    """Return the re-authentication flows in progress for an entry."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"]["source"] == SOURCE_REAUTH
        and flow["context"]["entry_id"] == entry.entry_id
    ]


def reauth_issue(entry):
    """Return the issue HA raises while an entry needs re-authentication."""
    return ("homeassistant", f"config_entry_reauth_{DOMAIN}_{entry.entry_id}")


async def async_reauthenticate(
    hass: HomeAssistant, requests_mock, entry, user_input=RECONFIGURE_CONFIG_ENTRY
):
    """Re-authenticate an entry through the flow HA started for it."""
    [flow] = reauth_flows(hass, entry)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"])
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"] == {
        "entity_name": ENTITY_NAME,
        CONF_NAME: ENTITY_NAME,
    }

    # The same form as a reconfigure, with the credentials of the entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    assert get_schema_default(schema, "client_secret") == CLIENT_SECRET

    MS365MOCKS.standard_mocks(requests_mock)
    mock_token(requests_mock, BASE_TOKEN_PERMS)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )
    assert result["step_id"] == "request_default"
    assert result["description_placeholders"]["entity_name"] == ENTITY_NAME

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT)},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
