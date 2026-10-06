# pylint: disable=unused-argument,line-too-long,wrong-import-order
"""Test syncing, refreshing and keeping of calendar events."""

import json
import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.components.calendar import SERVICE_GET_EVENTS
from homeassistant.const import EVENT_HOMEASSISTANT_FINAL_WRITE, EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from requests.exceptions import HTTPError
from requests_mock import Mocker

from ..helpers.mock_config_entry import MS365MockConfigEntry
from ..helpers.utils import check_entity_state, load_json, mock_call, utcnow
from .const_integration import DOMAIN, URL
from .helpers_integration.mocks import MS365MOCKS

CALENDAR1 = "calendar.test_calendar1"
CALENDAR1_VIEW = f"{URL.CALENDARS.value}/calendar1/calendarView"
GRAPH_TIME = "%Y-%m-%dT%H:%M:%S.0000000"
SERVICE_TIME = "%Y-%m-%dT%H:%M:%SZ"
OUTSIDE_START = "2022-03-22T20:00:00.000Z"
OUTSIDE_END = "2022-03-22T22:00:00.000Z"


async def test_entities_start_with_events(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the events are fetched before the entities are added."""
    MS365MOCKS.standard_mocks(requests_mock)
    first_states = {}

    @callback
    def _first_state(event: Event) -> None:
        if event.data["old_state"] is None:
            first_states[event.data["entity_id"]] = event.data["new_state"]

    hass.bus.async_listen(EVENT_STATE_CHANGED, _first_state)
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)

    # Something that reads the events as soon as setup is done, such as a
    # calendar trigger, gets them
    coordinator = base_config_entry.runtime_data.coordinator[0]
    events = await coordinator.async_get_events(
        dt_util.utcnow() - timedelta(hours=1), dt_util.utcnow() + timedelta(hours=1)
    )
    assert sorted(event.object_id for event in events) == ["event1", "event2"]

    await hass.async_block_till_done()
    first_state = first_states[CALENDAR1]
    assert first_state.state == "on"
    assert first_state.attributes["message"] == "Test event 1 calendar1"
    assert len(first_state.attributes["data"]) == 2


async def test_next_event_when_event_ends(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the meeting that follows is shown when one ends, without an update."""
    now = dt_util.utcnow().replace(microsecond=0)
    MS365MOCKS.no_events_mocks(requests_mock)
    calendar_view = requests_mock.get(
        CALENDAR1_VIEW,
        text=_calendar_view(
            "calendar1_calendar_view_back_to_back",
            [
                (now - timedelta(minutes=30), now + timedelta(seconds=30)),
                (now + timedelta(seconds=30), now + timedelta(hours=1)),
            ],
        ),
    )
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()
    check_entity_state(hass, CALENDAR1, "on", attributes={"message": "First meeting"})
    syncs = calendar_view.call_count

    # Only the alarm at the end of the first meeting runs, the next update is later
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    check_entity_state(hass, CALENDAR1, "on", attributes={"message": "Second meeting"})
    assert calendar_view.call_count == syncs


async def test_cancelled_meeting_left_out(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a meeting the organizer cancelled is not shown."""
    MS365MOCKS.no_events_mocks(requests_mock)
    mock_call(
        requests_mock,
        URL.CALENDARS,
        "calendar1_calendar_view_cancelled",
        "calendar1/calendarView",
        start=(utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
        end=(utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    calendar_view = next(
        request
        for request in requests_mock.request_history
        if "calendarview" in request.url.lower()
    )
    assert "iscancelled" in calendar_view.qs["$select"][0].lower()

    # The cancelled meeting is on now, but the entity is off and does not list it
    check_entity_state(hass, CALENDAR1, "off", data_length=0)
    assert hass.states.get(CALENDAR1).attributes.get("message") is None
    now = dt_util.utcnow()
    assert (
        await _get_events(
            hass,
            (now - timedelta(hours=1)).strftime(SERVICE_TIME),
            (now + timedelta(hours=1)).strftime(SERVICE_TIME),
        )
        == []
    )

    # A range fetched from MS Graph keeps the live event only
    events = await _get_events(
        hass, "2099-01-01T00:00:00.000Z", "2099-01-02T00:00:00.000Z"
    )
    assert [event["summary"] for event in events] == ["Test live event"]


async def test_events_on_every_page(
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the events on the pages after the first are used too."""
    MS365MOCKS.no_events_mocks(requests_mock)
    dates = {
        "start": (utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
        "end": (utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    mock_call(
        requests_mock,
        URL.CALENDARS,
        "calendar1_calendar_view_page1",
        "calendar1/calendarView",
        **dates,
    )
    mock_call(
        requests_mock,
        URL.CALENDARS,
        "calendar1_calendar_view_page2",
        "calendar1/calendarView?$skip=999",
        **dates,
    )
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    data = hass.states.get(CALENDAR1).attributes["data"]
    assert sorted(item["uid"] for item in data) == ["event1", "event_page2"]

    events = await _get_events(hass, OUTSIDE_START, OUTSIDE_END)
    assert sorted(event["summary"] for event in events) == [
        "Test event page 1",
        "Test event page 2",
    ]


async def test_range_outside_window_kept(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    setup_base_integration,
    requests_mock: Mocker,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a range outside the synced window is fetched once and kept a while."""
    first = await _get_events(hass, OUTSIDE_START, OUTSIDE_END)
    assert len(first) == 2
    assert await _get_events(hass, OUTSIDE_START, OUTSIDE_END) == first
    assert _range_fetches(requests_mock, "2022-03-22") == 1

    # Past the five minutes it is kept for, it is fetched again
    freezer.tick(timedelta(minutes=6))
    assert await _get_events(hass, OUTSIDE_START, OUTSIDE_END) == first
    assert _range_fetches(requests_mock, "2022-03-22") == 2

    # And straight away after a change made through the integration
    await base_config_entry.runtime_data.coordinator[0].async_refresh()
    assert await _get_events(hass, OUTSIDE_START, OUTSIDE_END) == first
    assert _range_fetches(requests_mock, "2022-03-22") == 3


async def test_range_outside_window_error(
    hass: HomeAssistant,
    setup_base_integration,
) -> None:
    """Test a failed fetch of a range the synced window does not cover is an error."""
    with (
        patch("O365.calendar.Calendar.get_events", side_effect=HTTPError()),
        pytest.raises(HomeAssistantError, match="Unable to get events from MS Graph"),
    ):
        await _get_events(hass, OUTSIDE_START, OUTSIDE_END)


async def test_range_error_logged_again_after_recovery(
    hass: HomeAssistant,
    setup_base_integration,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a failure after a fetch that worked is logged as a warning again."""
    caplog.set_level(logging.WARNING)
    now = dt_util.utcnow()
    start = (now - timedelta(days=30)).strftime(SERVICE_TIME)
    end = (now + timedelta(hours=1)).strftime(SERVICE_TIME)
    with patch("O365.calendar.Calendar.get_events", side_effect=HTTPError()):
        events = await _get_events(hass, start, end)
    # The part of the range in the synced window is still returned
    assert len(events) == 2

    await _get_events(hass, OUTSIDE_START, OUTSIDE_END)
    with patch("O365.calendar.Calendar.get_events", side_effect=HTTPError()):
        await _get_events(hass, start, end)

    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and record.getMessage().startswith("Error getting calendar event range")
    ]
    assert len(warnings) == 2


async def test_failed_first_sync_after_restart(
    hass: HomeAssistant,
    hass_storage,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a failed first sync does not use the event file an older version wrote."""
    key = f"{DOMAIN}.Storage-{base_config_entry.entry_id}"
    hass_storage[key] = _old_event_file(key, "Calendar1")
    MS365MOCKS.standard_mocks(requests_mock)
    base_config_entry.add_to_hass(hass)
    with patch("O365.calendar.Calendar.get_events", side_effect=HTTPError()):
        await hass.config_entries.async_setup(base_config_entry.entry_id)
        await hass.async_block_till_done()

    check_entity_state(
        hass, CALENDAR1, "off", data_length=0, attributes={"sync_state": "problem"}
    )
    now = dt_util.utcnow()
    assert (
        await _get_events(
            hass,
            (now - timedelta(hours=2)).strftime(SERVICE_TIME),
            (now + timedelta(hours=2)).strftime(SERVICE_TIME),
        )
        == []
    )


async def test_events_not_written_to_disk(
    hass: HomeAssistant,
    hass_storage,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the events are kept in memory and the file of an older version removed."""
    key = f"{DOMAIN}.Storage-{base_config_entry.entry_id}"
    hass_storage[key] = _old_event_file(key, "Removed calendar")
    MS365MOCKS.standard_mocks(requests_mock)
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()
    assert key not in hass_storage

    # Nothing is written later either, also not when Home Assistant stops
    await base_config_entry.runtime_data.coordinator[0].async_refresh()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    assert key not in hass_storage
    check_entity_state(hass, CALENDAR1, "on", data_length=2)


async def test_no_event_file_after_removal(
    hass: HomeAssistant,
    hass_storage,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test removing the integration leaves no event file behind."""
    key = f"{DOMAIN}.Storage-{base_config_entry.entry_id}"
    await base_config_entry.runtime_data.coordinator[0].async_refresh()

    assert await hass.config_entries.async_remove(base_config_entry.entry_id)
    await hass.async_block_till_done()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_FINAL_WRITE)
    await hass.async_block_till_done()
    assert key not in hass_storage


async def _get_events(hass: HomeAssistant, start, end):
    """Get the events of calendar 1 with the calendar service."""
    result = await hass.services.async_call(
        CALENDAR_DOMAIN,
        SERVICE_GET_EVENTS,
        {"entity_id": CALENDAR1, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return result[CALENDAR1]["events"]


def _calendar_view(datafile, times):
    """Load a calendar view and give its events these start and end times."""
    data = json.loads(load_json(f"O365/{datafile}.json"))
    for event, (start, end) in zip(data["value"], times, strict=True):
        event["start"]["dateTime"] = start.strftime(GRAPH_TIME)
        event["end"]["dateTime"] = end.strftime(GRAPH_TIME)
    return json.dumps(data)


def _range_fetches(requests_mock: Mocker, day):
    """Count the calendar view requests for a range on the day."""
    return len(
        [
            request
            for request in requests_mock.request_history
            if "calendarview" in request.url.lower() and day in request.url
        ]
    )


def _old_event_file(key, name):
    """Build the event file as an older version wrote it."""
    now = dt_util.utcnow()
    return {
        "version": 1,
        "minor_version": 1,
        "key": key,
        "data": {
            name: {
                "event_sync": {
                    "calendar1": {
                        "items": {
                            "event1": {
                                "object_id": "event1",
                                "subject": "Old event",
                                "start": str(now - timedelta(hours=1)),
                                "end": str(now + timedelta(hours=1)),
                                "is_all_day": False,
                            }
                        }
                    }
                }
            }
        },
    }
