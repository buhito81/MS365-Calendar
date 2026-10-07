---
title: Calendar Configuration
nav_order: 6
---

# Calendar configuration
The integration uses an external `ms365_calendars_<entity_name>.yaml` file which is stored in the `ms365_storage` directory. Much of this can be managed by the UI, but more complex items must be managed via the yaml file. Items that can by the standard integration configure UI are:
* name
* track
* end_offset
* start_offset
* max_results

Group calendars plus device_id, search, exclude, sensitivity_exclude, exclude_declined and show_as_exclude must be managed via the yaml file.

## Example Calendar yaml:
```yaml
- cal_id: xxxx
  entities:
  - device_id: work_calendar
    end_offset: 24
    name: My Work Calendar
    start_offset: 0
    track: true

- cal_id: xxxx
  entities:
  - device_id: birthdays
    end_offset: 24
    name: Birthdays
    start_offset: 0
    track: true
```

### Calendar yaml configuration variables

Key | Type | Required | Description
-- | -- | -- | --
`cal_id` | `string` | `True` | Microsoft 365 generated unique ID, DO NOT CHANGE
`entities` | `list<entity>` | `True` | List of entities (see below) to generate from this calendar

### Entity configuration

Key | Type | Required | Description
-- | -- | -- | --
`device_id` | `string` | `True` | The entity_id will be "calendar.{entity_name}_{device_id}"
`name` | `string` | `True` | The name of your sensor that you’ll see in the frontend.
`track` | `boolean` | `True` | **True**=Create calendar entity. False=Don't create entity
`search` | `string` | `False` | Only get events if subject contains this string. Enter it as it appears in the subject; an apostrophe does not need to be doubled
`exclude` | `list[string/regex]` | `False` | Exclude events where the subject contains any one of items in the list of strings
`start_offset` | `integer` | `False` | Number of hours to offset the start time to search for events for (negative numbers to offset into the past).
`end_offset` | `integer` | `False` | Number of hours to offset the end time to search for events for (negative numbers to offset into the past).
`max_results` | `integer` | `False` | Max number of events in the `data` attribute. Default is no limit.
`sensitivity_exclude` | `list[string]` | `False` | List of sensitivities to exclude from the calendar (`normal`/`personal`/`private`/`confidential`)
`exclude_declined` | `boolean` | `False` | True=Exclude the events you have declined. Default is false
`show_as_exclude` | `list[string]` | `False` | List of show as values to exclude from the calendar (`free`/`tentative`/`busy`/`oof`/`workingElsewhere`/`unknown`)

## Group calendars

The integration supports Group calendars in a fairly simple form. The below are the constraints.
* This gets the default calendar for the group.
* There is no discovery. You will need to find them in the MS Graph api. Using the MS Graph API you can call https://graph.microsoft.com/v1.0/me/transitiveMemberOf/microsoft.graph.group to get the groups. You will need the relevant group's `id` for configuration purposes, see below
* You can create events using the standard service, but you cannot modify/delete/respond to them.
* The group calendar is checked when the integration starts. If MS Graph rejects the request, for example because the id is wrong, the group has been deleted or you no longer have access, a warning is logged and no entity is created for it. If MS Graph is only busy or does not answer in time at that moment, the entity is still created.

To configure a Group Calendar, add an extra section to `ms365_calendars_<entity_name>.yaml`. Set `cal_id` to `group:xxxxxxxxxxxxxxx` using the ID you found via the api above. Make sure to set the `device_id` to something unique.

```yaml
  - cal_id: group:xxxx
    entities:
    - device_id: group_calendar
      end_offset: 24
      name: Group Calendar
      start_offset: 0
      track: true
  ```

## Exclude

To exclude calendar items from being displayed, the exclude attribute can be used. This takes straight strings or can be configured with a regex for more complex exclusions. Meetings the organizer has cancelled are always left out, so they do not need an exclude.

```yaml
    exclude:
     - "^Private"
     - "^In.*Junk$"
```

Each item is used as a regex, so characters such as `[ ] ( ) . * + ?` have their regex meaning; to match them as text, escape them with `\` inside single quotes, e.g. `'\[External\]'`. An item that is not a valid regex, such as `"(Optional"`, is matched as plain text and a warning is logged.

## Sensitivity Exclude

To exclude specific sensitivities from being included in the calendar.

```yaml
    sensitivity_exclude:
     - private
     - confidential
```

## Exclude Declined

Events you have declined can stay on your calendar. To exclude them, set `exclude_declined` to `true`. Your own response to each event is shown in its `response` field, see [Sensors](./sensor.md).

```yaml
    exclude_declined: true
```

## Show As Exclude

To exclude events by how they show in the calendar, such as free time or out of office.

```yaml
    show_as_exclude:
     - free
     - oof
```

The values are those of MS365: `free`, `tentative`, `busy`, `oof` (out of office), `workingElsewhere` and `unknown`. The names shown in the `show_as` field of the event data, such as `WorkingElsewhere`, can be used too.

An entity with both settings:

```yaml
- cal_id: xxxx
  entities:
  - device_id: work_calendar
    end_offset: 24
    exclude_declined: true
    name: My Work Calendar
    show_as_exclude:
    - free
    start_offset: 0
    track: true
```

Like the other exclude settings, these leave the events out everywhere the entity is used: its state and `data` attribute, the calendar panel, `calendar.get_events` and `ms365_calendar.get_calendar_events`, also for dates outside the synchronized range.
