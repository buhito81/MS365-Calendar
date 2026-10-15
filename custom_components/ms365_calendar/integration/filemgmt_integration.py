"""Calendar file management processes."""

import logging
import os

from voluptuous.error import Error as VoluptuousError
import yaml

from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant

from ..classes.config_entry import MS365ConfigEntry
from ..const import CONF_ENTITY_NAME
from ..helpers.filemgmt import build_config_file_path
from .const_integration import (
    CONF_CAL_ID,
    CONF_DEVICE_ID,
    CONF_ENTITIES,
    CONF_TRACK,
    CONST_GROUP,
    YAML_CALENDARS_FILENAME,
)
from .schema_integration import YAML_CALENDAR_DEVICE_SCHEMA

_LOGGER = logging.getLogger(__name__)


def load_yaml_file(path, item_id, display_error=False):
    """Load the ms365 yaml file."""
    items = {}
    for item in read_calendar_yaml_file(path):
        try:
            items[item[item_id]] = YAML_CALENDAR_DEVICE_SCHEMA(item)
        except VoluptuousError as exception:
            # keep going
            if display_error:
                _LOGGER.warning(
                    "Invalid Data - entry ignored until it is fixed in file %s - for item %s: %s",
                    path,
                    item,
                    exception,
                )

    return items


def validate_calendar(calendar):
    """Validate a calendar entry, None if it is not valid."""
    try:
        return YAML_CALENDAR_DEVICE_SCHEMA(calendar)
    except VoluptuousError:
        return None


def write_yaml_file(yaml_filepath, cal):
    """Write to the calendar file."""
    dirpath = os.path.dirname(yaml_filepath)
    if not os.path.isdir(dirpath):
        os.makedirs(dirpath)  # pragma: no cover
    with open(yaml_filepath, "a", encoding="UTF8") as out:
        yaml.dump([cal], out, default_flow_style=False, encoding="UTF8")
        out.close()


def _get_calendar_info(calendar, track_new_devices):
    """Convert data from MS365 into DEVICE_SCHEMA."""
    return YAML_CALENDAR_DEVICE_SCHEMA(
        {
            CONF_CAL_ID: calendar.calendar_id,
            CONF_ENTITIES: [
                {
                    CONF_TRACK: track_new_devices,
                    CONF_NAME: calendar.name,
                    CONF_DEVICE_ID: calendar.name,
                }
            ],
        }
    )


async def async_update_calendar_file(
    entry: MS365ConfigEntry, calendar, hass: HomeAssistant, track_new_devices
):
    """Update the calendar file."""
    path = build_yaml_filename(entry, YAML_CALENDARS_FILENAME)
    yaml_filepath = build_yaml_file_path(hass, path)
    existing_calendars = await hass.async_add_executor_job(
        read_calendar_yaml_file, yaml_filepath
    )
    cal = _get_calendar_info(calendar, track_new_devices)
    # Also check entries that are not valid, so a calendar is not added twice
    if cal[CONF_CAL_ID] in [
        item.get(CONF_CAL_ID) for item in existing_calendars if isinstance(item, dict)
    ]:
        return
    await hass.async_add_executor_job(write_yaml_file, yaml_filepath, cal)


async def async_check_for_deleted_calendars(
    entry: MS365ConfigEntry, calendars, hass: HomeAssistant
):
    """Delete removed calendars from yaml file."""
    path = build_yaml_filename(entry, YAML_CALENDARS_FILENAME)
    yaml_filepath = build_yaml_file_path(hass, path)

    existing_calendars = await hass.async_add_executor_job(
        load_yaml_file, yaml_filepath, CONF_CAL_ID, True
    )
    deleted_calendars = []
    for e_cal_id in existing_calendars:
        if e_cal_id.startswith(CONST_GROUP) or e_cal_id in [
            calendar.calendar_id for calendar in calendars
        ]:
            continue
        _LOGGER.info("Calendar deleted from %s: %s", path, e_cal_id)

        deleted_calendars.append(existing_calendars[e_cal_id])
    if deleted_calendars:
        await hass.async_add_executor_job(
            _remove_calendars_from_file, yaml_filepath, deleted_calendars
        )
    return deleted_calendars


def _remove_calendars_from_file(yaml_filepath, deleted_calendars):
    """Remove the deleted calendars, other entries are written back as they are."""
    deleted_ids = [calendar[CONF_CAL_ID] for calendar in deleted_calendars]
    updated_calendars = []
    for calendar in read_calendar_yaml_file(yaml_filepath):
        valid_calendar = validate_calendar(calendar)
        if not valid_calendar or valid_calendar[CONF_CAL_ID] not in deleted_ids:
            updated_calendars.append(calendar)
    write_calendar_yaml_file(yaml_filepath, updated_calendars)


def build_yaml_filename(conf: MS365ConfigEntry, filename):
    """Create the token file name."""

    return filename.format(f"_{conf.data.get(CONF_ENTITY_NAME)}")


def build_yaml_file_path(hass: HomeAssistant, yaml_filename):
    """Create yaml path."""
    return build_config_file_path(hass, yaml_filename)


def read_calendar_yaml_file(yaml_filepath):
    """Read the yaml file."""
    try:
        with open(yaml_filepath, encoding="utf8") as file:
            return yaml.safe_load(file) or []
    except FileNotFoundError:
        # When YAML file could not be loaded
        return []


def write_calendar_yaml_file(yaml_filepath, contents):
    """Write the yaml file."""
    with open(yaml_filepath, "w", encoding="UTF8") as out:
        yaml.safe_dump(contents, out, default_flow_style=False, encoding="UTF8")
