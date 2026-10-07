# pylint: disable=unused-argument,line-too-long
"""Test the repeat rules of created and updated events."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from requests_mock import Mocker
from voluptuous.error import MultipleInvalid

from ..helpers.utils import mock_call
from .const_integration import DOMAIN, URL
from .fixtures import ClientFixture

CALENDAR_NAME = "calendar.test_calendar1"
EVENT_NAME = "event1"
TIME_ZONE = "Pacific Standard Time"
EVERY_DAY = [
    "friday",
    "monday",
    "saturday",
    "sunday",
    "thursday",
    "tuesday",
    "wednesday",
]


def _all_day(start, end):
    return {"start": f"{start}T00:00:00", "end": f"{end}T00:00:00", "is_all_day": True}


def _timed(start, end):
    return {"start": start, "end": end}


def _posted_event(mock_save):
    """Get the event that creating it posts to MS Graph."""
    payload = mock_save.call_args.args[0].to_api_data()
    if days := payload.get("recurrence", {}).get("pattern", {}).get("daysOfWeek"):
        # O365 keeps the days in a set, so they are sent in any order
        days.sort()
    return payload


async def _async_create_event(hass, data):
    """Call the create service."""
    await hass.services.async_call(
        DOMAIN,
        "create_calendar_event",
        {"entity_id": CALENDAR_NAME, "subject": "Repeating", **data},
        blocking=True,
        return_response=False,
    )


@pytest.mark.parametrize(
    ("event", "rrule", "pattern", "recurrence_range"),
    [
        # 18:00 on Monday is already Tuesday in UTC, the series starts on Monday
        (
            _timed("2099-01-05T18:00:00-08:00", "2099-01-05T19:00:00-08:00"),
            "FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
            {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": ["monday", "wednesday"],
                "firstDayOfWeek": "sunday",
            },
            {"type": "numbered", "startDate": "2099-01-05", "numberOfOccurrences": 10},
        ),
        (
            _all_day("2099-01-06", "2099-01-07"),
            "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH;UNTIL=20990331",
            {
                "type": "weekly",
                "interval": 2,
                "daysOfWeek": ["thursday", "tuesday"],
                "firstDayOfWeek": "sunday",
            },
            {"type": "endDate", "startDate": "2099-01-06", "endDate": "2099-03-31"},
        ),
        (
            _timed("2099-02-10T09:00:00-08:00", "2099-02-10T10:00:00-08:00"),
            "FREQ=MONTHLY;BYDAY=+2TU",
            {
                "type": "relativeMonthly",
                "interval": 1,
                "daysOfWeek": ["tuesday"],
                "index": "second",
            },
            {"type": "noEnd", "startDate": "2099-02-10"},
        ),
        # 05:00 UTC on 1 December is still 30 November in US/Pacific
        (
            _timed("2099-01-30T17:00:00-08:00", "2099-01-30T18:00:00-08:00"),
            "FREQ=MONTHLY;BYDAY=-1FR;UNTIL=20991201T050000Z",
            {
                "type": "relativeMonthly",
                "interval": 1,
                "daysOfWeek": ["friday"],
                "index": "last",
            },
            {"type": "endDate", "startDate": "2099-01-30", "endDate": "2099-11-30"},
        ),
        (
            _timed("2099-04-15T09:00:00-07:00", "2099-04-15T10:00:00-07:00"),
            "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=15",
            {"type": "absoluteMonthly", "interval": 3, "dayOfMonth": 15},
            {"type": "noEnd", "startDate": "2099-04-15"},
        ),
        # Outlook's last day of the month is the last of any day of the week
        (
            _all_day("2099-01-31", "2099-02-01"),
            "FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=12",
            {
                "type": "relativeMonthly",
                "interval": 1,
                "daysOfWeek": EVERY_DAY,
                "index": "last",
            },
            {"type": "numbered", "startDate": "2099-01-31", "numberOfOccurrences": 12},
        ),
        (
            _all_day("2099-04-15", "2099-04-16"),
            "FREQ=YEARLY;COUNT=5",
            {"type": "absoluteYearly", "interval": 1, "dayOfMonth": 15, "month": 4},
            {"type": "numbered", "startDate": "2099-04-15", "numberOfOccurrences": 5},
        ),
        (
            _timed("2099-01-05T07:00:00-08:00", "2099-01-05T07:30:00-08:00"),
            "FREQ=DAILY;INTERVAL=3;UNTIL=20990120T060000Z",
            {"type": "daily", "interval": 3},
            {"type": "endDate", "startDate": "2099-01-05", "endDate": "2099-01-19"},
        ),
        # A rule written as a YAML block ends in a line break
        (
            _timed("2099-01-05T18:00:00-08:00", "2099-01-05T19:00:00-08:00"),
            "FREQ=WEEKLY;BYDAY=MO,WE\n",
            {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": ["monday", "wednesday"],
                "firstDayOfWeek": "sunday",
            },
            {"type": "noEnd", "startDate": "2099-01-05"},
        ),
    ],
)
async def test_create_event_with_rrule(
    hass: HomeAssistant,
    setup_update_integration,
    event,
    rrule,
    pattern,
    recurrence_range,
) -> None:
    """Test create event - MS365 service sends the series the rule describes."""
    with patch("O365.calendar.Event.save", autospec=True) as mock_save:
        await _async_create_event(hass, {**event, "rrule": rrule})

    payload = _posted_event(mock_save)
    assert payload["isAllDay"] is event.get("is_all_day", False)
    assert payload["recurrence"]["pattern"] == pattern
    assert payload["recurrence"]["range"] == {
        **recurrence_range,
        "recurrenceTimeZone": TIME_ZONE,
    }


@pytest.mark.parametrize("data", [{}, {"rrule": ""}, {"rrule": "\n"}])
async def test_create_event_without_rrule(
    hass: HomeAssistant,
    setup_update_integration,
    data,
) -> None:
    """Test create event - MS365 service without a rule creates a single event."""
    with patch("O365.calendar.Event.save", autospec=True) as mock_save:
        await _async_create_event(
            hass,
            {
                **_timed("2099-01-05T18:00:00-08:00", "2099-01-05T19:00:00-08:00"),
                **data,
            },
        )

    payload = _posted_event(mock_save)
    assert "recurrence" not in payload
    assert payload["start"] == {
        "dateTime": "2099-01-05T18:00:00",
        "timeZone": TIME_ZONE,
    }


@pytest.mark.parametrize(
    ("rrule", "part"),
    [
        ("FREQ=HOURLY", "FREQ=HOURLY"),
        ("FREQ=weekly", "FREQ=weekly"),
        ("FREQ=WEEKLY;byday=MO", "byday=MO"),
        ("FREQ=MONTHLY;BYDAY=MO,TU,WE,TH,FR;BYSETPOS=-1", "BYSETPOS=-1"),
        ("FREQ=YEARLY;BYMONTH=1,7", "BYMONTH=1,7"),
        ("FREQ=YEARLY;BYMONTH=6", "BYMONTH=6"),
        ("FREQ=DAILY;BYHOUR=9", "BYHOUR=9"),
        ("FREQ=WEEKLY;BYDAY=SU,MO;WKST=MO", "WKST=MO"),
        ("FREQ=WEEKLY;INTERVAL=0", "INTERVAL=0"),
        ("FREQ=DAILY;COUNT=0", "COUNT=0"),
        ("FREQ=DAILY;COUNT=5;UNTIL=20991231", "COUNT=5;UNTIL=20991231"),
        ("FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR", "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR"),
        ("FREQ=WEEKLY;BYDAY=+1MO", "FREQ=WEEKLY;BYDAY=+1MO"),
        ("FREQ=WEEKLY;BYDAY=mo", "FREQ=WEEKLY;BYDAY=mo"),
        ("FREQ=MONTHLY;BYDAY=MO", "FREQ=MONTHLY;BYDAY=MO"),
        ("FREQ=MONTHLY;BYDAY=+1MO,+3MO", "FREQ=MONTHLY;BYDAY=+1MO,+3MO"),
        ("FREQ=MONTHLY;BYDAY=+5FR", "FREQ=MONTHLY;BYDAY=+5FR"),
        ("FREQ=MONTHLY;BYDAY=1FR", "FREQ=MONTHLY;BYDAY=1FR"),
        ("FREQ=YEARLY;BYDAY=-1SU", "FREQ=YEARLY;BYDAY=-1SU"),
        ("FREQ=MONTHLY;BYMONTHDAY=1,15", "FREQ=MONTHLY;BYMONTHDAY=1,15"),
        ("FREQ=MONTHLY;BYMONTHDAY=-2", "FREQ=MONTHLY;BYMONTHDAY=-2"),
        ("FREQ=WEEKLY;BYMONTHDAY=15", "FREQ=WEEKLY;BYMONTHDAY=15"),
        ("FREQ=MONTHLY;BYDAY=FR;BYMONTHDAY=13", "BYDAY=FR;BYMONTHDAY=13"),
    ],
)
async def test_create_event_rrule_not_supported(
    hass: HomeAssistant,
    setup_update_integration,
    rrule,
    part,
) -> None:
    """Test create event - a rule MS365 would change is refused, naming the part."""
    with (
        patch("O365.calendar.Event.save", autospec=True) as mock_save,
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        await _async_create_event(
            hass,
            {
                **_timed("2099-01-05T18:00:00-08:00", "2099-01-05T19:00:00-08:00"),
                "rrule": rrule,
            },
        )

    assert (
        str(exc_info.value)
        == f"Repeat rule {rrule} cannot be created in MS365: {part} is not supported"
    )
    assert not mock_save.called


@pytest.mark.parametrize(
    ("rrule", "message"),
    [
        (
            "COUNT=10",
            "Repeat rule COUNT=10 has no FREQ. Give the rule without RRULE: in front, such as FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
        ),
        (
            "RRULE:FREQ=DAILY",
            "Repeat rule RRULE:FREQ=DAILY has no FREQ. Give the rule without RRULE: in front, such as FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
        ),
        (
            "FREQ=WEEKLY;BYDAY=XX",
            "Repeat rule FREQ=WEEKLY;BYDAY=XX is not valid: invalid 'BYDAY': XX",
        ),
        (
            "FREQ=DAILY;COUNT=ten",
            "Repeat rule FREQ=DAILY;COUNT=ten is not valid: invalid 'COUNT': TEN",
        ),
        (
            "FREQ=DAILY;UNTIL=someday",
            "Repeat rule FREQ=DAILY;UNTIL=someday is not valid: invalid 'UNTIL': SOMEDAY",
        ),
        # dateutil reads what follows a space as another rule, which has no FREQ
        (
            "FREQ=WEEKLY BYDAY=MO",
            "Repeat rule FREQ=WEEKLY BYDAY=MO has a space or line break in it. Separate its parts with ; and no spaces, such as FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
        ),
        (
            "FREQ=WEEKLY;COUNT=10\nBYDAY=MO,WE",
            "Repeat rule FREQ=WEEKLY;COUNT=10\nBYDAY=MO,WE has a space or line break in it. Separate its parts with ; and no spaces, such as FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
        ),
        (
            "FREQ=DAILY;INTERVAL=2 FREQ=WEEKLY",
            "Repeat rule FREQ=DAILY;INTERVAL=2 FREQ=WEEKLY has a space or line break in it. Separate its parts with ; and no spaces, such as FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10",
        ),
    ],
)
async def test_create_event_rrule_invalid(
    hass: HomeAssistant,
    setup_update_integration,
    rrule,
    message,
) -> None:
    """Test create event - a rule that does not parse is refused."""
    with (
        patch("O365.calendar.Event.save", autospec=True) as mock_save,
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        await _async_create_event(
            hass,
            {**_all_day("2099-01-05", "2099-01-06"), "rrule": rrule},
        )

    assert str(exc_info.value) == message
    assert not mock_save.called


async def test_create_event_rrule_out_of_range(
    hass: HomeAssistant,
    setup_update_integration,
) -> None:
    """Test create event - a date too large to read is refused as not valid."""
    rrule = "FREQ=DAILY;UNTIL=99999999999999999999"
    with (
        patch("O365.calendar.Event.save", autospec=True) as mock_save,
        pytest.raises(ServiceValidationError) as exc_info,
    ):
        await _async_create_event(
            hass,
            {**_all_day("2099-01-05", "2099-01-06"), "rrule": rrule},
        )

    # The reason is Python's own text, which differs between versions
    assert str(exc_info.value).startswith(f"Repeat rule {rrule} is not valid: ")
    assert not mock_save.called


async def test_modify_event_has_no_rrule(
    hass: HomeAssistant,
    setup_update_integration,
    requests_mock: Mocker,
) -> None:
    """Test modify event - MS365 service does not change the repeat of a series."""
    mock_call(
        requests_mock,
        URL.CALENDARS,
        "calendar1_event1",
        f"calendar1/events/{EVENT_NAME}",
    )

    with (
        patch("O365.calendar.Event.save", autospec=True) as mock_save,
        pytest.raises(MultipleInvalid),
    ):
        await hass.services.async_call(
            DOMAIN,
            "modify_calendar_event",
            {
                "entity_id": CALENDAR_NAME,
                "event_id": EVENT_NAME,
                "rrule": "FREQ=DAILY;COUNT=5",
            },
            blocking=True,
            return_response=False,
        )

    assert not mock_save.called


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("create", {}),
        ("update", {"uid": EVENT_NAME}),
    ],
)
async def test_ui_rrule_not_supported(
    ws_client: ClientFixture,
    setup_update_integration,
    requests_mock: Mocker,
    command,
    payload,
) -> None:
    """Test create and update event - HA API call refuses a rule MS365 would change.

    The calendar panel only makes rules MS365 supports, but the HA API takes any.
    """
    mock_call(
        requests_mock,
        URL.CALENDARS,
        "calendar1_event1",
        f"calendar1/events/{EVENT_NAME}",
    )
    client = await ws_client()
    with patch("O365.calendar.Event.save", autospec=True) as mock_save:
        resp = await client.cmd(
            command,
            {
                "entity_id": CALENDAR_NAME,
                **payload,
                "event": {
                    "summary": "Gym",
                    "dtstart": "2099-01-05T18:00:00",
                    "dtend": "2099-01-05T19:00:00",
                    "rrule": "FREQ=MONTHLY;BYDAY=MO",
                },
            },
        )

    assert not resp["success"]
    assert resp["error"]["message"] == (
        "Repeat rule FREQ=MONTHLY;BYDAY=MO cannot be created in MS365: "
        "FREQ=MONTHLY;BYDAY=MO is not supported"
    )
    assert not mock_save.called
