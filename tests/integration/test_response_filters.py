# pylint: disable=unused-argument,line-too-long,wrong-import-order
"""Test your own response to each event."""

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from requests_mock import Mocker

from ..helpers.mock_config_entry import MS365MockConfigEntry
from .const_integration import DOMAIN
from .helpers_integration.mocks import MS365MOCKS
from .helpers_integration.utils_integration import yaml_setup

CALENDAR1 = "calendar.test_calendar1"
SERVICE_TIME = "%Y-%m-%dT%H:%M:%SZ"
OUTSIDE_START = "2022-03-22T20:00:00.000Z"
OUTSIDE_END = "2022-03-22T22:00:00.000Z"
# The response of each event in calendar1_calendar_view_responses
RESPONSES = {
    "Accepted meeting": "accepted",
    "Declined meeting": "declined",
    "Tentative meeting": "tentatively_accepted",
    "Unanswered meeting": "not_responded",
    "Holiday": "organizer",
    "Working from home": None,
}


async def test_response_in_event_data(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test your own response to each event is in the data and the service response."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry)

    calendar_view = next(
        request
        for request in requests_mock.request_history
        if "calendarview" in request.url.lower()
    )
    assert "responsestatus" in calendar_view.qs["$select"][0].lower()

    data = hass.states.get(CALENDAR1).attributes["data"]
    assert {event["summary"]: event["response"] for event in data} == RESPONSES

    # In the synced window and in a range fetched from MS Graph
    for start, end in (_window(), (OUTSIDE_START, OUTSIDE_END)):
        events = await _get_calendar_events(hass, CALENDAR1, start, end)
        assert {event["summary"]: event["response"] for event in events} == RESPONSES


async def _async_setup(
    hass: HomeAssistant,
    tmp_path,
    requests_mock: Mocker,
    entry: MS365MockConfigEntry,
    yaml_file=None,
):
    """Set up calendar 1 with an event for each response and show as."""
    MS365MOCKS.response_event_mocks(requests_mock)
    if yaml_file:
        yaml_setup(tmp_path, yaml_file)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _get_calendar_events(hass: HomeAssistant, entity_id, start, end):
    """Get the events with the integration's own service."""
    result = await hass.services.async_call(
        DOMAIN,
        "get_calendar_events",
        {"entity_id": entity_id, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["events"]


def _window():
    """Get a range in the synced window, around now."""
    now = dt_util.utcnow()
    return (
        (now - timedelta(hours=1)).strftime(SERVICE_TIME),
        (now + timedelta(hours=1)).strftime(SERVICE_TIME),
    )
