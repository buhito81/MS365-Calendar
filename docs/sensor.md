---
title: Sensors
nav_order: 8
---

# Sensors
## Calendar Sensor
The status of the calendar sensor indicates (on/off) whether there is an event on at the current time. The `message`, `all_day`, `start_time`, `end_time`, `location` and `description` attributes provide details of the current or next event. A non-all-day event is favoured over all_day events. To act a set time before or after an event, use a [calendar trigger](https://www.home-assistant.io/integrations/calendar/#automation) with an `offset`.

The `data` attribute provides an array of events for the period defined by the `start_offset` and `end_offset` in `ms365_calendars_<entity_name>.yaml`. Individual array elements can be accessed using the template notation `states.calendar.<entity_name>_calendar.attributes.data[0...n]`.

Each event has `summary`, `start`, `end`, `all_day`, `description`, `location`, `categories`, `sensitivity`, `show_as`, `reminder`, `organizer`, `response`, `attendees` and `uid`. `response` is the calendar owner's response to the event, in the same form as the `status` of each attendee: `accepted`, `tentatively_accepted`, `declined`, `not_responded` or `organizer`, or empty (`null`) when MS365 has no response for it. On your own calendars this is your own response. On a calendar someone else has shared with you, or with `shared_mailbox`, it is the response of the person whose calendar it is, not yours. On a group calendar it is the group's, which is usually `organizer`. Events the owner has declined can be left out with `exclude_declined`, see [Calendar configuration](./calendar_configuration.md#exclude-declined).
