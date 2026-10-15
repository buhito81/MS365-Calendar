# pylint: disable=unused-argument,line-too-long,wrong-import-order
"""Test file management."""

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from requests_mock import Mocker

from .const_integration import FULL_INIT_ENTITY_NO

from ..helpers.mock_config_entry import MS365MockConfigEntry
from .helpers_integration.mocks import MS365MOCKS
from .helpers_integration.utils_integration import (
    check_yaml_file_contents,
    read_yaml_file,
    write_yaml_file,
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

    assert "Invalid Data - entry not loaded" in caplog.text


async def test_corrupt_file_2(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test for corrupt yaml content."""
    # logging.disable(logging.WARNING)
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_corrupt2")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert "Invalid Data - entry not loaded" in caplog.text

    entities = er.async_entries_for_config_entry(
        entity_registry, base_config_entry.entry_id
    )
    assert len(entities) == FULL_INIT_ENTITY_NO


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


async def test_corrupt_file_repaired(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test a corrupt entry is not added again, and is used once repaired."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_corrupt")

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    calendars = read_yaml_file(tmp_path)
    assert [calendar["cal_id"] for calendar in calendars] == [
        "calendar1",
        "group:calendar2",
        "calendar3",
    ]
    assert hass.states.get("calendar.test_calendar1") is None
    assert caplog.text.count("Invalid Data - entry not loaded") == 1
    assert "'cal_id': 'calendar1'" in caplog.text
    assert "required key not provided" in caplog.text

    caplog.clear()
    calendars[0]["entities"][0]["name"] = "Calendar1 Repaired"
    write_yaml_file(tmp_path, calendars)
    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("calendar.test_calendar1")
    assert state.attributes["friendly_name"] == "Calendar1 Repaired"
    assert "Invalid Data" not in caplog.text


@pytest.mark.parametrize(
    "infile",
    [
        "ms365_calendars_invalid_key",
        "ms365_calendars_invalid_value",
        "ms365_calendars_invalid_entity",
        "ms365_calendars_invalid_cal_id",
        "ms365_calendars_invalid_empty_cal_id",
        "ms365_calendars_invalid_dash",
    ],
)
async def test_invalid_entry_kept(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
    infile,
) -> None:
    """Test an entry that is not valid is kept as it is."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, infile)
    calendars = read_yaml_file(tmp_path)

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert read_yaml_file(tmp_path) == calendars

    # Calendar3 has been deleted in MS365, so the file is rewritten
    MS365MOCKS.no_events_mocks(requests_mock)
    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()

    del calendars[2]
    assert read_yaml_file(tmp_path) == calendars
    assert "Calendar deleted from" in caplog.text
    # One warning at each start
    assert caplog.text.count("Invalid Data - entry not loaded") == 2


async def test_deleted_file_sensitivity(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test sensitivity_exclude can still be read after a calendar is deleted."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_sensitivity")
    calendars = read_yaml_file(tmp_path)

    base_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    # Calendar3 was added, and has now been deleted in MS365
    MS365MOCKS.no_events_mocks(requests_mock)
    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert read_yaml_file(tmp_path) == calendars

    await hass.config_entries.async_reload(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert base_config_entry.state is ConfigEntryState.LOADED
