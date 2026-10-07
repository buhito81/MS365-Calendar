"""Configuration flow for the MS365 platform."""

from copy import deepcopy
import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from O365.calendar import (  # pylint: disable=no-name-in-module
    EventSensitivity,
    EventShowAs,
)
from O365.utils import to_camel_case  # pylint: disable=no-name-in-module

from ..classes.config_entry import MS365ConfigEntry
from ..const import CONF_ENABLE_UPDATE, CONF_ENTITY_NAME, CONF_SHARED_MAILBOX
from ..helpers.utils import add_attribute_to_item
from .const_integration import (
    CONF_ADVANCED_OPTIONS,
    CONF_BASIC_CALENDAR,
    CONF_CAL_ID,
    CONF_CALENDAR_LIST,
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_EXCLUDE,
    CONF_EXCLUDE_DECLINED,
    CONF_FILTERS,
    CONF_GROUPS,
    CONF_HOURS_BACKWARD_TO_GET,
    CONF_HOURS_FORWARD_TO_GET,
    CONF_MAX_RESULTS,
    CONF_SEARCH,
    CONF_SENSITIVITY_EXCLUDE,
    CONF_SHOW_AS_EXCLUDE,
    CONF_TRACK,
    CONF_TRACK_NEW_CALENDAR,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_HOURS_BACKWARD_TO_GET,
    DEFAULT_HOURS_FORWARD_TO_GET,
    DEFAULT_UPDATE_INTERVAL,
    YAML_CALENDARS_FILENAME,
)
from .filemgmt_integration import (
    build_yaml_file_path,
    build_yaml_filename,
    read_calendar_yaml_file,
    write_calendar_yaml_file,
    write_yaml_file,
)
from .schema_integration import SENSITIVITY_VALUE, SHOW_AS_VALUE
from .utils_integration import async_delete_calendar

BOOLEAN_SELECTOR = BooleanSelector()
SENSITIVITY_OPTIONS = [sensitivity.value for sensitivity in EventSensitivity]
SHOW_AS_OPTIONS = [show_as.value for show_as in EventShowAs]
FILTERS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SEARCH): TextSelector(),
        vol.Optional(CONF_EXCLUDE): TextSelector(TextSelectorConfig(multiple=True)),
        vol.Optional(CONF_SENSITIVITY_EXCLUDE): SelectSelector(
            SelectSelectorConfig(
                options=SENSITIVITY_OPTIONS,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_SENSITIVITY_EXCLUDE,
            )
        ),
        vol.Optional(CONF_EXCLUDE_DECLINED, default=False): BOOLEAN_SELECTOR,
        vol.Optional(CONF_SHOW_AS_EXCLUDE): SelectSelector(
            SelectSelectorConfig(
                options=SHOW_AS_OPTIONS,
                multiple=True,
                mode=SelectSelectorMode.LIST,
                translation_key=CONF_SHOW_AS_EXCLUDE,
            )
        ),
    }
)


def integration_reconfigure_schema(entry_data):
    """Extend the scheme with integration specific attributes."""
    return {
        vol.Optional(
            CONF_ENABLE_UPDATE, default=entry_data[CONF_ENABLE_UPDATE]
        ): cv.boolean,
        vol.Optional(
            CONF_BASIC_CALENDAR, default=entry_data[CONF_BASIC_CALENDAR]
        ): cv.boolean,
        vol.Optional(CONF_GROUPS, default=entry_data[CONF_GROUPS]): cv.boolean,
        vol.Optional(
            CONF_SHARED_MAILBOX,
            description={"suggested_value": entry_data.get(CONF_SHARED_MAILBOX, None)},
        ): cv.string,
    }


def integration_validate_schema(user_input):  # pylint: disable=unused-argument
    """Validate the user input."""
    if user_input.get(CONF_BASIC_CALENDAR) and user_input.get(CONF_SHARED_MAILBOX):
        return {CONF_BASIC_CALENDAR: "cannot_have_basic_shared"}
    if user_input.get(CONF_BASIC_CALENDAR) and user_input.get(CONF_ENABLE_UPDATE):
        return {CONF_BASIC_CALENDAR: "cannot_have_basic_update"}
    if user_input.get(CONF_GROUPS) and user_input.get(CONF_SHARED_MAILBOX):
        return {CONF_GROUPS: "cannot_have_groups_shared"}
    return {}


async def async_integration_imports(hass: HomeAssistant, import_data):
    """Do the integration  level import tasks."""
    # The legacy integration leaves calendars out when it has no calendars yaml
    calendars = import_data.get("calendars", {})
    path = YAML_CALENDARS_FILENAME.format(
        f"_{import_data['data'].get(CONF_ENTITY_NAME)}"
    )
    yaml_filepath = build_yaml_file_path(hass, path)

    for calendar in calendars.values():
        await hass.async_add_executor_job(write_yaml_file, yaml_filepath, calendar)


class MS365OptionsFlowHandler(config_entries.OptionsFlow):
    """Config flow options for MS365."""

    def __init__(self, entry: MS365ConfigEntry) -> None:
        """Initialize MS365 options flow."""

        self._track_new_calendar = entry.options.get(CONF_TRACK_NEW_CALENDAR, True)
        self._calendars = []
        self._calendar_list = []
        self._calendar_list_selected = []
        self._calendar_list_selected_original = []
        self._yaml_filename = build_yaml_filename(entry, YAML_CALENDARS_FILENAME)
        self._yaml_filepath = None
        self._calendar_no = 0
        self._user_input = None

    async def async_step_init(
        self,
        user_input=None,  # pylint: disable=unused-argument
    ) -> ConfigFlowResult:
        """Set up the option flow."""

        self._yaml_filepath = build_yaml_file_path(self.hass, self._yaml_filename)
        self._calendars = await self.hass.async_add_executor_job(
            read_calendar_yaml_file,
            self._yaml_filepath,
        )
        if not self._calendars:
            return self.async_abort(reason="no_calendars")

        for calendar in self._calendars:
            for entity in calendar.get(CONF_ENTITIES):
                self._calendar_list.append(entity[CONF_DEVICE_ID])
                if entity[CONF_TRACK]:
                    self._calendar_list_selected.append(entity[CONF_DEVICE_ID])

        self._calendar_list_selected_original = deepcopy(self._calendar_list_selected)
        return await self.async_step_user()

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors = {}

        if user_input:
            self._user_input = user_input
            self._track_new_calendar = user_input[CONF_TRACK_NEW_CALENDAR]
            self._calendar_list_selected = user_input[CONF_CALENDAR_LIST]

            for calendar in self._calendars:
                for entity in calendar[CONF_ENTITIES]:
                    entity[CONF_TRACK] = (
                        entity[CONF_DEVICE_ID] in self._calendar_list_selected
                    )

            return await self.async_step_calendar_config()

        return self.async_show_form(
            step_id="user",
            description_placeholders={
                CONF_ENTITY_NAME: self.config_entry.data[CONF_ENTITY_NAME]
            },
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CALENDAR_LIST, default=self._calendar_list_selected
                    ): cv.multi_select(self._calendar_list),
                    vol.Optional(
                        CONF_TRACK_NEW_CALENDAR,
                        default=self._track_new_calendar,
                    ): BOOLEAN_SELECTOR,
                    vol.Optional(CONF_ADVANCED_OPTIONS): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    CONF_UPDATE_INTERVAL,
                                    default=self.config_entry.options.get(
                                        CONF_ADVANCED_OPTIONS, {}
                                    ).get(
                                        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                                    ),
                                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=600)),
                                vol.Optional(
                                    CONF_DAYS_BACKWARD,
                                    default=self.config_entry.options.get(
                                        CONF_ADVANCED_OPTIONS, {}
                                    ).get(CONF_DAYS_BACKWARD, DEFAULT_DAYS_BACKWARD),
                                ): vol.All(vol.Coerce(int), vol.Range(min=-90, max=90)),
                                vol.Optional(
                                    CONF_DAYS_FORWARD,
                                    default=self.config_entry.options.get(
                                        CONF_ADVANCED_OPTIONS, {}
                                    ).get(CONF_DAYS_FORWARD, DEFAULT_DAYS_FORWARD),
                                ): vol.All(vol.Coerce(int), vol.Range(min=-90, max=90)),
                            }
                        ),
                        {"collapsed": True},
                    ),
                }
            ),
            errors=errors,
            last_step=False,
        )

    async def async_step_calendar_config(self, user_input=None) -> ConfigFlowResult:
        """Handle calendar setup."""
        if user_input is not None:
            calendar_item = self._get_calendar_item()
            # A form without the filters, as sent before they were added, keeps them
            filters = user_input.get(CONF_FILTERS)
            if filters is not None and (invalid := _invalid_exclude(filters)):
                # Shown again with the input, so the pattern can be corrected
                return self._show_calendar_config(
                    calendar_item, user_input, filters, invalid
                )
            add_attribute_to_item(calendar_item, user_input, CONF_NAME)
            add_attribute_to_item(calendar_item, user_input, CONF_HOURS_FORWARD_TO_GET)
            add_attribute_to_item(calendar_item, user_input, CONF_HOURS_BACKWARD_TO_GET)
            add_attribute_to_item(calendar_item, user_input, CONF_MAX_RESULTS)
            if filters is not None:
                _save_filters(calendar_item, filters)
            return await self.async_step_calendar_config()

        if self._calendar_no == len(self._calendar_list_selected):
            return await self._async_tidy_up(self._user_input)

        self._calendar_no += 1
        calendar_item = self._get_calendar_item()
        return self._show_calendar_config(
            calendar_item, calendar_item, _form_filters(calendar_item)
        )

    def _show_calendar_config(self, calendar_item, values, filters, invalid=None):
        """Show the form of a calendar, filled with the values and filters."""
        return self.async_show_form(
            step_id="calendar_config",
            description_placeholders={
                CONF_ENTITY_NAME: self.config_entry.data[CONF_ENTITY_NAME],
                CONF_DEVICE_ID: calendar_item[CONF_DEVICE_ID],
                **(invalid or {}),
            },
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_NAME,
                        default=values[CONF_NAME],
                    ): cv.string,
                    vol.Required(
                        CONF_HOURS_FORWARD_TO_GET,
                        default=values.get(
                            CONF_HOURS_FORWARD_TO_GET, DEFAULT_HOURS_FORWARD_TO_GET
                        ),
                    ): int,
                    vol.Required(
                        CONF_HOURS_BACKWARD_TO_GET,
                        default=values.get(
                            CONF_HOURS_BACKWARD_TO_GET, DEFAULT_HOURS_BACKWARD_TO_GET
                        ),
                    ): int,
                    vol.Optional(
                        CONF_MAX_RESULTS,
                        description={"suggested_value": values.get(CONF_MAX_RESULTS)},
                    ): cv.positive_int,
                    vol.Optional(CONF_FILTERS): section(
                        self.add_suggested_values_to_schema(FILTERS_SCHEMA, filters),
                        # Open when a filter has to be corrected
                        {"collapsed": not invalid},
                    ),
                }
            ),
            errors={CONF_FILTERS: "invalid_exclude"} if invalid else {},
            last_step=self._calendar_no == len(self._calendar_list_selected),
        )

    def _get_calendar_item(self):
        for calendar in self._calendars:
            for entity in calendar[CONF_ENTITIES]:
                if (
                    entity[CONF_DEVICE_ID]
                    == self._calendar_list_selected[self._calendar_no - 1]
                ):
                    return entity
        return None  # pragma: no cover

    async def _async_delete_entities(self, device_id):
        # The entity is found by its unique id, which holds the calendar id
        for calendar in self._calendars:
            for entity in calendar[CONF_ENTITIES]:
                if entity[CONF_DEVICE_ID] == device_id:
                    await async_delete_calendar(
                        self.hass, self.config_entry, calendar[CONF_CAL_ID], device_id
                    )

    async def _async_tidy_up(self, user_input):
        await self.hass.async_add_executor_job(
            write_calendar_yaml_file, self._yaml_filepath, self._calendars
        )
        for calendar in self._calendar_list_selected_original:
            if calendar not in self._calendar_list_selected:
                await self._async_delete_entities(calendar)
        update = self.async_create_entry(title="", data=user_input)
        if (
            user_input == dict(self.config_entry.options)
            or self.config_entry.state is not config_entries.ConfigEntryState.LOADED
        ):
            # The update listener only reloads a loaded entry whose options changed
            self.hass.config_entries.async_schedule_reload(self._config_entry_id)
        return update


def _form_filters(calendar_item):
    """Get the filters of a calendar in the file, as the form shows them.

    A value the file does not accept is left out, as the form has no place for it.
    """
    return {
        CONF_SEARCH: _accepted(cv.string, calendar_item.get(CONF_SEARCH)),
        CONF_EXCLUDE: _accepted_list(cv.string, calendar_item.get(CONF_EXCLUDE)),
        CONF_SENSITIVITY_EXCLUDE: [
            sensitivity.value
            for sensitivity in _accepted_list(
                SENSITIVITY_VALUE, calendar_item.get(CONF_SENSITIVITY_EXCLUDE)
            )
        ],
        CONF_EXCLUDE_DECLINED: _accepted(
            cv.boolean, calendar_item.get(CONF_EXCLUDE_DECLINED)
        ),
        CONF_SHOW_AS_EXCLUDE: [
            show_as.value
            for show_as in _accepted_list(
                SHOW_AS_VALUE, calendar_item.get(CONF_SHOW_AS_EXCLUDE)
            )
        ],
    }


def _accepted(validator, value):
    """Get a value as the file schema reads it, or None if it is not accepted."""
    try:
        return validator(value)
    except vol.Invalid:
        return None


def _accepted_list(validator, values):
    """Get the values of a list the file schema accepts, as it reads them."""
    return [
        accepted
        for value in cv.ensure_list(values)
        if (accepted := _accepted(validator, value)) is not None
    ]


def _excludes(filters):
    """Get the exclude patterns, without the blank entries the form can send."""
    return [exclude for exclude in filters.get(CONF_EXCLUDE, []) if exclude.strip()]


def _invalid_exclude(filters):
    """Find the first exclude that is not a valid regular expression."""
    for exclude in _excludes(filters):
        try:
            re.compile(exclude)
        except re.error as err:
            return {"pattern": exclude, "error": str(err)}
    return {}


def _save_filters(calendar_item, filters):
    """Write the filters into the calendar's entry of the file."""
    search = filters.get(CONF_SEARCH, "")
    sensitivities = filters.get(CONF_SENSITIVITY_EXCLUDE, [])
    show_as_values = filters.get(CONF_SHOW_AS_EXCLUDE, [])
    values = {
        # Kept as typed, as spaces can be part of the text to search for
        CONF_SEARCH: search if search.strip() else None,
        CONF_EXCLUDE: _excludes(filters),
        CONF_SENSITIVITY_EXCLUDE: [
            value for value in SENSITIVITY_OPTIONS if value in sensitivities
        ],
        CONF_EXCLUDE_DECLINED: filters.get(CONF_EXCLUDE_DECLINED, False),
        # As MS365 names them, such as workingElsewhere, like the documentation
        CONF_SHOW_AS_EXCLUDE: [
            to_camel_case(value) for value in SHOW_AS_OPTIONS if value in show_as_values
        ],
    }
    for key, value in values.items():
        if value:
            calendar_item[key] = value
        else:
            # Left out when not set, so the file is as it was without the filter
            calendar_item.pop(key, None)
