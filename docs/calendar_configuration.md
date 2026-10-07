---
title: Calendar Configuration
nav_order: 6
---

# Calendar configuration
The integration uses an external `ms365_calendars_<entity_name>.yaml` file which is stored in the `ms365_storage` directory. Much of this can be managed by the UI, but more complex items must be managed via the yaml file. Items that can be set in the integration's options (**Configure**) are:
* name
* track
* end_offset
* start_offset
* max_results
* search, exclude, sensitivity_exclude, exclude_declined and show_as_exclude, in the **Filters** section of each calendar, see [Filters in the options](#filters-in-the-options)

Group calendars and device_id must be managed via the yaml file.

The integration reads the calendars of the account when it starts or is reloaded. A calendar that is not in the file yet is added at the end, with `name` and `device_id` set to the calendar's name, `start_offset: 0`, `end_offset: 24` and `track` set by the `track_new_calendar` option (Enable new calendars). A calendar that has been removed from MS365 is removed from the file and its entity is deleted. Group calendars are never removed. Only the first 50 calendars of the account are read. Calendars past those are not added, but you can add them to the file by hand with their `cal_id` and an `entities` entry. When 50 calendars come back, none are removed from the file. Changes to the file are read when the integration is reloaded or Home Assistant restarts. When a calendar is removed from the file this way, or the options are saved, the file is written again, so comments in it are lost. Removing the integration deletes the file.

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
`start_offset` | `integer` | `False` | Start of the period of the `data` attribute, in hours from now (negative numbers to offset into the past). Default is 0
`end_offset` | `integer` | `False` | End of the period of the `data` attribute, in hours from now (negative numbers to offset into the past). Default is 24
`max_results` | `integer` | `False` | Max number of events in the `data` attribute. Default is no limit.
`sensitivity_exclude` | `list[string]` | `False` | List of sensitivities to exclude from the calendar (`normal`/`personal`/`private`/`confidential`)
`exclude_declined` | `boolean` | `False` | True=Exclude the events the calendar's owner has declined (on your own calendars, the events you have declined). Default is false
`show_as_exclude` | `list[string]` | `False` | List of show as values to exclude from the calendar (`free`/`tentative`/`busy`/`oof`/`workingElsewhere`/`unknown`)

If the settings of a calendar in the file are not valid, for example `sensitivity_exclude: Private` (write the sensitivity values in lower case as listed; unlike `show_as_exclude`, the names shown in the event data are not accepted), a `show_as_exclude` value MS365 does not have, or `exclude` given as a single string instead of a list, the warning `Invalid Data - duplicate entries may be created in file` is logged. It names the calendar by its `cal_id` and the names of its entities, and says what is not valid and where, for example `expected EventShowAs or one of 'free', 'tentative', 'busy', 'oof', 'working_elsewhere', 'unknown' at 'entities[0].show_as_exclude[1]'` for the second `show_as_exclude` value of the first entity. The whole calendar entry, with all its entities, is then skipped and no entity is created from it. If it is a calendar the integration finds in your account, a new entry for it is added at the end of the file when the integration starts or is reloaded. That entry has the calendar's MS365 name as `name` and `device_id`, the default offsets, none of your other settings, and `track` set by the Enable new calendars option. The entity is then set up from that new entry, so it can have a different entity_id from the one you configured, or no entity at all if Enable new calendars is off. To fix it, correct your entry and delete the added one: while both are in the file, the last one is used.

## Filters in the options

The filters of each calendar can also be set in the integration's options. Select **Configure**, then open the **Filters** section on the form of the calendar. It is filled in from the calendar's entry in the file:

Field | Setting
-- | --
Only events with this text in the subject | `search`
Exclude events whose subject matches | `exclude`, one regular expression per entry
Exclude events with sensitivity | `sensitivity_exclude`
Exclude declined events | `exclude_declined`
Exclude events shown as | `show_as_exclude`

Saving the options writes the filters into the calendar's entry and reloads the integration, so they apply straight away, also when nothing else was changed. A filter that is cleared, or set to its default (no text, no entries, nothing selected, or Exclude declined events off), is removed from the entry, so the calendar works as if it had never been set. The other settings in the file are kept. `show_as_exclude` is written as MS365 names the values, such as `workingElsewhere`.

Each exclude must be a valid regular expression. If one is not, the form is shown again with an error that names it, and nothing is saved until it is corrected. Empty entries are removed.

A value the file does not accept, such as `sensitivity_exclude: Private` or a `show_as_exclude` value MS365 does not have, is not shown in the form, so it is removed from the file when the form of that calendar is saved. A single `exclude` given as text instead of a list is shown as one entry, and saved as a list.

## Group calendars

The integration supports Group calendars in a fairly simple form. The below are the constraints.
* The integration's `groups` option ("Enable support for group calendars") must be on, so that the `Group.Read.All` permission (`Group.ReadWrite.All` with `enable_update`) is requested, see [Installation and Configuration](./installation_and_configuration.md) and [Permissions](./permissions.md). It cannot be used with `shared_mailbox`.
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

Each item is used as a regex, so characters such as `[ ] ( ) . * + ?` have their regex meaning; to match them as text, escape them with `\` inside single quotes, e.g. `'\[External\]'`. An item that is not a valid regex, such as `"(Optional"`, is matched as plain text and a warning is logged. The options do not save such an item, see [Filters in the options](#filters-in-the-options).

Matching is case sensitive. To ignore case, start the item with `(?i)`, e.g. `'(?i)^private'`. It must be at the very start: placed later, as in `'^(?i)private'`, the item is not a valid regex and is matched as plain text.

## Sensitivity Exclude

To exclude specific sensitivities from being included in the calendar.

```yaml
    sensitivity_exclude:
     - private
     - confidential
```

## Exclude Declined

Events you have declined can stay on your calendar. To exclude them, set `exclude_declined` to `true`. This uses the response of the calendar's owner, which is shown in the `response` field of each event, see [Sensors](./sensor.md). On your own calendars that is your own response. On a calendar someone else has shared with you, or with `shared_mailbox`, it hides the events that person has declined, not the ones you have declined. On a group calendar the response is the group's, usually `organizer`, so it hides nothing there.

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
