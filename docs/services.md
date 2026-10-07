---
title: Services
nav_order: 15
---

# Services

##  Calendar Services
The create, modify, remove and respond actions are only available when `enable_update` is set, see [Installation and Configuration](./installation_and_configuration.md), and they only work on calendars you can edit. `get_calendar_events` is always available.

### ms365_calendar.create_calendar_event
Create an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. With `rrule` the event repeats, see [Repeating events](#repeating-events).
### ms365_calendar.modify_calendar_event
Modify an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars. It has no `rrule`, so it cannot change how a series repeats; do that in Outlook or, for the whole series, in the [Calendar Panel](./calendar_panel.md).
### ms365_calendar.remove_calendar_event
Remove an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars.
### ms365_calendar.respond_calendar_event
Respond to an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars.
### ms365_calendar.get_calendar_events
Get the events in a time range, with the same per-event detail as the calendar entity's `data` attribute - including `attendees` (email, type, response status), `organizer`, the calendar owner's `response`, `categories`, `sensitivity`, `show_as`, `uid` and the [location details](./sensor.md#location-details) (address, coordinates, type, room email and each place of an event held in several). Use it with `response_variable`. Unlike the core `calendar.get_events` action, which only returns summary, start, end, description and location, and unlike the `data` attribute, which only covers the entity's `start_offset`/`end_offset` window. Events left out by the calendar's exclude settings, such as `exclude_declined` and `show_as_exclude`, are left out here too.

#### Example create event service call

```yaml
service: ms365_calendar.create_calendar_event
target:
  entity_id:
    - calendar.user_primary
data:
  subject: Clean up the garage
  start: 2023-01-01T12:00:00+0000
  end: 2023-01-01T12:30:00+0000
  body: Remember to also clean out the gutters
  location: 1600 Pennsylvania Ave Nw, Washington, DC 20500
  sensitivity: Normal
  show_as: Busy
  attendees:
    - email: test@example.com
      type: Required
```

Response - Note uid is shown as an attribute of the entity_id since multiple entities can potentially be actioned at the same time.

```yaml
calendar.user_primary:
  uid: >-
    long_guid
```

#### Repeating events

`rrule` makes the created event the first of a series. It takes an RFC 5545 RRULE value without `RRULE:` in front, the same format as the repeat rule of an event in the Home Assistant calendar. The series starts on the date of `start`, and every occurrence has the time and length of the event.

```yaml
action: ms365_calendar.create_calendar_event
target:
  entity_id: calendar.user_primary
data:
  subject: Team stand-up
  start: "2026-01-05 09:00:00"
  end: "2026-01-05 09:15:00"
  rrule: FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10
```

| Repeats | `rrule` |
| --- | --- |
| Every Monday and Wednesday, 10 times | `FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10` |
| Every other Tuesday and Thursday, until 31 March 2026 | `FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,TH;UNTIL=20260331` |
| Every workday | `FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR` |
| On the 15th of every month | `FREQ=MONTHLY;BYMONTHDAY=15` |
| On the second Tuesday of every month | `FREQ=MONTHLY;BYDAY=+2TU` |
| On the last day of every month, 12 times | `FREQ=MONTHLY;BYMONTHDAY=-1;COUNT=12` |
| On the last Friday of every third month | `FREQ=MONTHLY;INTERVAL=3;BYDAY=-1FR` |
| Every year on the date of `start`, 5 times | `FREQ=YEARLY;COUNT=5` |
| Every third day, until 31 December 2026 | `FREQ=DAILY;INTERVAL=3;UNTIL=20261231` |

Outlook only has some kinds of series, so a rule can only have these parts:

| Part | Value |
| --- | --- |
| `FREQ` | Required: `DAILY`, `WEEKLY`, `MONTHLY` or `YEARLY` |
| `INTERVAL` | Repeat every so many days, weeks, months or years, `1` or more. Without it, `1` |
| `COUNT` | End after so many occurrences, `1` or more |
| `UNTIL` | End on this date, such as `20261231`. A date and time ending in `Z`, such as `20261231T230000Z`, is in UTC and ends on the local date of that time |
| `BYDAY` | With `WEEKLY`, the days of the week, such as `MO,WE,FR`. With `MONTHLY`, one day of the week in a given week: `+1` to `+4` for the first to the fourth or `-1` for the last, such as `+2TU` or `-1FR` |
| `BYMONTHDAY` | With `MONTHLY`, one day of the month: `1` to `31`, or `-1` for the last day of the month |

Use `COUNT` or `UNTIL`, not both; without either, the series has no end. A weekly series without `BYDAY` repeats on the day of the week of `start`, a monthly series without `BYDAY` or `BYMONTHDAY` on its day of the month, and a yearly series always repeats on the date of `start`. If the date of `start` does not fit the rule, the series starts on the first date after it that does.

A rule with anything else is refused with an error that names the part, rather than creating a different series. For example `FREQ=HOURLY`, `BYMONTH`, `BYSETPOS`, `BYHOUR` or `WKST`, `BYDAY` with `DAILY` or `YEARLY`, a monthly `BYDAY` without a week (`MO`) or with several days, `BYDAY` and `BYMONTHDAY` together, or a week written without its sign (`1MO` instead of `+1MO`).

Two things work differently in Outlook than RFC 5545 describes:

- In a month that does not have the day, such as the 31st, the occurrence falls on the last day of that month, where RFC 5545 skips the month.
- Outlook starts the week on Sunday. This only matters for a series every 2 or more weeks on Sunday and other days: Sunday counts with the days after it, where RFC 5545 counts it with the days before it.

#### Example get events service call

{% raw %}
```yaml
action: ms365_calendar.get_calendar_events
target:
  entity_id: calendar.user_primary
data:
  start_date_time: "{{ now().isoformat() }}"
  end_date_time: "{{ (now() + timedelta(days=3)).isoformat() }}"
response_variable: events
```
{% endraw %}

The response is keyed by entity: `events['calendar.user_primary'].events` is a list of events, each with `summary`, `start`, `end`, `all_day`, `description`, `location`, `location_details`, `locations`, `categories`, `sensitivity`, `show_as`, `reminder`, `organizer`, `response`, `attendees` and `uid`. `response` is the calendar owner's response to the event: `accepted`, `tentatively_accepted`, `declined`, `not_responded` or `organizer`, or `null` when MS365 has no response for it. On your own calendars this is your own response; for shared and group calendars, see [Sensors](./sensor.md). `location_details` and `locations` are described under [location details](./sensor.md#location-details).

```yaml
calendar.user_primary:
  events:
    - summary: Coffee with Alex
      start: "2025-03-01T10:00:00+01:00"
      end: "2025-03-01T11:00:00+01:00"
      all_day: false
      description: ""
      location: Fourth Coffee
      location_details:
        address:
          street: 4567 Main St
          city: Redmond
          state: WA
          postal_code: "98052"
          country: United States
        coordinates:
          latitude: 47.672
          longitude: -122.103
        type: local_business
      locations: null
      categories: []
      sensitivity: Normal
      show_as: Busy
      reminder:
        minutes: 15
        is_on: true
      organizer: alex@example.com
      response: accepted
      attendees:
        - email: me@example.com
          type: required
          status: accepted
      uid: long_guid
```
