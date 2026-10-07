# pylint: disable=line-too-long, unused-argument
"""Test the config flow."""

import json
import re
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from O365.calendar import EventSensitivity, EventShowAs
from requests_mock import Mocker

from custom_components.ms365_calendar.integration.const_integration import (
    CONF_ADVANCED_OPTIONS,
    CONF_CALENDAR_LIST,
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_EXCLUDE,
    CONF_EXCLUDE_DECLINED,
    CONF_HOURS_BACKWARD_TO_GET,
    CONF_HOURS_FORWARD_TO_GET,
    CONF_MAX_RESULTS,
    CONF_SEARCH,
    CONF_SENSITIVITY_EXCLUDE,
    CONF_SHOW_AS_EXCLUDE,
    CONF_TRACK_NEW_CALENDAR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_UPDATE_INTERVAL,
)
from custom_components.ms365_calendar.integration.schema_integration import (
    YAML_CALENDAR_ENTITY_SCHEMA,
)

from ..const import STORAGE_LOCATION
from ..helpers.mock_config_entry import MS365MockConfigEntry
from ..helpers.utils import build_token_url, get_schema_default, mock_token
from .const_integration import (
    AUTH_CALLBACK_PATH_DEFAULT,
    RECONFIGURE_CONFIG_ENTRY,
    BASE_CONFIG_ENTRY,
    BASE_TOKEN_PERMS,
    DOMAIN,
    SHARED_TOKEN_PERMS,
    UPDATE_CALENDAR_LIST,
    URL,
)
from .helpers_integration.mocks import MS365MOCKS
from .helpers_integration.utils_integration import (
    check_yaml_file_contents,
    read_yaml_file,
    update_options,
    yaml_setup,
)

FILTERS = "filters"
# The options as the first step of the options flow sends them unchanged
OPTIONS = {
    CONF_TRACK_NEW_CALENDAR: True,
    CONF_CALENDAR_LIST: UPDATE_CALENDAR_LIST,
    CONF_ADVANCED_OPTIONS: {
        CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
        CONF_DAYS_BACKWARD: DEFAULT_DAYS_BACKWARD,
        CONF_DAYS_FORWARD: DEFAULT_DAYS_FORWARD,
    },
}
CALENDAR1 = {
    CONF_NAME: "Calendar1",
    CONF_HOURS_FORWARD_TO_GET: 24,
    CONF_HOURS_BACKWARD_TO_GET: 0,
}
# The events of calendar1_calendar_view_responses
ALL_EVENTS = [
    "Accepted meeting",
    "Declined meeting",
    "Holiday",
    "Tentative meeting",
    "Unanswered meeting",
    "Working from home",
]
FILTERED_EVENTS = ["Accepted meeting", "Tentative meeting", "Unanswered meeting"]
TRANSLATIONS = (
    Path(__file__).parents[2]
    / "custom_components"
    / DOMAIN
    / "translations"
    / "en.json"
)


async def test_options_flow(
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow."""

    result = await hass.config_entries.options.async_init(base_config_entry.entry_id)
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    schema = result["data_schema"].schema
    assert get_schema_default(schema, CONF_TRACK_NEW_CALENDAR) is True
    assert get_schema_default(schema, CONF_CALENDAR_LIST) == [
        "Calendar1",
        "Calendar2",
        "Calendar3",
    ]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_TRACK_NEW_CALENDAR: False,
            CONF_CALENDAR_LIST: UPDATE_CALENDAR_LIST,
            CONF_ADVANCED_OPTIONS: {
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_DAYS_BACKWARD: DEFAULT_DAYS_BACKWARD,
                CONF_DAYS_FORWARD: DEFAULT_DAYS_FORWARD,
            },
        },
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "calendar_config"
    assert result["last_step"] is True
    schema = result["data_schema"].schema
    assert get_schema_default(schema, CONF_NAME) == "Calendar1"
    assert get_schema_default(schema, CONF_HOURS_FORWARD_TO_GET) == 24
    assert get_schema_default(schema, CONF_HOURS_BACKWARD_TO_GET) == 0
    assert get_schema_default(schema, CONF_MAX_RESULTS) is None

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Calendar1_Changed",
            CONF_HOURS_FORWARD_TO_GET: 48,
            CONF_HOURS_BACKWARD_TO_GET: -48,
            CONF_MAX_RESULTS: 5,
        },
    )
    await hass.async_block_till_done()
    assert result.get("type") is FlowResultType.CREATE_ENTRY

    assert result["data"][CONF_TRACK_NEW_CALENDAR] is False

    assert result["data"][CONF_CALENDAR_LIST] == UPDATE_CALENDAR_LIST


async def test_options_flow_keeps_sensitivity_exclude(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow keeps settings it does not show."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_sensitivity")
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    await update_options(hass, base_config_entry)
    await hass.async_block_till_done()

    entity = read_yaml_file(tmp_path)[0]["entities"][0]
    assert entity[CONF_NAME] == "Calendar1_Changed"
    assert entity["sensitivity_exclude"] == ["private"]


async def test_options_flow_keeps_response_filters(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow keeps the declined and show as filters."""
    MS365MOCKS.response_event_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_both_response_filters")
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    await update_options(hass, base_config_entry)
    await hass.async_block_till_done()

    entity = read_yaml_file(tmp_path)[0]["entities"][0]
    assert entity[CONF_NAME] == "Calendar1_Changed"
    assert entity["exclude_declined"] is True
    assert entity["show_as_exclude"] == ["workingElsewhere", "oof"]

    # The reload with the changed options still leaves the events out
    data = hass.states.get("calendar.test_calendar1").attributes["data"]
    assert sorted(event["summary"] for event in data) == [
        "Accepted meeting",
        "Tentative meeting",
        "Unanswered meeting",
    ]


async def test_options_flow_no_offsets(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow for a calendar with no offsets in the yaml file."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_no_offsets")
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(base_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_TRACK_NEW_CALENDAR: True,
            CONF_CALENDAR_LIST: UPDATE_CALENDAR_LIST,
            CONF_ADVANCED_OPTIONS: {
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_DAYS_BACKWARD: DEFAULT_DAYS_BACKWARD,
                CONF_DAYS_FORWARD: DEFAULT_DAYS_FORWARD,
            },
        },
    )
    assert result["step_id"] == "calendar_config"
    schema = result["data_schema"].schema
    assert get_schema_default(schema, CONF_HOURS_FORWARD_TO_GET) == 24
    assert get_schema_default(schema, CONF_HOURS_BACKWARD_TO_GET) == 0


async def test_options_flow_no_calendars(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow when the calendars yaml file is missing."""
    (tmp_path / STORAGE_LOCATION / f"{DOMAIN}s_test.yaml").unlink()

    result = await hass.config_entries.options.async_init(base_config_entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_calendars"


async def test_options_flow_reload(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the options flow reloads once, after the new options are saved."""
    MS365MOCKS.no_events_mocks(requests_mock)
    base_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()

    # Two calendars have been created since the last start
    MS365MOCKS.standard_mocks(requests_mock)
    start = len(requests_mock.request_history)
    await update_options(hass, base_config_entry)
    await hass.async_block_till_done()

    # Reloaded once, as each setup scans for calendars once
    assert _calendar_scans(requests_mock, start) == 1
    calendars = read_yaml_file(tmp_path)
    assert [calendar["cal_id"] for calendar in calendars] == [
        "calendar1",
        "group:calendar2",
        "calendar3",
    ]
    assert [calendar["entities"][0]["track"] for calendar in calendars] == [
        True,
        False,
        False,
    ]

    # Same options, so only the yaml changes
    start = len(requests_mock.request_history)
    result = await hass.config_entries.options.async_init(base_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=dict(base_config_entry.options)
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Calendar1_Renamed",
            CONF_HOURS_FORWARD_TO_GET: 48,
            CONF_HOURS_BACKWARD_TO_GET: -48,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _calendar_scans(requests_mock, start) == 1
    state = hass.states.get("calendar.test_calendar1")
    assert state.attributes["friendly_name"] == "Calendar1_Renamed"


async def test_options_flow_retries_failed_setup(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test changing the options of an entry that failed to set up retries it."""
    MS365MOCKS.standard_mocks(requests_mock)
    yaml_setup(tmp_path, "ms365_calendars_base")
    base_config_entry.add_to_hass(hass)
    # No token file, so the setup fails
    await hass.config_entries.async_setup(base_config_entry.entry_id)
    await hass.async_block_till_done()
    assert base_config_entry.state is config_entries.ConfigEntryState.SETUP_ERROR

    with patch.object(hass.config_entries, "async_schedule_reload") as schedule_reload:
        await update_options(hass, base_config_entry)
        await hass.async_block_till_done()

    schedule_reload.assert_called_once_with(base_config_entry.entry_id)


async def test_options_flow_filters_filled_in(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the filters of a calendar are filled in from the yaml file."""
    await _async_setup(
        hass, tmp_path, requests_mock, base_config_entry, "ms365_calendars_filters"
    )

    result = await _async_calendar_form(hass, base_config_entry)

    assert result["step_id"] == "calendar_config"
    filters = _filters_section(result)
    assert filters.options["collapsed"] is True
    assert _filter_values(result) == {
        CONF_SEARCH: "meeting",
        CONF_EXCLUDE: ["^Holiday", "(?i)WORKING"],
        CONF_SENSITIVITY_EXCLUDE: ["private"],
        CONF_EXCLUDE_DECLINED: True,
        CONF_SHOW_AS_EXCLUDE: ["working_elsewhere", "oof"],
    }

    # The options are the values the yaml file accepts, each with its text
    translations = _translations()
    for key, values in (
        (CONF_SENSITIVITY_EXCLUDE, EventSensitivity),
        (CONF_SHOW_AS_EXCLUDE, EventShowAs),
    ):
        options = filters.schema.schema[key].config["options"]
        assert options == [value.value for value in values]
        entity = YAML_CALENDAR_ENTITY_SCHEMA(
            {**CALENDAR1, "device_id": "x", "track": True, key: options}
        )
        assert entity[key] == list(values)
        assert list(translations["selector"][key]["options"]) == options
    texts = translations["options"]["step"]["calendar_config"]["sections"][FILTERS]
    keys = [str(key) for key in filters.schema.schema]
    assert list(texts["data"]) == keys
    assert list(texts["data_description"]) == keys
    assert "invalid_exclude" in translations["options"]["error"]


@pytest.mark.parametrize("base_config_entry", [{"options": OPTIONS}], indirect=True)
async def test_options_flow_set_filters(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test a change to only the filters writes them and reloads with them."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry)
    assert _summaries(hass) == ALL_EVENTS

    start = len(requests_mock.request_history)
    result = await _async_calendar_form(hass, base_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            **CALENDAR1,
            FILTERS: {
                CONF_SEARCH: "meeting",
                # An added field left empty, or holding only spaces, is left out
                CONF_EXCLUDE: ["^Holiday", " ", ""],
                CONF_SENSITIVITY_EXCLUDE: ["confidential", "private"],
                CONF_EXCLUDE_DECLINED: True,
                CONF_SHOW_AS_EXCLUDE: ["working_elsewhere", "free"],
            },
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == OPTIONS
    assert read_yaml_file(tmp_path)[0]["entities"] == [
        {
            "device_id": "Calendar1",
            "end_offset": 24,
            "exclude": ["^Holiday"],
            "exclude_declined": True,
            "name": "Calendar1",
            "search": "meeting",
            "sensitivity_exclude": ["private", "confidential"],
            "show_as_exclude": ["free", "workingElsewhere"],
            "start_offset": 0,
            "track": True,
        }
    ]

    # The options did not change, yet the entry is reloaded once with the filters
    assert _calendar_scans(requests_mock, start) == 1
    assert _summaries(hass) == FILTERED_EVENTS
    queries = [
        request.qs.get("$filter", [""])[0]
        for request in requests_mock.request_history[start:]
        if "calendarview" in request.url.lower()
    ]
    assert queries
    for query in queries:
        assert "contains(subject, 'meeting')" in query
        assert "sensitivity ne 'private'" in query
        assert "sensitivity ne 'confidential'" in query


@pytest.mark.parametrize("base_config_entry", [{"options": OPTIONS}], indirect=True)
async def test_options_flow_clear_filters(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test clearing the filters removes them from the yaml file, and keeps the rest."""
    await _async_setup(
        hass, tmp_path, requests_mock, base_config_entry, "ms365_calendars_filters"
    )
    assert _summaries(hass) == FILTERED_EVENTS

    result = await _async_calendar_form(hass, base_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            **CALENDAR1,
            FILTERS: {
                CONF_SEARCH: "  ",
                CONF_EXCLUDE: [""],
                CONF_SENSITIVITY_EXCLUDE: [],
                CONF_EXCLUDE_DECLINED: False,
                CONF_SHOW_AS_EXCLUDE: [],
            },
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert read_yaml_file(tmp_path) == [
        {
            "cal_id": "calendar1",
            "entities": [
                {
                    "device_id": "Calendar1",
                    "end_offset": 24,
                    "name": "Calendar1",
                    "start_offset": 0,
                    "track": True,
                }
            ],
            "note": "Not known to the options",
        }
    ]
    assert _summaries(hass) == ALL_EVENTS


@pytest.mark.parametrize("base_config_entry", [{"options": OPTIONS}], indirect=True)
async def test_options_flow_invalid_exclude(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test an exclude that is not a regular expression is shown with the input kept."""
    await _async_setup(hass, tmp_path, requests_mock, base_config_entry)
    filters = {
        CONF_SEARCH: "meeting",
        CONF_EXCLUDE: ["^Holiday", "(Optional"],
        CONF_EXCLUDE_DECLINED: True,
    }

    result = await _async_calendar_form(hass, base_config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**CALENDAR1, CONF_NAME: "Renamed", FILTERS: filters},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "calendar_config"
    assert result["errors"] == {FILTERS: "invalid_exclude"}
    with pytest.raises(re.error) as err:
        re.compile("(Optional")
    assert result["description_placeholders"] == {
        "entity_name": "test",
        "device_id": "Calendar1",
        "pattern": "(Optional",
        "error": str(err.value),
    }
    # Shown again as entered, with the filters open to correct the pattern
    assert get_schema_default(result["data_schema"].schema, CONF_NAME) == "Renamed"
    assert _filters_section(result).options["collapsed"] is False
    assert _filter_values(result) == filters

    filters[CONF_EXCLUDE] = ["^Holiday", r"\(Optional"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**CALENDAR1, CONF_NAME: "Renamed", FILTERS: filters},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entity = read_yaml_file(tmp_path)[0]["entities"][0]
    assert entity[CONF_NAME] == "Renamed"
    assert entity[CONF_EXCLUDE] == ["^Holiday", r"\(Optional"]


async def test_options_flow_filters_not_accepted(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test filter values the yaml file does not accept are left out of the form."""
    yaml_setup(tmp_path, "ms365_calendars_filters_invalid")

    result = await _async_calendar_form(hass, base_config_entry)

    filters = _filter_values(result)
    assert filters == {
        CONF_SEARCH: None,
        # A single exclude is read as a list of one
        CONF_EXCLUDE: ["Holiday"],
        # Sensitivities must be in lower case
        CONF_SENSITIVITY_EXCLUDE: [],
        CONF_EXCLUDE_DECLINED: None,
        CONF_SHOW_AS_EXCLUDE: ["busy"],
    }

    # Saved as shown, the calendar is valid again
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            **CALENDAR1,
            FILTERS: {
                CONF_EXCLUDE: filters[CONF_EXCLUDE],
                CONF_SHOW_AS_EXCLUDE: filters[CONF_SHOW_AS_EXCLUDE],
            },
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entity = read_yaml_file(tmp_path)[0]["entities"][0]
    assert entity == {
        "device_id": "Calendar1",
        "end_offset": 24,
        "exclude": ["Holiday"],
        "name": "Calendar1",
        "show_as_exclude": ["busy"],
        "start_offset": 0,
        "track": True,
    }
    YAML_CALENDAR_ENTITY_SCHEMA(entity)


async def test_options_flow_filters_per_calendar(
    tmp_path,
    hass: HomeAssistant,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test each calendar's filters are filled in from and saved to its own entry."""
    result = await hass.config_entries.options.async_init(base_config_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**OPTIONS, CONF_CALENDAR_LIST: ["Calendar1", "Calendar3"]},
    )
    assert result["last_step"] is False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={**CALENDAR1, FILTERS: {CONF_EXCLUDE_DECLINED: True}},
    )

    # The next calendar is filled in from its own entry
    assert result["description_placeholders"]["device_id"] == "Calendar3"
    assert result["last_step"] is True
    assert _filter_values(result) == {
        CONF_SEARCH: None,
        CONF_EXCLUDE: [],
        CONF_SENSITIVITY_EXCLUDE: [],
        CONF_EXCLUDE_DECLINED: None,
        CONF_SHOW_AS_EXCLUDE: [],
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            **CALENDAR1,
            CONF_NAME: "Calendar3",
            FILTERS: {CONF_EXCLUDE: ["^Event"]},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    entities = {
        calendar["cal_id"]: calendar["entities"][0]
        for calendar in read_yaml_file(tmp_path)
    }
    assert entities["calendar1"]["exclude_declined"] is True
    assert CONF_EXCLUDE not in entities["calendar1"]
    assert entities["calendar3"][CONF_EXCLUDE] == ["^Event"]
    assert CONF_EXCLUDE_DECLINED not in entities["calendar3"]


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


async def _async_calendar_form(hass: HomeAssistant, entry: MS365MockConfigEntry):
    """Open the options and keep them, up to the form of the first calendar."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=dict(entry.options)
    )


def _filters_section(result):
    """Get the filters section of a calendar form."""
    return result["data_schema"].schema[FILTERS]


def _filter_values(result):
    """Get the values the filters of a calendar form are filled in with."""
    return {
        str(key): key.description["suggested_value"]
        for key in _filters_section(result).schema.schema
        if key.description
    }


def _translations():
    """Read the English texts of the integration."""
    return json.loads(TRANSLATIONS.read_text(encoding="utf8"))


def _summaries(hass: HomeAssistant):
    """Get the sorted titles of the events in the data of calendar 1."""
    data = hass.states.get("calendar.test_calendar1").attributes["data"]
    return sorted(event["summary"] for event in data)


def _calendar_scans(requests_mock, start):
    """Count the requests for the list of calendars made since start."""
    return len(
        [
            request
            for request in requests_mock.request_history[start:]
            if request.method == "GET"
            and request.url.split("?")[0] == URL.CALENDARS.value
        ]
    )


async def test_import_without_calendars(
    tmp_path,
    hass: HomeAssistant,
    requests_mock: Mocker,
    base_token,
) -> None:
    """Test a legacy import with no calendars, as sent when it has no yaml file."""
    MS365MOCKS.standard_mocks(requests_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={"data": deepcopy(BASE_CONFIG_ENTRY), "options": {}},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].state is config_entries.ConfigEntryState.LOADED
    check_yaml_file_contents(tmp_path, "ms365_calendars_base")


async def test_invalid_combinations(
    hass: HomeAssistant,
    requests_mock: Mocker,
    setup_base_integration,
    base_config_entry: MS365MockConfigEntry,
) -> None:
    """Test the reconfigure flow."""
    mock_token(requests_mock, BASE_TOKEN_PERMS)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": base_config_entry.entry_id,
        },
    )
    assert result.get("type") is FlowResultType.FORM
    assert result["step_id"] == "user"

    reconfigure_config_entry = deepcopy(RECONFIGURE_CONFIG_ENTRY)
    reconfigure_config_entry["basic_calendar"] = True
    reconfigure_config_entry["enable_update"] = True

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=reconfigure_config_entry,
    )

    assert "errors" in result
    assert "basic_calendar" in result["errors"]
    assert result["errors"]["basic_calendar"] == "cannot_have_basic_update"

    reconfigure_config_entry = deepcopy(RECONFIGURE_CONFIG_ENTRY)
    reconfigure_config_entry["basic_calendar"] = True
    reconfigure_config_entry["shared_mailbox"] = "john@nospam.com"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=reconfigure_config_entry,
    )

    assert "errors" in result
    assert "basic_calendar" in result["errors"]
    assert result["errors"]["basic_calendar"] == "cannot_have_basic_shared"

    reconfigure_config_entry = deepcopy(RECONFIGURE_CONFIG_ENTRY)
    reconfigure_config_entry["groups"] = True
    reconfigure_config_entry["shared_mailbox"] = "john@nospam.com"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=reconfigure_config_entry,
    )

    assert "errors" in result
    assert "groups" in result["errors"]
    assert result["errors"]["groups"] == "cannot_have_groups_shared"


async def test_shared_email_invalid(
    hass: HomeAssistant,
    requests_mock: Mocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test for invalid shared mailbox."""
    mock_token(requests_mock, SHARED_TOKEN_PERMS)
    MS365MOCKS.standard_mocks(requests_mock)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    user_input = deepcopy(BASE_CONFIG_ENTRY)
    email = "john@nomail.com"
    user_input["shared_mailbox"] = email
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input=user_input,
    )

    with patch(
        f"custom_components.{DOMAIN}.classes.api.MS365CustomAccount",
        return_value=mock_account(email),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={
                "url": build_token_url(result, AUTH_CALLBACK_PATH_DEFAULT),
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    assert (
        f"Login email address '{email}' should not be entered as shared email address, config attribute removed"
        in caplog.text
    )


def mock_account(email):
    """Mock the account."""
    return MagicMock(is_authenticated=True, username=email, main_resource=email)
