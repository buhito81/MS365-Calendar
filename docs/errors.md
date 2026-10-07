---
title: Errors
nav_order: 19
---

# Errors

Guidance on logged errors for the MS365 Integrations can be found on the MS365 Home Assistant [Errors](https://rogerselwyn.github.io/MS365-HomeAssistant/errors.html) page.

When the integration starts, the warnings `Token has expired for account`, `Client Secret expired for account` and `Token error for account` mean Microsoft no longer accepts the token or the client secret. Home Assistant then asks you to re-authenticate the integration, see [Re-authentication](./authentication.md#re-authentication).

While Home Assistant is running, the logged message `Unable to refresh the token, fetching from cache` means the token could not be refreshed. The calendars keep showing the events synced before, with the `sync_state` attribute set to `problem`.

* If Microsoft refused the token or the client secret (for example `invalid_grant`), Home Assistant also asks you to re-authenticate, see [Re-authentication](./authentication.md#re-authentication). Until you do, a create, modify, remove or respond action, or a change in the calendar panel, fails with `The token can no longer be refreshed, please reconfigure the integration and re-authenticate`. `get_calendar_events` and the calendar panel still show the events synced before.
* If the login service was only busy (for example `temporarily_unavailable`), or another refresh had the token file locked, you do not need to re-authenticate. The next sync tries again. Until then, a create, modify, remove or respond action, or a change in the calendar panel, fails with `Unable to connect to MS Graph`.

When MS Graph or the Microsoft login service cannot be reached when the integration starts, answers with a server error, or does not answer within 30 seconds, the integration shows `Unable to connect to MS Graph: <error>` and Home Assistant retries the setup by itself. Nothing needs to be done. If MS Graph only fails while the events are being retrieved, after the calendars have been read, the integration still sets up, and the calendars start without events and with `sync_state` set to `problem` until a sync works. While Home Assistant is running, such errors are logged as `Error syncing calendar events from MS Graph, fetching from cache`, or as `Unable to refresh the token, fetching from cache` when the login service fails or is busy. The calendars keep the events synced before, with `sync_state` set to `problem`, until a sync works again.
