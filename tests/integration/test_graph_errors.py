# pylint: disable=unused-argument,line-too-long
"""Test the calendar's handling of MS Graph and token errors."""

from unittest.mock import patch

import pytest
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from requests.exceptions import ConnectionError as RequestConnectionError, RetryError
from requests_mock import Mocker

from ..const import ENTITY_NAME
from ..helpers.mock_config_entry import MS365MockConfigEntry
from ..helpers.refresh import expire_access_token, mock_refresh_failure
from ..helpers.utils import check_entity_state, mock_call
from .const_integration import DOMAIN, URL
from .fixtures import ClientFixture
from .helpers_integration.mocks import MS365MOCKS

CALENDAR1_VIEW = f"{URL.CALENDARS.value}/calendar1/calendarView"


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


async def test_sync_token_refresh_failure(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a token that can no longer be refreshed raises the repair issue."""
    coordinator = _coordinator(base_config_entry, "calendar1")
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)
    mock_refresh_failure(requests_mock, "invalid_grant")

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    issues = list(issue_registry.issues.values())
    assert [issue.translation_key for issue in issues] == ["expired"]
    assert issues[0].translation_placeholders["entity_name"] == ENTITY_NAME
    check_entity_state(
        hass, "calendar.test_calendar1", "on", attributes={"sync_state": "problem"}
    )
    assert "Refresh token operation failed: invalid_grant" in caplog.text
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


async def test_get_events_token_refresh_failure(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
    requests_mock: Mocker,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test a token that can no longer be refreshed when fetching a range of events."""
    await _async_expire_token(hass, tmp_path, base_config_entry)
    requests_mock.get(CALENDAR1_VIEW, status_code=401)
    mock_refresh_failure(requests_mock, "invalid_grant")

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


async def _async_get_events(hass: HomeAssistant):
    """Get events outside the synced range, so they are fetched from MS Graph."""
    return await hass.services.async_call(
        CALENDAR_DOMAIN,
        SERVICE_GET_EVENTS,
        {
            "entity_id": "calendar.test_calendar1",
            "start_date_time": "2022-03-22T20:00:00.000Z",
            "end_date_time": "2022-03-22T22:00:00.000Z",
        },
        blocking=True,
        return_response=True,
    )
