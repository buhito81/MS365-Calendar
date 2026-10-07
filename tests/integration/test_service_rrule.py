# pylint: disable=unused-argument,line-too-long
"""Test the repeat rules of created and updated events."""

from unittest.mock import patch

import pytest
from requests_mock import Mocker

from ..helpers.utils import mock_call
from .const_integration import URL
from .fixtures import ClientFixture

CALENDAR_NAME = "calendar.test_calendar1"
EVENT_NAME = "event1"


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
