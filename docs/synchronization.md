---
title: Synchronization
nav_order: 7
---

# Synchronization
The calendar integration supports two sets of time periods for synchronization. 

1. Within the configuration options for the integration under [Advanced options](./installation_and_configuration.md#advanced-options), are the master synchronization options for the integration. These settings define what set of events will be retrieved and stored for use by all aspects if Home Assistant usage (e.g. calendar pane or other calendar card). Accessing events within this range will not incur extra data retrieval commitments. Accessing data outside this range will require extra calls to the MS Graph API. The events of such a range are kept for up to 5 minutes, so showing the same range again in that time, such as on a dashboard, does not call MS Graph again. Every synchronization clears them, including the one that runs after a change made in Home Assistant, so a change made outside Home Assistant shows after the next synchronization at the latest. If MS Graph fails or cannot be reached for such a range, only the events within the synchronized range are shown. The range should not be set to smaller than that defined by item 2, but the integration will ensure that the minimum retrieved is that defined in item 2. The range is configured in **days**. The interval is configured in **seconds**.

1. Within the [calendar configuration](./calendar_configuration.md) is the start and end offsets for events that are added to the attributes of the calendar entity. The range is configured in **hours**.

The events are kept in memory only, not written to disk. When Home Assistant starts or the integration is reloaded, they are retrieved before the calendar entities are added, so the calendars start with their events. The `.storage/ms365_calendar.Storage-<entry_id>` file that earlier versions wrote is removed.

There is a balance to be made between how much data is retrieved at one time and performance of the Home Assistant UI. Previous to v1.5.0, the only event data retrieved on a scheduled basis was that defined in 2 above, which was done on an every 30 second basis. For people using other functionality, such as the calendar pane, this meant that any events needing to be displayed would be retrieved dynamically every time with no caching. With many calendars in use, performance could be poor.

If you have many calendars or many events, you may wish to synchronize less frequently, with the knowledge that events created outside HA would not be displayed until the next scheduled synchronization. If you are regularly displaying events from a wide range of dates, you may wish to increase the scheduled retrieval range, to reduce dynamic load time. If you only want to use a small range displayed in the entity attributes and never use anything else, then you can configure accordingly.

If a synchronization fails, because MS Graph returns an error or does not answer in time, or the token cannot be refreshed, the error is logged and the calendars keep the events of the last synchronization that worked, with the `sync_state` attribute set to `problem` until a synchronization works again. The events are only kept in memory, so if the first synchronization after Home Assistant starts or the integration reloads fails, the calendars have no events until a synchronization works. When Microsoft no longer accepts the token, Home Assistant also asks you to re-authenticate, see [Re-authentication](./authentication.md#re-authentication).
