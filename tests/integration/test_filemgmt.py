# pylint: disable=unused-argument,line-too-long,wrong-import-order
"""Test file management."""

import json
import logging

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from requests_mock import Mocker

from custom_components.ms365_calendar.integration.const_integration import (
    CONF_CAL_ID,
    CONF_TRACK_NEW_CALENDAR,
)
from custom_components.ms365_calendar.integration.filemgmt_integration import (
    load_yaml_file,
)
from custom_components.ms365_calendar.integration.schema_integration import (
    YAML_CALENDAR_DEVICE_SCHEMA,
)

from ..const import TEST_DATA_INTEGRATION_LOCATION
from ..helpers.mock_config_entry import MS365MockConfigEntry
from ..helpers.utils import load_json, mock_call
from .const_integration import URL
from .helpers_integration.mocks import MS365MOCKS
from .helpers_integration.utils_integration import (
    check_yaml_file_contents,
    read_yaml_file,
    yaml_setup,
)


async def test_base_filemgmt(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test base file management."""

    check_yaml_file_contents(tmp_path, "ms365_calendars_base")


async def test_empty_file(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test for an empty yaml file."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_empty")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    check_yaml_file_contents(tmp_path, "ms365_calendars_base")


async def test_corrupt_file(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test for corrupt yaml content."""
    # logging.disable(logging.WARNING)
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_corrupt")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert "Invalid Data - duplicate entries may be created" in caplog.text


async def test_invalid_calendar_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test the warning for an invalid calendar names it and what is wrong."""
    path = TEST_DATA_INTEGRATION_LOCATION / "yaml/ms365_calendars_invalid_entries.yaml"

    calendars = load_yaml_file(path, CONF_CAL_ID, YAML_CALENDAR_DEVICE_SCHEMA)

    # The invalid calendars are skipped as before
    assert list(calendars) == ["calendar4"]
    prefix = f"Invalid Data - duplicate entries may be created in file {path}, calendar"
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert warnings == [
        f"{prefix} cal_id 'calendar1' with entities named ['Calendar1', 'Calendar1 away']: "
        "expected EventShowAs or one of 'free', 'tentative', 'busy', 'oof', "
        "'working_elsewhere', 'unknown' at 'entities[1].show_as_exclude[0]'",
        f"{prefix} cal_id 'calendar2' with entities named []: "
        "expected a mapping at 'entities[0]'",
        f"{prefix} 'calendar3': expected a mapping",
    ]


async def test_deleted_file(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test for deleting yaml content."""
    # logging.disable(logging.WARNING)
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_delete")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    check_yaml_file_contents(tmp_path, "ms365_calendars_base")

    assert "Calendar deleted from" in caplog.text


async def test_deleted_file_keeps_sensitivity(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test deleting yaml content keeps a file that loads again."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_delete_sensitivity")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    calendars = read_yaml_file(tmp_path)
    assert [calendar["cal_id"] for calendar in calendars] == [
        "calendar1",
        "group:calendar2",
        "calendar3",
    ]
    assert calendars[0]["entities"][0]["sensitivity_exclude"] == ["private"]

    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()
    assert base_config_entry.state is ConfigEntryState.LOADED


async def test_deleted_file_keeps_response_filters(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test deleting yaml content keeps the declined and show as filters."""
    MS365MOCKS.response_event_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_delete_response_filters")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    calendars = read_yaml_file(tmp_path)
    assert [calendar["cal_id"] for calendar in calendars] == ["calendar1"]
    entity = calendars[0]["entities"][0]
    assert entity["exclude_declined"] is True
    assert entity["show_as_exclude"] == ["workingElsewhere", "oof"]

    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()
    assert base_config_entry.state is ConfigEntryState.LOADED
    data = hass.states.get("calendar.test_calendar1").attributes["data"]
    assert sorted(event["summary"] for event in data) == [
        "Accepted meeting",
        "Tentative meeting",
        "Unanswered meeting",
    ]


async def test_file_without_newline(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a new calendar is added to a file that does not end with a newline."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_no_newline")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    check_yaml_file_contents(tmp_path, "ms365_calendars_base")


async def test_calendar_limit_reached(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test no calendars are deleted when the scan returns the most it reads."""
    MS365MOCKS.standard_mocks(requests_mock)
    # 50 calendars, the most that are read; calendar3 is not among them
    data = json.loads(load_json("O365/calendars.json"))
    first = data["value"][0]
    data["value"] = [first] + [
        {**first, "id": f"calendar{number}", "name": f"Calendar{number}"}
        for number in range(4, 53)
    ]
    requests_mock.get(URL.CALENDARS.value, json=data)
    yaml_setup(tmp_path, "ms365_calendars_base")

    base_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        base_config_entry, options={CONF_TRACK_NEW_CALENDAR: False}
    )

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    calendar_ids = [calendar["cal_id"] for calendar in read_yaml_file(tmp_path)]
    assert "calendar3" in calendar_ids
    assert len(calendar_ids) == 52
    assert "Calendar deleted from" not in caplog.text


async def test_no_calendars_found(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test no calendars are deleted when the scan finds none."""
    MS365MOCKS.standard_mocks(requests_mock)
    mock_call(requests_mock, URL.CALENDARS, "calendars_none")
    yaml_setup(tmp_path, "ms365_calendars_base")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    check_yaml_file_contents(tmp_path, "ms365_calendars_base")
    assert "No calendars found, so none deleted" in caplog.text
