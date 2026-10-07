---
title: Services
nav_order: 15
---

# Services

##  Calendar Services
The create, modify, remove and respond actions are only available when `enable_update` is set, see [Installation and Configuration](./installation_and_configuration.md), and they only work on calendars you can edit. `get_calendar_events` is always available.

### ms365_calendar.create_calendar_event
Create an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab.
### ms365_calendar.modify_calendar_event
Modify an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars.
### ms365_calendar.remove_calendar_event
Remove an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars.
### ms365_calendar.respond_calendar_event
Respond to an event in the specified calendar - All parameters are shown in the available parameter list on the Developer Tools/Actions tab. Not possible for group calendars.
### ms365_calendar.get_calendar_events
Get the events in a time range, with the same per-event detail as the calendar entity's `data` attribute - including `attendees` (email, type, response status), `organizer`, the calendar owner's `response`, `categories`, `sensitivity`, `show_as`, `uid`, the [location details](./sensor.md#location-details) (address, coordinates, type, room email and each place of an event held in several) and the [online meeting and links](./sensor.md#online-meetings-and-links) (the service and join link of an online meeting, such as a Teams meeting, and the link that opens the event in Outlook on the web). Use it with `response_variable`. Unlike the core `calendar.get_events` action, which only returns summary, start, end, description and location, and unlike the `data` attribute, which only covers the entity's `start_offset`/`end_offset` window. Events left out by the calendar's exclude settings, such as `exclude_declined` and `show_as_exclude`, are left out here too.

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

The response is keyed by entity: `events['calendar.user_primary'].events` is a list of events, each with `summary`, `start`, `end`, `all_day`, `description`, `location`, `location_details`, `locations`, `online_meeting`, `categories`, `sensitivity`, `show_as`, `reminder`, `organizer`, `response`, `attendees`, `uid` and `web_link`. `response` is the calendar owner's response to the event: `accepted`, `tentatively_accepted`, `declined`, `not_responded` or `organizer`, or `null` when MS365 has no response for it. On your own calendars this is your own response; for shared and group calendars, see [Sensors](./sensor.md). `location_details` and `locations` are described under [location details](./sensor.md#location-details), and `online_meeting` and `web_link` under [online meetings and links](./sensor.md#online-meetings-and-links).

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
      online_meeting: null
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
      web_link: https://outlook.office365.com/owa/?itemid=...&exvsurl=1&path=/calendar/item
    - summary: Project review
      start: "2025-03-01T14:00:00+01:00"
      end: "2025-03-01T15:00:00+01:00"
      all_day: false
      description: ""
      location: Microsoft Teams Meeting
      location_details: null
      locations: null
      online_meeting:
        provider: teams_for_business
        join_url: https://teams.microsoft.com/l/meetup-join/19%3ameeting_...
      categories: []
      sensitivity: Normal
      show_as: Busy
      reminder:
        minutes: 15
        is_on: true
      organizer: me@example.com
      response: organizer
      attendees:
        - email: alex@example.com
          type: required
          status: accepted
      uid: long_guid
      web_link: https://outlook.office365.com/owa/?itemid=...&exvsurl=1&path=/calendar/item
```
