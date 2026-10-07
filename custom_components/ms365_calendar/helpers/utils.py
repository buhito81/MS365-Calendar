"""Utilities processes."""

from msal.exceptions import MsalServiceError

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import async_generate_entity_id

from ..const import (
    CONF_API_COUNTRY,
    CONF_API_OPTIONS,
    CONF_TENANT_ID,
    DEFAULT_TENANT_ID,
    TOKEN_FILE_CORRUPTED,
    TOKEN_FILE_EXPIRED,
    TOKEN_FILE_LOCKED,
    TOKEN_FILE_MISSING,
    TOKEN_FILE_OUTDATED,
    TOKEN_FILE_PERMISSIONS,
    TOKEN_REFRESH_BUSY,
    TOKEN_REFRESH_FAILED,
    CountryOptions,
)
from ..integration.const_integration import DOMAIN


def add_attribute_to_item(item, user_input, attribute):
    """Add an attribute to an item."""
    if user_input.get(attribute) is not None:
        item[attribute] = user_input[attribute]
    elif attribute in item:
        del item[attribute]


def async_delete_token_issues(hass: HomeAssistant, entry_id):
    """Delete the token repair issues of a config entry."""
    for error in (
        TOKEN_FILE_CORRUPTED,
        # Older versions raised it for an expired token, which now starts re-auth
        TOKEN_FILE_EXPIRED,
        TOKEN_FILE_MISSING,
        TOKEN_FILE_OUTDATED,
        TOKEN_FILE_PERMISSIONS,
    ):
        ir.async_delete_issue(hass, DOMAIN, f"{error}_{entry_id}")


def build_entity_id(hass: HomeAssistant, entity_id_format, name):
    """Build an entity ID."""
    return async_generate_entity_id(
        entity_id_format,
        name,
        hass=hass,
    )


def get_country(entry_data):
    """Get the country from entry_data."""
    country = CountryOptions.DEFAULT
    if entry_data.get(CONF_API_OPTIONS):
        country = entry_data[CONF_API_OPTIONS][CONF_API_COUNTRY]
    return country


def get_tenant_id(entry_data):
    """Get the tenant_id from entry_data, defaulting to 'common'."""
    if entry_data.get(CONF_API_OPTIONS):
        tid = entry_data[CONF_API_OPTIONS].get(CONF_TENANT_ID, "")
        if tid.strip():
            return tid.strip()
    return DEFAULT_TENANT_ID


def token_refresh_refused(err: Exception) -> bool:
    """Check for a token that the login service will no longer refresh.

    A busy login service may refresh it later. Any other refusal, such as
    invalid_grant or interaction_required, needs the user to sign in again.
    """
    message = str(err)
    return message.startswith(TOKEN_REFRESH_FAILED) and not message.startswith(
        TOKEN_REFRESH_BUSY
    )


def token_refresh_unavailable(err: Exception) -> bool:
    """Check for a token refresh that can work when tried again later."""
    # The login service failed or is busy, or another refresh kept the token file locked
    return isinstance(err, MsalServiceError) or str(err).startswith(
        (TOKEN_REFRESH_BUSY, TOKEN_FILE_LOCKED)
    )
