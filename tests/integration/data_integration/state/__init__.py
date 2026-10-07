"""Tests for MS365 Calendar."""

import datetime

import zoneinfo

BASE_STATE_CAL1 = [
    {
        "summary": "Test event 1 calendar1",
        "start": datetime.datetime(
            2020, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
        "end": datetime.datetime(
            2020, 1, 2, 23, 59, 59, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
        "all_day": False,
        "description": "Test",
        "location": "Test Location",
        "location_details": None,
        "locations": None,
        "categories": [],
        "sensitivity": "Normal",
        "show_as": "Busy",
        "reminder": {"minutes": 30, "is_on": True},
        "organizer": "john@nomail.com",
        "attendees": [
            {"email": "jane@nomail.com", "type": "required", "status": "not_responded"}
        ],
        "uid": "event1",
    },
    {
        "summary": "Test event 2 calendar1",
        "start": datetime.date(2020, 1, 1),
        "end": datetime.date(2020, 1, 2),
        "all_day": True,
        "description": "Plain Text",
        "location": "Test Location",
        "location_details": None,
        "locations": None,
        "categories": [],
        "sensitivity": "Private",
        "show_as": "Busy",
        "reminder": {"minutes": 0, "is_on": False},
        "attendees": [],
        "organizer": "",
        "uid": "event2",
    },
]

BASE_STATE_CAL2 = [
    {
        "summary": "Test event calendar2",
        "start": datetime.datetime(
            2020, 1, 1, 0, 0, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
        "end": datetime.datetime(
            2020, 1, 2, 23, 59, 59, tzinfo=zoneinfo.ZoneInfo(key="UTC")
        ),
        "all_day": False,
        "description": "Test",
        "location": "Test Location",
        "location_details": None,
        "locations": None,
        "categories": [],
        "sensitivity": "Normal",
        "show_as": "Busy",
        "reminder": {"minutes": 0, "is_on": False},
        "attendees": [],
        "organizer": "",
        "uid": "event1",
    }
]

# The location fields of each event in calendar1_calendar_view_locations, by uid
LOCATION_STATE = {
    "address": {
        "location": "Fourth Coffee",
        "location_details": {
            "address": {
                "street": "4567 Main St",
                "city": "Redmond",
                "state": "WA",
                "postal_code": "98052",
                "country": "United States",
            },
            "coordinates": {"latitude": 47.672, "longitude": -122.103},
            "type": "local_business",
            "uri": "https://www.bingapis.com/api/v6/localbusinesses/fourthcoffee",
        },
        "locations": None,
    },
    "room": {
        "location": "Room 1",
        "location_details": {
            "address": {"city": "Utrecht"},
            "type": "conference_room",
            "email": "room1@nomail.com",
        },
        "locations": None,
    },
    "several": {
        "location": "Room 1; Head office; Home office",
        "location_details": None,
        "locations": [
            {"name": "Room 1", "type": "conference_room", "email": "room1@nomail.com"},
            {
                "name": "Head office",
                "address": {
                    "street": "1 Station Square",
                    "city": "Utrecht",
                    "postal_code": "3511 ED",
                    "country": "Netherlands",
                },
                "coordinates": {"latitude": 52.089, "longitude": 5.11},
                "type": "business_address",
            },
            {"name": "Home office"},
        ],
    },
    "name_only": {
        "location": "Dentist",
        "location_details": None,
        "locations": None,
    },
    "no_location": {
        "location": "",
        "location_details": None,
        "locations": None,
    },
}
