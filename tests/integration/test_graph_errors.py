# pylint: disable=unused-argument,line-too-long
"""Test the calendar's handling of MS Graph and token errors."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from requests.exceptions import ConnectionError as RequestConnectionError, RetryError
from requests_mock import Mocker

from ..const import ENTITY_NAME
from ..helpers.mock_config_entry import MS365MockConfigEntry
from ..helpers.refresh import (
    REFRESH_UNAVAILABLE,
    expire_access_token,
    mock_refresh_failure,
    mock_refresh_timeout,
    refresh_unavailable,
)
from ..helpers.utils import check_entity_state, mock_call
from .const_integration import DOMAIN, URL
from .fixtures import ClientFixture
from .helpers_integration.mocks import MS365MOCKS

CALENDAR1_VIEW = f"{URL.CALENDARS.value}/calendar1/calendarView"
# Refusals of the login service that need the user to sign in again
REFRESH_REFUSED = ["invalid_grant", "interaction_required", "unauthorized_client"]


async def test_setup_retry_calendar_list(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test setup is retried when the calendars cannot be listed."""
    MS365MOCKS.standard_mocks(requests_mock)
    requests_mock.get(
        URL.CALENDARS.value, exc=RequestConnectionError("Connection reset")
    )
    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert base_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert base_config_entry.reason == "Unable to connect to MS Graph: Connection reset"


@pytest.mark.parametrize("error", [RequestConnectionError, RetryError])
async def test_setup_retry_calendar_get(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    error,
) -> None:
    """Test setup is retried, not the calendar dropped, when it cannot be fetched."""
    MS365MOCKS.standard_mocks(requests_mock)
    requests_mock.get(f"{URL.CALENDARS.value}/calendar1", exc=error("Connection reset"))
    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert base_config_entry.state is ConfigEntryState.SETUP_RETRY
    assert "Has the calendar been deleted?" not in caplog.text


@pytest.mark.parametrize("error", REFRESH_REFUSED)
async def test_sync_token_refresh_failure(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
    error,
) -> None:
    """Test a token that can no longer be refreshed raises the repair issue."""
    coordinator = _coordinator(base_config_entry, "calendar1")
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)
    mock_refresh_failure(requests_mock, error)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    issues = list(issue_registry.issues.values())
    assert [issue.translation_key for issue in issues] == ["expired"]
    assert issues[0].issue_id == f"expired_{base_config_entry.entry_id}"
    assert issues[0].translation_placeholders["entity_name"] == ENTITY_NAME
    check_entity_state(
        hass, "calendar.test_calendar1", "on", attributes={"sync_state": "problem"}
    )
    assert (
        "Unable to refresh the token, fetching from cache: "
        f"Refresh token operation failed: {error}"
    ) in caplog.text
    assert "Unexpected error" not in caplog.text

    # The issue goes once the calendar syncs again, such as after a reconfigure
    MS365MOCKS.standard_mocks(requests_mock)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not issue_registry.issues
    check_entity_state(
        hass, "calendar.test_calendar1", "on", attributes={"sync_state": "ok"}
    )

    # Other errors are not taken for a token problem
    with patch(
        "O365.calendar.Calendar.get_events", side_effect=RuntimeError("Other error")
    ):
        await coordinator.async_refresh()
    assert "Unexpected error fetching Calendar1 data" in caplog.text


@pytest.mark.parametrize("error", REFRESH_REFUSED)
async def test_get_events_token_refresh_failure(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
    error,
) -> None:
    """Test a token that can no longer be refreshed when fetching a range of events."""
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)
    mock_refresh_failure(requests_mock, error)

    result = await _async_get_events(hass)

    assert result["calendar.test_calendar1"]["events"] == []
    issues = list(issue_registry.issues.values())
    assert [issue.translation_key for issue in issues] == ["expired"]

    # Other errors are not taken for a token problem
    with (
        patch(
            "O365.calendar.Calendar.get_events", side_effect=RuntimeError("Other error")
        ),
        pytest.raises(RuntimeError, match="Other error"),
    ):
        await _async_get_events(hass)


@pytest.mark.parametrize(("cause", "error"), REFRESH_UNAVAILABLE)
async def test_token_refresh_unavailable(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
    cause,
    error,
) -> None:
    """Test a token that cannot be refreshed for now uses the cache, with no issue."""
    coordinator = _coordinator(base_config_entry, "calendar1")
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)

    with refresh_unavailable(requests_mock, cause):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        result = await _async_get_events(hass)

    check_entity_state(
        hass, "calendar.test_calendar1", "on", attributes={"sync_state": "problem"}
    )
    assert f"Unable to refresh the token, fetching from cache: {error}" in caplog.text
    assert "Unexpected error" not in caplog.text
    # A range outside the synced one also comes from the cache
    assert result["calendar.test_calendar1"]["events"] == []
    assert f"Unable to refresh the token, fetching from cache. - {error}" in caplog.text
    assert not issue_registry.issues


async def test_token_refresh_timeout(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a token refresh that times out uses the cache, as a connection error does."""
    coordinator = _coordinator(base_config_entry, "calendar1")
    cached_events = hass.states.get("calendar.test_calendar1").attributes["data"]
    assert len(cached_events) == 2
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)
    mock_refresh_timeout(requests_mock)

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    check_entity_state(
        hass,
        "calendar.test_calendar1",
        "on",
        attributes={"sync_state": "problem", "data": cached_events},
    )
    assert (
        "Error syncing calendar events from MS Graph, fetching from cache: "
        "Read timed out"
    ) in caplog.text
    assert "Timeout fetching" not in caplog.text

    # A range reaching beyond the synced one also comes from the cache
    now = dt_util.utcnow()
    result = await _async_get_events(
        hass,
        (now - timedelta(days=60)).isoformat(),
        (now + timedelta(days=60)).isoformat(),
    )

    events = result["calendar.test_calendar1"]["events"]
    assert sorted(event["summary"] for event in events) == [
        "Test event 1 calendar1",
        "Test event 2 calendar1",
    ]
    assert (
        "Error getting calendar event range from MS Graph, fetching from cache. - "
        "Read timed out"
    ) in caplog.text
    assert not issue_registry.issues


async def test_remove_missing_event(
    hass: HomeAssistant,
    setup_update_integration,
    requests_mock: Mocker,
) -> None:
    """Test removing an event that is not in the calendar gives a clear error."""
    requests_mock.get(
        f"{URL.CALENDARS.value}/calendar1/events/event9",
        status_code=404,
        json={
            "error": {
                "code": "ErrorItemNotFound",
                "message": "The specified object was not found in the store.",
            }
        },
    )

    with pytest.raises(ServiceValidationError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "remove_calendar_event",
            {"entity_id": "calendar.test_calendar1", "event_id": "event9"},
            blocking=True,
        )
    assert (
        str(exc_info.value) == "Event event9 was not found in calendar.test_calendar1"
    )


@pytest.mark.parametrize(("cause", "error"), REFRESH_UNAVAILABLE)
async def test_remove_event_token_refresh_unavailable(
    tmp_path,
    hass: HomeAssistant,
    setup_update_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    cause,
    error,
) -> None:
    """Test a service call while the token cannot be refreshed gives a clear error."""
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(f"{URL.CALENDARS.value}/calendar1/events/event1", status_code=401)

    with (
        refresh_unavailable(requests_mock, cause),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _async_remove_event1(hass)
    assert str(exc_info.value) == f"Unable to connect to MS Graph: {error}"

    # Other errors are not taken for a connection problem
    with (
        patch("O365.calendar.Calendar.get_event", side_effect=RuntimeError("Other")),
        pytest.raises(RuntimeError, match="Other"),
    ):
        await _async_remove_event1(hass)


@pytest.mark.parametrize(
    ("error", "status_code"),
    [("invalid_grant", 400), ("invalid_client", 401), ("interaction_required", 400)],
)
async def test_remove_event_token_refresh_refused(
    tmp_path,
    hass: HomeAssistant,
    ws_client: ClientFixture,
    setup_update_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    error,
    status_code,
) -> None:
    """Test a change while the token can no longer be refreshed asks to sign in again."""
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(f"{URL.CALENDARS.value}/calendar1/events/event1", status_code=401)
    mock_refresh_failure(requests_mock, error, status_code)
    message = (
        "The token can no longer be refreshed, please reconfigure the integration "
        f"and re-authenticate: Refresh token operation failed: {error}"
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await _async_remove_event1(hass)
    assert str(exc_info.value) == message

    # The calendar panel shows the same message
    client = await ws_client()
    resp = await client.cmd(
        "delete", {"entity_id": "calendar.test_calendar1", "uid": "event1"}
    )
    assert not resp["success"]
    assert resp["error"]["code"] == "failed"
    assert resp["error"]["message"] == message


async def test_respond_refused(
    hass: HomeAssistant,
    setup_update_integration,
    requests_mock: Mocker,
) -> None:
    """Test a response that MS Graph refuses gives the reason it gave."""
    mock_call(
        requests_mock, URL.CALENDARS, "calendar1_event1", "calendar1/events/event1"
    )
    requests_mock.post(
        f"{URL.ME.value}/events/event1/accept",
        status_code=400,
        json={
            "error": {
                "code": "ErrorInvalidRequest",
                "message": "You can't respond to a meeting you organized.",
            }
        },
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            DOMAIN,
            "respond_calendar_event",
            {
                "entity_id": "calendar.test_calendar1",
                "event_id": "event1",
                "response": "Accept",
            },
            blocking=True,
        )
    message = str(exc_info.value)
    assert message.startswith("MS Graph returned an error: 400 Client Error")
    assert message.endswith(
        "Error Message: You can't respond to a meeting you organized."
    )


async def test_create_event_offline(
    ws_client: ClientFixture,
    setup_update_integration,
    requests_mock: Mocker,
) -> None:
    """Test creating an event in the calendar panel while MS Graph cannot be reached."""
    requests_mock.post(
        f"{URL.CALENDARS.value}/calendar1/events",
        exc=RequestConnectionError("Connection reset"),
    )
    client = await ws_client()

    resp = await client.cmd(
        "create",
        {
            "entity_id": "calendar.test_calendar1",
            "event": {
                "summary": "Department Party",
                "dtstart": "2024-10-24T07:00:00",
                "dtend": "2024-10-24T07:30:00",
            },
        },
    )

    assert not resp["success"]
    assert resp["error"]["code"] == "failed"
    assert resp["error"]["message"] == "Unable to connect to MS Graph: Connection reset"


def _coordinator(entry: MS365MockConfigEntry, calendar_id):
    return next(
        coordinator
        for coordinator in entry.runtime_data.coordinator
        if coordinator.sync.calendar_id == calendar_id
    )


async def _async_expire_token(hass: HomeAssistant, tmp_path, entry):
    """Have the access token expire while HA is running."""
    await hass.async_add_executor_job(expire_access_token, tmp_path)
    token_backend = entry.runtime_data.ha_account.account.con.token_backend
    await hass.async_add_executor_job(token_backend.load_token)


async def _async_remove_event1(hass: HomeAssistant):
    await hass.services.async_call(
        DOMAIN,
        "remove_calendar_event",
        {"entity_id": "calendar.test_calendar1", "event_id": "event1"},
        blocking=True,
    )


async def _async_get_events(
    hass: HomeAssistant,
    start="2022-03-22T20:00:00.000Z",
    end="2022-03-22T22:00:00.000Z",
):
    """Get events outside the synced range, so they are fetched from MS Graph."""
    return await hass.services.async_call(
        CALENDAR_DOMAIN,
        SERVICE_GET_EVENTS,
        {
            "entity_id": "calendar.test_calendar1",
            "start_date_time": start,
            "end_date_time": end,
        },
        blocking=True,
        return_response=True,
    )
