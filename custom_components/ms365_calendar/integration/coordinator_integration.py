"""Calendar coordinator processing."""

from collections.abc import Iterable
from datetime import datetime, timedelta
import logging

from msal.exceptions import MsalServiceError
from requests.exceptions import (
    ConnectionError as RequestConnectionError,
    HTTPError,
    RetryError,
    Timeout,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OK, STATE_PROBLEM, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.network import get_url
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from O365.calendar import Event  # pylint: disable=no-name-in-module)

from ..const import CONF_ENTITY_NAME, TOKEN_FILE_EXPIRED
from ..helpers.utils import token_refresh_refused, token_refresh_unavailable
from .const_integration import (
    CONF_ADVANCED_OPTIONS,
    CONF_DAYS_BACKWARD,
    CONF_DAYS_FORWARD,
    CONF_HOURS_BACKWARD_TO_GET,
    CONF_HOURS_FORWARD_TO_GET,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DAYS_BACKWARD,
    DEFAULT_DAYS_FORWARD,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .sync.sync import MS365CalendarEventSyncManager
from .sync.timeline import MS365Timeline
from .utils_integration import get_end_date, get_start_date

_LOGGER = logging.getLogger(__name__)
# Maximum number of upcoming events to consider for state changes between
# coordinator updates.
# MAX_UPCOMING_EVENTS = 20
# How long the events of a range outside the synced window are kept, as a
# dashboard asks for the range it shows again on every state update
RANGE_CACHE_TIME = timedelta(minutes=5)


class MS365CalendarSyncCoordinator(DataUpdateCoordinator):
    """Coordinator for calendar RPC calls that use an efficient sync."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        sync: MS365CalendarEventSyncManager,
        name: str,
        entity,
    ) -> None:
        """Create the CalendarSyncUpdateCoordinator."""
        update_interval = entry.options.get(CONF_ADVANCED_OPTIONS, {}).get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=timedelta(seconds=update_interval),
        )
        days_backward = entry.options.get(CONF_ADVANCED_OPTIONS, {}).get(
            CONF_DAYS_BACKWARD, DEFAULT_DAYS_BACKWARD
        )
        days_forward = entry.options.get(CONF_ADVANCED_OPTIONS, {}).get(
            CONF_DAYS_FORWARD, DEFAULT_DAYS_FORWARD
        )
        self.sync = sync
        # self._upcoming_timeline: MS365Timeline | None = None
        # self.event = None
        self._sync_event_min_time = timedelta(
            days=(min(entity.get(CONF_HOURS_BACKWARD_TO_GET) / 24, days_backward))
        )
        self._sync_event_max_time = timedelta(
            days=(max(entity.get(CONF_HOURS_FORWARD_TO_GET) / 24, days_forward))
        )
        self._last_sync_min = None
        self._last_sync_max = None
        self.entity = entity
        self._error = False
        self.sync_state = STATE_UNKNOWN
        self._range_cache = {}

    async def async_refresh(self) -> None:
        """Refresh data and drop the kept ranges, so a change made here shows."""
        self._range_cache.clear()
        await super().async_refresh()

    async def _async_update_data(self) -> MS365Timeline:
        """Fetch data from API endpoint."""
        _LOGGER.debug("Started fetching %s data", self.name)

        self._last_sync_min = dt_util.now() + self._sync_event_min_time
        self._last_sync_max = dt_util.now() + self._sync_event_max_time
        try:
            await self.sync.run(self._last_sync_min, self._last_sync_max)
            self.sync_state = STATE_OK
            # The token works again, such as after a reconfigure
            ir.async_delete_issue(self.hass, DOMAIN, self._token_issue_id)
        except (HTTPError, RetryError, RequestConnectionError, Timeout) as err:
            _LOGGER.error(
                "Error syncing calendar events from MS Graph, fetching from cache: %s",
                err,
            )
            self.sync_state = STATE_PROBLEM
        except (MsalServiceError, RuntimeError) as err:
            if not self._async_token_error(err):
                raise
            _LOGGER.error("Unable to refresh the token, fetching from cache: %s", err)
            self.sync_state = STATE_PROBLEM

        return await self.sync.store_service.async_get_timeline(
            dt_util.get_default_time_zone()
        )

        # self._upcoming_timeline = timeline
        # return timeline

    async def async_get_events(
        self, start_date: datetime, end_date: datetime
    ) -> Iterable[Event]:
        """Get all events in a specific time frame."""
        if not self.data:
            raise HomeAssistantError(
                "Unable to get events: Sync from server has not completed"
            )

        # If the request is for outside of the synced data, manually request it now,
        # and keep it for a few minutes
        if start_date < self._last_sync_min or end_date > self._last_sync_max:
            cached = self._range_cache.get((start_date, end_date))
            if cached and dt_util.utcnow() < cached[0]:
                return cached[1]
            _LOGGER.debug(
                "Fetch events from api - %s - %s - %s", self.name, start_date, end_date
            )
            try:
                return await self._async_list_range(start_date, end_date)
            except (HTTPError, RetryError, RequestConnectionError, Timeout) as err:
                self._log_error(
                    "Error getting calendar event range "
                    "from MS Graph, fetching from cache.",
                    err,
                )
            except (MsalServiceError, RuntimeError) as err:
                if not self._async_token_error(err):
                    raise
                self._log_error(
                    "Unable to refresh the token, fetching from cache.", err
                )
        _LOGGER.debug(
            "Fetch events from cache - %s - %s - %s",
            self.name,
            start_date,
            end_date,
        )

        return self.data.overlapping(
            start_date,
            end_date,
        )

    async def _async_list_range(self, start_date, end_date):
        """Get the events of a range from MS Graph and keep them for a while."""
        events = await self.sync.async_list_events(start_date, end_date)
        # It worked, so log the next failure as a new one
        self._error = False
        now = dt_util.utcnow()
        self._range_cache = {
            key: value for key, value in self._range_cache.items() if now < value[0]
        }
        # Keep it at least until just after the next update writes the state again
        keep = max(RANGE_CACHE_TIME, self.update_interval + timedelta(minutes=1))
        self._range_cache[(start_date, end_date)] = (now + keep, events)
        return events

    def get_current_event(self):
        """Get the current event."""

        # Not possible to get this situation I beleieve
        # if not self.data:
        #     _LOGGER.debug(
        #         "No current event found for %s",
        #         self.sync.calendar_id,
        #     )
        #     self.event = None
        #     return None

        #
        # Get events that are current now
        #
        today = dt_util.utcnow()

        current_events = self.data.overlapping(
            today,
            today,
        )
        started_event = None
        not_started_event = None
        all_day_event = None
        for event in current_events:
            if event.is_all_day:
                if not all_day_event:
                    all_day_event = event
                continue
            if not started_event and self.is_started(event):
                started_event = event

        #
        # If no current events, then find unfinished event within next day
        #
        if not started_event and not all_day_event:
            events = self.data.overlapping(
                today,
                today + timedelta(days=1),
            )
            for event in events:
                if event.is_all_day:
                    continue  # pragma: no cover
                if self.is_started(event):
                    continue  # pragma: no cover
                if (
                    not self.is_finished(event)
                    and not event.is_all_day
                    and not not_started_event
                ):
                    not_started_event = event

        vevent = None
        if started_event:
            vevent = started_event
        elif all_day_event:
            vevent = all_day_event
        elif not_started_event:
            vevent = not_started_event

        return vevent

    @staticmethod
    def is_started(vevent):
        """Is it over."""
        return dt_util.utcnow() >= MS365CalendarSyncCoordinator.to_datetime(
            get_start_date(vevent)
        )

    @staticmethod
    def is_finished(vevent):
        """Is it over."""
        return dt_util.utcnow() >= MS365CalendarSyncCoordinator.to_datetime(
            get_end_date(vevent)
        )

    @staticmethod
    def to_datetime(obj):
        """To datetime."""
        if not isinstance(obj, datetime):
            date_obj = dt_util.start_of_local_day(
                dt_util.dt.datetime.combine(obj, dt_util.dt.time.min)
            )  # pragma: no cover
        else:
            date_obj = obj

        return dt_util.as_utc(date_obj)

    def _log_error(self, error, err):
        if not self._error:
            _LOGGER.warning("%s - %s", error, err)
            self._error = True
        else:
            _LOGGER.debug("Repeat error - %s - %s", error, err)

    @property
    def _token_issue_id(self) -> str:
        return f"{TOKEN_FILE_EXPIRED}_{self.config_entry.entry_id}"

    def _async_token_error(self, err: Exception) -> bool:
        """Check for a failed token refresh, and raise the repair issue if needed."""
        if not token_refresh_refused(err):
            return token_refresh_unavailable(err)
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._token_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=TOKEN_FILE_EXPIRED,
            translation_placeholders={
                "domain": DOMAIN,
                "url": f"{get_url(self.hass)}/config/integrations/integration/{DOMAIN}",
                CONF_ENTITY_NAME: self.config_entry.data.get(CONF_ENTITY_NAME),
            },
        )
        return True
