---
title: Sensors
nav_order: 8
---

# Sensors
## Calendar Sensor
The status of the calendar sensor indicates (on/off) whether there is an event on at the current time. The `message`, `all_day`, `start_time`, `end_time`, `location` and `description` attributes provide details of the current event or, when there is none, of the next event that starts within 24 hours. An all-day event is only shown while it is on. An event that has started is favoured over an all-day event, but an all-day event that is on is favoured over an event that has not started yet. To act a set time before or after an event, use a [calendar trigger](https://www.home-assistant.io/integrations/calendar/#automation) with an `offset`.

The `sync_state` attribute is `ok` when the last synchronization with MS Graph worked, and `problem` when it failed, for example because MS Graph returned an error, could not be reached or did not answer in time, or the token could not be refreshed. The calendar then keeps the events of the last synchronization that worked since Home Assistant started, see [Synchronization](./synchronization.md). The `color` attribute is the colour of the calendar in Outlook, or `auto` when no colour was chosen for it, and `hex_color` is its colour code, such as `#cf2b36`, which MS365 only has when a colour was chosen. Group calendars have neither attribute.

The `data` attribute provides an array of the events in the period defined by the `start_offset` and `end_offset` in `ms365_calendars_<entity_name>.yaml`, sorted by start, so `data[0]` is the event that starts first. When `max_results` is set, only the first `max_results` of these events are kept. The attribute is rebuilt at every synchronization (see [`update_interval`](./installation_and_configuration.md#advanced-options)), and the period is counted from the time of that synchronization. Individual array elements can be accessed using the template notation `states.calendar.<entity_name>_<device_id>.attributes.data[0...n]`, with `<entity_name>_<device_id>` in lower case and every character other than a letter or digit (such as a space, `-` or `'`) replaced by `_` (see [Calendar configuration](./calendar_configuration.md)). For example, `states.calendar.account1_calendar.attributes.data[0]` for a calendar with device_id `Calendar`.

Each event has `summary`, `start`, `end`, `all_day`, `description`, `location`, `location_details`, `locations`, `online_meeting`, `categories`, `sensitivity`, `show_as`, `reminder`, `organizer`, `response`, `attendees`, `uid` and `web_link`. `response` is the calendar owner's response to the event, in the same form as the `status` of each attendee: `accepted`, `tentatively_accepted`, `declined`, `not_responded` or `organizer`, or empty (`null`) when MS365 has no response for it. On your own calendars this is your own response. On a calendar someone else has shared with you, or with `shared_mailbox`, it is the response of the person whose calendar it is, not yours. On a group calendar it is the group's, which is usually `organizer`. Events the owner has declined can be left out with `exclude_declined`, see [Calendar configuration](./calendar_configuration.md#exclude-declined).

### Location details

`location` is the name of the place, as Outlook shows it. When MS Graph knows more about the place, such as for an address picked from the suggestions in Outlook or for a booked room, `location_details` has it, with only the parts that are filled in:

- `address` - `street`, `city`, `state`, `postal_code` and `country`
- `coordinates` - `latitude` and `longitude`
- `type` - the kind of place, such as `conference_room`, `street_address`, `business_address` or `local_business`. A place typed in as plain text has no type
- `email` - the email address of a room
- `uri` - a link for the place

`location_details` is `null` when there is nothing more than the name.

An event can be held in several places, such as a room and a home office. `location` then has all their names, separated by `; `, and `locations` lists each place with its `name` and the same details. For an event in one place, or none, `locations` is `null`.

```yaml
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
```

```yaml
location: Room 1; Head office
location_details: null
locations:
  - name: Room 1
    type: conference_room
    email: room1@example.com
  - name: Head office
    address:
      street: 1 Station Square
      city: Utrecht
      postal_code: 3511 ED
      country: Netherlands
```

For example, this template gives the address of the first event as one line, such as for a travel time to it. It gives nothing when there is no event in the period, or no address:

{% raw %}
```
{% set events = state_attr('calendar.user_primary', 'data') or [] %}
{% set details = events[0].location_details if events else none %}
{% if details and details.address is defined %}
  {{ details.address.values() | join(', ') }}
{% endif %}
```
{% endraw %}

### Online meetings and links

`online_meeting` is set for an online meeting, such as a Teams meeting, and is `null` for any other event. It has:

- `provider` - the service of the meeting: `teams_for_business`, `skype_for_business` or `skype_for_consumer`, or `null` when MS Graph does not say which
- `join_url` - the link to join the meeting, or `null` when MS365 has none for it. This is the join link MS Graph has for the meeting. Some older meetings, such as Skype meetings, only have a link in the older `onlineMeetingUrl` field of MS Graph, which is then used

Only the meetings MS365 knows as online meetings are shown. A link to another service, such as Zoom or Webex, that is only in the text of the event is not looked for.

`web_link` is the link that opens the event in Outlook on the web. It only opens the event for someone who can open that calendar there.

```yaml
online_meeting:
  provider: teams_for_business
  join_url: https://teams.microsoft.com/l/meetup-join/19%3ameeting_...
web_link: https://outlook.office365.com/owa/?itemid=...&exvsurl=1&path=/calendar/item
```

Anyone who has the join link can use it to join the meeting, or wait in its lobby, so take care where you show or send it, such as in a notification or on a dashboard others can see. The `data` attribute is not kept in the history of the calendar, and the integration's diagnostics have no event data, so the links are in neither.

For example, this template gives the join link of the first online meeting in the period that has one, such as for a button on a dashboard. It gives nothing when there is none:

{% raw %}
```
{% set events = state_attr('calendar.user_primary', 'data') or [] %}
{% set meetings = events | map(attribute='online_meeting') | select | selectattr('join_url') | list %}
{{ meetings[0].join_url if meetings else '' }}
```
{% endraw %}
