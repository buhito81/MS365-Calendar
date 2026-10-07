---
title: Installation and Configuration
nav_order: 4
---

# Installation and Configuration
This page details the configuration details for this integration. General instructions can be found on the MS365 Home Assistant [Installation and Configuration](https://rogerselwyn.github.io/MS365-HomeAssistant/installation_and_configuration.html) page.

### Configuration variables

Key | Type | Required | Description
-- | -- | -- | --
`entity_name` | `string` | `True` | Uniquely identifying name for the account. Calendar entity_ids will be prefixed with this, e.g. `calendar.account1_calendar`. Do not use email address or spaces.
`client_id` | `string` | `True` | Client ID from your Entra ID App Registration.
`client_secret` | `string` | `True` | Client Secret from your Entra ID App Registration.
`alt_auth_method` | `boolean` | `False` | If False (default), authentication is not dependent on internet access to your HA instance. [See Authentication](./authentication.md)
`enable_update` | `boolean` | `False` | If True (**default is False**), this will enable the various services that allow updates to calendars
`basic_calendar` | `boolean` | `False` | If True (**default is False**), the permission requested will be `Calendars.ReadBasic`. Cannot be used together with `enable_update` or `shared_mailbox`.
`groups` | `boolean` | `False` | If True (**default is False**), will enable support for group calendars. No discovery is performed. You will need to know how to get the group ID from the MS Graph API. *Not for use on shared mailboxes*
`shared_mailbox` | `string` | `False` | Email address or ID of shared mailbox (This should not be the same email address as the logged in user).

#### Advanced API Options

These options will only be relevant for users in very specific circumstances.

Key | Type | Required | Description
-- | -- | -- | --
`country` | `string` | `True` | Selection of an alternate country specific API. Currently only 21Vianet from China and MS365 GCC.
`tenant_id` | `string` | `False` | Azure tenant ID for single-tenant app registrations. Leave blank for multi-tenant apps.

### Options

Key | Type | Required | Description
-- | -- | -- | --
`calendar_list` | `list[string]` | `False` | The selectable list of calendars for which calendar entities will be created.
`track_new_calendar` | `boolean` | `False` | If True (default), will automatically generate a calendar_entity when a new calendar is detected. The system scans for new calendars only on startup or reconfiguration/reload. Only the first 50 calendars are read, so a calendar after those is not detected. During the same scan, a calendar that no longer exists in MS365 is removed from the list and its entities are deleted, unless 50 calendars were read. Group calendars are never removed this way.

### Advanced Options

Key | Type | Required | Description
-- | -- | -- | --
`update_interval` | `integer` | `False` | How often in seconds that events will be retrieved and synced to store. Default 60. Range: 15 - 600
`days_backward` | `integer` | `False` | The days backward from `now` for which events will be synced to store. Default -8. Range: -90 - 90
`days_forward` | `integer` | `False` | The days forward from `now` for which events will be synced to store. Default 8. Range: -90 - 90

### Calendar options

After these options, a form is shown for each enabled calendar, filled in from its entry in the [calendars file](./calendar_configuration.md). Saving the options writes the calendars file and reloads the integration, so the changes apply straight away, also when only the settings of a calendar were changed.

Key | Type | Required | Description
-- | -- | -- | --
`name` | `string` | `True` | The calendar friendly name.
`end_offset` | `integer` | `True` | End of the period of the `data` attribute, in hours from now. Default 24
`start_offset` | `integer` | `True` | Start of the period of the `data` attribute, in hours from now. Default 0
`max_results` | `integer` | `False` | Max number of events in the `data` attribute. Default is no limit.

#### Filters

The collapsed **Filters** section of each calendar's form. A filter that is cleared is removed from the calendars file. See [Filters in the options](./calendar_configuration.md#filters-in-the-options).

Key | Type | Required | Description
-- | -- | -- | --
`search` | `string` | `False` | Only get events whose subject contains this text.
`exclude` | `list[string]` | `False` | Exclude events whose subject matches one of these regular expressions. Each must be a valid regular expression, or the form shows an error naming it.
`sensitivity_exclude` | `list[string]` | `False` | Exclude events with one of these sensitivities (Normal, Personal, Private, Confidential).
`exclude_declined` | `boolean` | `False` | Exclude the events the calendar's owner has declined. Default false
`show_as_exclude` | `list[string]` | `False` | Exclude events that show as one of these (Free, Tentative, Busy, Away (out of office), Working elsewhere, Unknown).
