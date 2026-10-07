# pylint: disable=unused-argument,line-too-long,wrong-import-order
"""Test your own response to each event, and the filters on it and on show as."""

from datetime import timedelta

import pytest
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from O365.calendar import EventShowAs
from requests_mock import Mocker
from voluptuous.error import Invalid

from custom_components.ms365_calendar.integration.schema_integration import (
    YAML_CALENDAR_ENTITY_SCHEMA,
)

from ..helpers.mock_config_entry import MS365MockConfigEntry
from .const_integration import DOMAIN
from .helpers_integration.mocks import MS365MOCKS
from .helpers_integration.utils_integration import read_yaml_file, yaml_setup

CALENDAR1 = "calendar.test_calendar1"
CALENDAR1_DECLINED = "calendar.test_calendar1_declined"
CALENDAR1_SHOW_AS = "calendar.test_calendar1_show_as"
SERVICE_TIME = "%Y-%m-%dT%H:%M:%SZ"
OUTSIDE_START = "2022-03-22T20:00:00.000Z"
OUTSIDE_END = "2022-03-22T22:00:00.000Z"
FILTERS_YAML = "ms365_calendars_response_filters"
# The response of each event in calendar1_calendar_view_responses
RESPONSES = {
    "Accepted meeting": "accepted",
    "Declined meeting": "declined",
    "Tentative meeting": "tentatively_accepted",
    "Unanswered meeting": "not_responded",
    "Holiday": "organizer",
    "Working from home": None,
}
ENTITY = {"name": "Calendar1", "device_id": "Calendar1", "track": True}


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


async def test_filters_off_by_default(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a calendar added to the file shows every event, as before."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry)

    entity = read_yaml_file(tmp_path)[0]["entities"][0]
    assert "exclude_declined" not in entity
    assert "show_as_exclude" not in entity

    data = hass.states.get(CALENDAR1).attributes["data"]
    assert _summaries(data) == sorted(RESPONSES)
    for start, end in (_window(), (OUTSIDE_START, OUTSIDE_END)):
        events = await _get_events(hass, CALENDAR1, start, end)
        assert _summaries(events) == sorted(RESPONSES)


async def test_exclude_declined(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test exclude_declined hides the events you declined, and only those."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry, FILTERS_YAML)
    shown = sorted(set(RESPONSES) - {"Declined meeting"})

    data = hass.states.get(CALENDAR1_DECLINED).attributes["data"]
    assert _summaries(data) == shown
    data = hass.states.get(CALENDAR1).attributes["data"]
    assert "Declined meeting" in _summaries(data)

    # In the synced window and in a range fetched from MS Graph
    for start, end in (_window(), (OUTSIDE_START, OUTSIDE_END)):
        events = await _get_events(hass, CALENDAR1_DECLINED, start, end)
        assert _summaries(events) == shown
        events = await _get_calendar_events(hass, CALENDAR1_DECLINED, start, end)
        assert _summaries(events) == shown
        events = await _get_events(hass, CALENDAR1, start, end)
        assert _summaries(events) == sorted(RESPONSES)


async def test_show_as_exclude(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test show_as_exclude hides the events shown as one of its values."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry, FILTERS_YAML)
    # Set to workingElsewhere and oof; the declined event shows as free
    shown = sorted(set(RESPONSES) - {"Holiday", "Working from home"})

    data = hass.states.get(CALENDAR1_SHOW_AS).attributes["data"]
    assert _summaries(data) == shown
    data = hass.states.get(CALENDAR1).attributes["data"]
    assert _summaries(data) == sorted(RESPONSES)

    # In the synced window and in a range fetched from MS Graph
    for start, end in (_window(), (OUTSIDE_START, OUTSIDE_END)):
        events = await _get_events(hass, CALENDAR1_SHOW_AS, start, end)
        assert _summaries(events) == shown
        events = await _get_calendar_events(hass, CALENDAR1_SHOW_AS, start, end)
        assert _summaries(events) == shown
        events = await _get_events(hass, CALENDAR1, start, end)
        assert _summaries(events) == sorted(RESPONSES)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("free", [EventShowAs.Free]),
        (["tentative", "busy"], [EventShowAs.Tentative, EventShowAs.Busy]),
        ("oof", [EventShowAs.Oof]),
        ("workingElsewhere", [EventShowAs.WorkingElsewhere]),
        ("unknown", [EventShowAs.Unknown]),
        # As shown in the show_as field of the data
        ("WorkingElsewhere", [EventShowAs.WorkingElsewhere]),
    ],
)
async def test_show_as_exclude_values(value, expected) -> None:
    """Test the show as values of MS Graph are accepted."""
    entity = YAML_CALENDAR_ENTITY_SCHEMA({**ENTITY, "show_as_exclude": value})
    assert entity["show_as_exclude"] == expected


@pytest.mark.parametrize(
    "settings",
    [
        {"show_as_exclude": ["away"]},
        {"show_as_exclude": ["busy", "BUSY"]},
        {"show_as_exclude": [""]},
        {"show_as_exclude": [None]},
        {"exclude_declined": "maybe"},
    ],
)
async def test_bad_settings_rejected(settings) -> None:
    """Test a show as value MS Graph does not have, or a declined setting, is rejected."""
    with pytest.raises(Invalid):
        YAML_CALENDAR_ENTITY_SCHEMA({**ENTITY, **settings})


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


async def _get_events(hass: HomeAssistant, entity_id, start, end):
    """Get the events with the core calendar service."""
    result = await hass.services.async_call(
        CALENDAR_DOMAIN,
        SERVICE_GET_EVENTS,
        {"entity_id": entity_id, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return result[entity_id]["events"]


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


def _summaries(events):
    """Get the sorted titles of the events."""
    return sorted(event["summary"] for event in events)
