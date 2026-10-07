"""Calendar utilities processes."""

from datetime import datetime, time
import logging
import warnings
from zoneinfo import ZoneInfoNotFoundError

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from dateutil import parser
from dateutil.rrule import rrulestr

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util, slugify
from O365.calendar import Attendee  # pylint: disable=no-name-in-module)
from O365.utils.casing import (  # pylint: disable=no-name-in-module, import-error
    to_snake_case,
)
from O365.utils.windows_tz import (  # pylint: disable=no-name-in-module, import-error
    get_windows_tz,
)

from ..classes.config_entry import MS365ConfigEntry
from ..const import CONF_ENTITY_NAME
from .const_integration import (
    ATTR_ATTENDEES,
    ATTR_BODY,
    ATTR_BODY_IS_TEXT,
    ATTR_CATEGORIES,
    ATTR_IS_ALL_DAY,
    ATTR_IS_REMINDER_ON,
    ATTR_LOCATION,
    ATTR_REMIND_BEFORE_MINUTES,
    ATTR_RRULE,
    ATTR_SENSITIVITY,
    ATTR_SHOW_AS,
    CALENDAR_ENTITY_ID_FORMAT,
    DAYS,
    DOMAIN,
    INDEXES,
    LOCATION_ADDRESS,
    RRULE_FREQUENCIES,
    RRULE_PARTS,
)

_LOGGER = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def clean_html(html):
    """Clean the HTML."""
    soup = BeautifulSoup(html, features="html.parser")
    if body := soup.find("body"):
        # get text
        text = body.get_text()

        # break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # drop blank lines
        text = "\n".join(chunk for chunk in chunks if chunk)
        return text.replace("\xa0", " ")

    return html


def format_event_data(event):
    """Format the event data."""
    attendees = event.attendees._Attendees__attendees  # noqa: SLF001
    return {
        "summary": event.subject or "",
        "start": get_hass_date(event.start, event.is_all_day),
        "end": get_hass_date(get_end_date(event), event.is_all_day),
        "all_day": event.is_all_day,
        "description": clean_html(event.body),
        "location": event.location["displayName"],
        "location_details": _location_details(event.location),
        "locations": _locations(event.locations),
        "categories": event.categories,
        "sensitivity": event.sensitivity.name,
        "show_as": event.show_as.name,
        "reminder": {
            "minutes": event.remind_before_minutes,
            "is_on": event.is_reminder_on,
        },
        "organizer": event.organizer.address,
        "response": event.response_status.status.value
        if event.response_status.status
        else None,
        "attendees": [
            {
                "email": x.address,
                "type": x.attendee_type.value,
                "status": x.response_status.status.value
                if x.response_status.status
                else None,
            }
            for x in attendees
        ],
        "uid": event.object_id,
    }


def _location_details(location):
    """Get what MS Graph has on a place beyond its name, leaving out empty parts."""
    # A place typed in as text has the default type, which tells nothing more
    location_type = to_snake_case(location.get("locationType") or "default")
    details = {
        "address": _location_address(location.get("address") or {}),
        "coordinates": _location_coordinates(location.get("coordinates") or {}),
        "type": None if location_type == "default" else location_type,
        "email": location.get("locationEmailAddress"),
        "uri": location.get("locationUri"),
    }
    return {key: value for key, value in details.items() if value} or None


def _location_address(address):
    return {
        key: address[graph_key]
        for key, graph_key in LOCATION_ADDRESS.items()
        if address.get(graph_key)
    }


def _location_coordinates(coordinates):
    latitude = coordinates.get("latitude")
    longitude = coordinates.get("longitude")
    # A place without coordinates can come with 0, 0, which is not a real place
    if latitude is None or longitude is None or latitude == longitude == 0:
        return None
    return {"latitude": latitude, "longitude": longitude}


def _locations(locations):
    """Get each place of an event held in several.

    The location of such an event is only their names joined, while for one place
    the location and its details already say it all.
    """
    if len(locations or []) < 2:
        return None
    return [
        {"name": place.get("displayName", ""), **(_location_details(place) or {})}
        for place in locations
    ]


def get_hass_date(obj, is_all_day):
    """Get the date."""
    return obj if isinstance(obj, datetime) and not is_all_day else obj.date()


def get_end_date(obj):
    """Get the end date."""
    return obj.end


def get_start_date(obj):
    """Get the start date."""
    return obj.start


def add_call_data_to_event(event, subject, start, end, **kwargs):
    """Add the call data.

    Only what is supplied is set. O365 sends every attribute that has been set, even
    to its current value, so anything else is left out of an update.
    """
    is_all_day = _is_all_day(kwargs.get(ATTR_IS_ALL_DAY), event, start, end)
    _add_attribute(event, "subject", subject)
    _add_body(kwargs.get(ATTR_BODY), kwargs.get(ATTR_BODY_IS_TEXT, False), event)
    _add_location(kwargs.get(ATTR_LOCATION), event)
    _add_attribute(event, "categories", kwargs.get(ATTR_CATEGORIES))
    _add_attribute(event, "show_as", kwargs.get(ATTR_SHOW_AS))
    _add_attribute(event, "start", start)
    _add_attribute(event, "end", end)
    _add_attribute(event, "is_reminder_on", kwargs.get(ATTR_IS_REMINDER_ON))
    if event.is_reminder_on:
        _add_attribute(
            event, "remind_before_minutes", kwargs.get(ATTR_REMIND_BEFORE_MINUTES)
        )
    _add_attribute(event, "sensitivity", kwargs.get(ATTR_SENSITIVITY))
    _add_attendees(kwargs.get(ATTR_ATTENDEES, []), event)
    _add_all_day(is_all_day, event)

    if rrule := kwargs.get(ATTR_RRULE):
        _validate_rrule(rrule)
        _rrule_processing(event, rrule)
    return event


def is_unchanged_text(text, body):
    """Check if text from the HA calendar is just the text of the body."""
    return text is not None and text.strip() == clean_html(body).strip()


def _add_attribute(event, name, value):
    if value is not None:
        setattr(event, name, value)


def _add_body(body, body_is_text, event):
    if body is None:
        return
    if body_is_text:
        # The HA calendar only has the text from clean_html, so writing it back
        # unchanged would replace the HTML body and lose its links and formatting
        if is_unchanged_text(body, event.body):
            return
        event.body_type = "text"
    event.body = body


def _add_location(location, event):
    # Only a name can be given, and Graph replaces the whole location (and any other
    # locations, such as a room) when it is set, so an unchanged name is not sent
    if location is not None and location != event.location.get("displayName"):
        event.location = location


def _is_all_day(is_all_day, event, start, end):
    """Work out the all day setting when the caller did not give one."""
    if is_all_day is not None or not event.is_all_day:
        return is_all_day
    # Times of day on an all day event mean it is moving to a timed slot
    for value in (start, end):
        if isinstance(value, datetime) and dt_util.as_local(value).time() != time():
            return False
    return None


def _add_attendees(attendees, event):
    if attendees:
        event.attendees.clear()
        event.attendees.add(
            [
                Attendee(x["email"], attendee_type=x["type"], event=event)
                for x in attendees
            ]
        )


def _add_all_day(is_all_day, event):
    if is_all_day is not None:
        event.is_all_day = is_all_day
        if event.is_all_day:
            event.start = datetime(
                event.start.year,
                event.start.month,
                event.start.day,
                0,
                0,
                0,
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )
            event.end = datetime(
                event.end.year,
                event.end.month,
                event.end.day,
                0,
                0,
                0,
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )


def _validate_rrule(rrule):
    """Refuse a repeat rule that _rrule_processing would not create as written.

    The rule is parsed as the HA calendar parses it. MS Graph only has some kinds of
    series, so anything else is refused rather than creating a different series.
    """
    rules = {}
    for item in rrule.split(";"):
        key, _, value = item.partition("=")
        rules[key] = value
    if "FREQ" not in rules:
        raise _rrule_error("rrule_no_freq", rrule)
    try:
        rrulestr(rrule)
    except ValueError as err:
        raise _rrule_error("rrule_invalid", rrule, error=str(err)) from err
    if part := _unsupported_rrule_part(rules):
        raise _rrule_error("rrule_not_supported", rrule, part=part)


def _rrule_error(translation_key, rrule, **placeholders):
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
        translation_placeholders={"rrule": rrule, **placeholders},
    )


def _unsupported_rrule_part(rules):
    """Get the part of a valid rule that _rrule_processing would not follow."""
    for key, value in rules.items():
        if key not in RRULE_PARTS:
            return f"{key}={value}"
    if rules["FREQ"] not in RRULE_FREQUENCIES:
        return f"FREQ={rules['FREQ']}"
    for key in ("INTERVAL", "COUNT"):
        # O365 leaves out 0, and MS Graph refuses less
        if int(rules.get(key, 1)) < 1:
            return f"{key}={rules[key]}"
    if "COUNT" in rules and "UNTIL" in rules:
        # RFC 5545 does not allow both, and O365 would drop the count
        return f"COUNT={rules['COUNT']};UNTIL={rules['UNTIL']}"
    return _unsupported_rrule_days(rules)


def _unsupported_rrule_days(rules):
    """Get the BYDAY or BYMONTHDAY that _rrule_processing would not follow.

    A weekly series repeats on days of the week, and a monthly series on one day of
    the week in a given week or on one day of the month. A yearly series repeats on
    the date it starts on, and a daily series every day.
    """
    freq = rules["FREQ"]
    if "BYDAY" in rules and "BYMONTHDAY" in rules:
        return f"BYDAY={rules['BYDAY']};BYMONTHDAY={rules['BYMONTHDAY']}"
    if "BYDAY" in rules and not _is_supported_byday(freq, rules["BYDAY"]):
        return f"FREQ={freq};BYDAY={rules['BYDAY']}"
    if "BYMONTHDAY" in rules and not (
        freq == "MONTHLY" and _is_day_of_month(rules["BYMONTHDAY"])
    ):
        return f"FREQ={freq};BYMONTHDAY={rules['BYMONTHDAY']}"
    return None


def _is_supported_byday(freq, byday):
    """Check the days are ones _process_byday reads for the frequency."""
    days = [(item[:-2], item[-2:]) for item in byday.split(",")]
    if any(day not in DAYS for _, day in days):
        return False
    if freq == "WEEKLY":
        return not any(index for index, _ in days)
    # Outlook repeats one day a month, in the first to the fourth or the last week
    return freq == "MONTHLY" and len(days) == 1 and days[0][0] in INDEXES


def _is_day_of_month(bymonthday):
    """Check it is one day of the month, or -1 that _rrule_processing reads as last."""
    return "," not in bymonthday and (bymonthday == "-1" or 1 <= int(bymonthday) <= 31)


def _rrule_processing(event, rrule):
    rules = {}
    for item in rrule.split(";"):
        keys = item.split("=")
        rules[keys[0]] = keys[1]

    # Without a start date, O365 starts the series today rather than on the event
    kwargs = {"start": _local_date(event.start, event.is_all_day)}
    if "COUNT" in rules:
        kwargs["occurrences"] = int(rules["COUNT"])
    if "UNTIL" in rules:
        kwargs["end"] = _local_date(parser.parse(rules["UNTIL"]), False)
    interval = int(rules["INTERVAL"]) if "INTERVAL" in rules else 1
    if "BYDAY" in rules:
        days, index = _process_byday(rules["BYDAY"])
        kwargs["days_of_week"] = days
        if index:
            kwargs["index"] = index

    if rules["FREQ"] == "YEARLY":
        kwargs["day_of_month"] = event.start.day
        event.recurrence.set_yearly(interval, event.start.month, **kwargs)

    if rules["FREQ"] == "MONTHLY":
        if rules.get("BYMONTHDAY") == "-1":
            # Outlook's 'last day of the month' is the last of any day of the week
            kwargs["days_of_week"] = list(DAYS.values())
            kwargs["index"] = "last"
        elif "BYDAY" not in rules:
            kwargs["day_of_month"] = int(rules.get("BYMONTHDAY", event.start.day))
        event.recurrence.set_monthly(interval, **kwargs)

    if rules["FREQ"] == "WEEKLY":
        kwargs["first_day_of_week"] = "sunday"
        # Without BYDAY the series repeats on the day of the week it starts on
        weekday = list(DAYS.values())[kwargs["start"].weekday()]
        kwargs.setdefault("days_of_week", [weekday])
        event.recurrence.set_weekly(interval, **kwargs)

    if rules["FREQ"] == "DAILY":
        event.recurrence.set_daily(interval, **kwargs)

    # The range dates are local dates, so Graph has to read them in the local zone
    try:
        event.recurrence.recurrence_time_zone = get_windows_tz(
            dt_util.get_default_time_zone()
        )
    except ZoneInfoNotFoundError:
        _LOGGER.debug(
            "No Windows time zone for %s, recurrence time zone left unchanged",
            dt_util.get_default_time_zone(),
        )


def _local_date(value, is_all_day):
    """Get the date as HA shows it; all day and naive values are already local."""
    if is_all_day or value.tzinfo is None:
        return value.date()
    return dt_util.as_local(value).date()


def _process_byday(byday):
    days = []
    for item in byday.split(","):
        if len(item) > 2:
            days.append(DAYS[item[2:4]])
            index = INDEXES[item[:2]]
        else:
            days.append(DAYS[item[:2]])
            index = None
    return days, index


def build_calendar_entity_id(device_id, entity_name):
    """Build calendar entity_id."""
    name = f"{entity_name}_{device_id}"
    return CALENDAR_ENTITY_ID_FORMAT.format(slugify(name))


def build_calendar_unique_id(cal_id, device_id, entity_name):
    """Build calendar unique_id."""
    return f"{cal_id}_{entity_name}_{device_id}"


async def async_delete_calendar(
    hass: HomeAssistant, config_entry: MS365ConfigEntry, cal_id, device_id
):
    """Delete a calendar."""
    unique_id = build_calendar_unique_id(
        cal_id, device_id, config_entry.data[CONF_ENTITY_NAME]
    )
    ent_reg = er.async_get(hass)
    # Found by unique id, as the user can change the entity id
    if entity_id := ent_reg.async_get_entity_id(Platform.CALENDAR, DOMAIN, unique_id):
        ent_reg.async_remove(entity_id)
