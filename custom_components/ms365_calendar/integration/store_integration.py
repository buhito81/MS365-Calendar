"""MS365 Calendar local storage."""

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const_integration import DOMAIN
from .sync.store import CalendarStore

STORAGE_KEY_FORMAT = "{domain}.Storage-{entry_id}"
STORAGE_VERSION = 1

_LOGGER = logging.getLogger(__name__)


class LocalCalendarStore(CalendarStore):
    """Storage of calendar and event data, held in memory.

    The events are not written to disk: the file they were written to could not be
    turned back into events after a restart, so it cost time and kept private data
    for nothing. The store is only used to remove a file an older version wrote.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize LocalCalendarStore."""
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            STORAGE_KEY_FORMAT.format(domain=DOMAIN, entry_id=entry_id),
            private=True,
        )
        self._data: dict[str, Any] = {}

    async def async_load(self) -> dict[str, Any] | None:
        """Load data."""
        return self._data

    async def async_save(self, data: dict[str, Any]) -> None:
        """Save data."""
        self._data = data

    async def async_remove(self) -> None:
        """Remove data."""
        await self._store.async_remove()
