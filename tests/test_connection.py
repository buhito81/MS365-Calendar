# pylint: disable=unused-argument
"""Test the handling of connection and token problems."""

import functools as ft
import time
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from portalocker import Lock
from portalocker.exceptions import LockException
from requests.exceptions import (
    ConnectionError as RequestConnectionError,
    ReadTimeout,
    RetryError,
)
from requests_mock import Mocker

from custom_components.ms365_calendar.classes.api import (
    MS365LockableFileSystemTokenBackend,
)

from .const import ENTITY_NAME, TOKEN_LOCATION
from .helpers.mock_config_entry import MS365MockConfigEntry
from .helpers.refresh import (
    expire_access_token,
    mock_refresh_failure,
    read_token_file,
    set_access_token,
)
from .integration.const_integration import DOMAIN, URL
from .integration.helpers_integration.mocks import MS365MOCKS

API = "custom_components.ms365_calendar.classes.api"


@pytest.mark.parametrize("error", [RequestConnectionError, ReadTimeout, RetryError])
async def test_setup_retry_when_unreachable(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    issue_registry: ir.IssueRegistry,
    error,
) -> None:
    """Test setup is retried when MS Graph cannot be reached."""
    MS365MOCKS.standard_mocks(requests_mock)
    requests_mock.get(URL.ME.value, exc=error("MS Graph unreachable"))
    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert base_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert (
        base_config_entry.reason
        == "Unable to connect to MS Graph: MS Graph unreachable"
    )
    assert not issue_registry.issues


async def test_expired_secret(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test an expired client secret, as MSAL reports it, raises the repair issue."""
    MS365MOCKS.standard_mocks(requests_mock)
    expire_access_token(tmp_path)
    requests_mock.get(URL.ME.value, status_code=401)
    mock_refresh_failure(requests_mock, "invalid_client", 401)
    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert f"Client Secret expired for account: {ENTITY_NAME}" in caplog.text
    assert base_config_entry.state is ConfigEntryState.SETUP_ERROR
    issue = issue_registry.async_get_issue(DOMAIN, "expired")
    assert issue is not None
    assert issue.translation_placeholders["entity_name"] == ENTITY_NAME


async def test_requests_have_timeout(
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
) -> None:
    """Test requests to MS Graph and to the login service have a timeout."""
    connection = base_config_entry.runtime_data.ha_account.account.con
    # Creating the MSAL client reads the login service configuration
    await hass.async_add_executor_job(getattr, connection, "msal_client")

    urls = [request.url for request in requests_mock.request_history]
    assert any(url.startswith(URL.ME.value) for url in urls)
    assert any(url.startswith(URL.OPENID.value) for url in urls)
    assert {request.timeout for request in requests_mock.request_history} == {30}


async def test_token_refresh_waits_for_lock(
    tmp_path,
    hass: HomeAssistant,
    base_token,
) -> None:
    """Test a refresh waits while another instance has the token file locked."""
    expire_access_token(tmp_path)
    backend = await hass.async_add_executor_job(_load_token_backend, tmp_path)
    con = MagicMock()
    con.refresh_token.side_effect = ft.partial(_new_refresh_token, backend)

    with (
        patch(f"{API}.Lock", side_effect=_locked(2)),
        patch(f"{API}.time") as mock_time,
    ):
        result = await hass.async_add_executor_job(backend.should_refresh_token, con)

    assert result is None
    assert mock_time.sleep.call_count == 2
    assert con.refresh_token.call_count == 1
    refresh_tokens = read_token_file(tmp_path)["RefreshToken"].values()
    assert [token["secret"] for token in refresh_tokens] == ["newrefreshtoken"]


async def test_token_refreshed_by_other_instance(
    tmp_path,
    hass: HomeAssistant,
    base_token,
) -> None:
    """Test a token refreshed by another instance is used, not refreshed again."""
    con = MagicMock()
    future = int(time.time()) + 3600

    # Refreshed before this instance looked
    backend = await hass.async_add_executor_job(_load_token_backend, tmp_path)
    set_access_token(tmp_path, "otheraccesstoken", future)
    with patch(f"{API}.Lock", side_effect=_locked(3)) as mock_lock:
        result = await hass.async_add_executor_job(backend.should_refresh_token, con)
    assert result is False
    assert mock_lock.call_count == 0
    assert backend.get_access_token()["secret"] == "otheraccesstoken"

    # Refreshed while this instance waited for the lock
    expire_access_token(tmp_path)
    backend = await hass.async_add_executor_job(_load_token_backend, tmp_path)
    waits = []

    def _wait(seconds):
        waits.append(seconds)
        if len(waits) == 2:
            set_access_token(tmp_path, "waitedaccesstoken", future)

    with (
        patch(f"{API}.Lock", side_effect=_locked(3)),
        patch(f"{API}.time") as mock_time,
    ):
        mock_time.sleep.side_effect = _wait
        result = await hass.async_add_executor_job(backend.should_refresh_token, con)

    assert result is False
    assert len(waits) == 2
    assert con.refresh_token.call_count == 0
    assert backend.get_access_token()["secret"] == "waitedaccesstoken"


async def test_token_refresh_gives_up(
    tmp_path,
    hass: HomeAssistant,
    base_token,
) -> None:
    """Test a refresh that cannot go ahead raises an error."""
    expire_access_token(tmp_path)
    backend = await hass.async_add_executor_job(_load_token_backend, tmp_path)
    con = MagicMock()

    # The other instance never lets go of the token file
    with (
        patch(f"{API}.Lock", side_effect=_locked(3)),
        patch(f"{API}.time") as mock_time,
        pytest.raises(RuntimeError, match="Could not access locked token file"),
    ):
        await hass.async_add_executor_job(backend.should_refresh_token, con)
    assert mock_time.sleep.call_count == 3
    assert con.refresh_token.call_count == 0

    # The refresh itself does not work
    con.refresh_token.return_value = False
    with pytest.raises(RuntimeError, match="Token Refresh Operation not working"):
        await hass.async_add_executor_job(backend.should_refresh_token, con)


def _load_token_backend(tmp_path):
    backend = MS365LockableFileSystemTokenBackend(
        token_path=tmp_path / TOKEN_LOCATION,
        token_filename=f"{DOMAIN}_{ENTITY_NAME}.token",
    )
    backend.load_token()
    return backend


def _new_refresh_token(backend):
    """Act as O365's refresh does, with Entra ID handing out a new refresh token."""
    backend.get_refresh_token()["secret"] = "newrefreshtoken"
    backend.save_token(force=True)
    return True


def _locked(times):
    """Have the token file locked by another instance for the first tries."""
    tries = []

    def _lock(*args, **kwargs):
        tries.append(args)
        if len(tries) <= times:
            raise LockException
        return Lock(*args, **kwargs)

    return _lock
