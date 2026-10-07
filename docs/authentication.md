---
title: Authentication
nav_order: 5
---

# Authentication

Authentication of the MS365 Integrations can be found on the MS365 Home Assistant [Authentication](https://rogerselwyn.github.io/MS365-HomeAssistant/authentication.html) page.

## Re-authentication

Microsoft can stop accepting the token, for example after it has not been used for a long time, after a password change or when access has been revoked. The client secret of the Entra ID App Registration also expires, at the end of the period chosen when it was created. When either happens, Home Assistant shows that the integration needs re-authentication, on the **Settings** page and under **Settings > Devices & services**:

* If it happens when the integration starts, the integration does not set up until you re-authenticate.
* If it happens while Home Assistant is running, the calendars keep showing the events synced before, with the `sync_state` attribute set to `problem`, until you re-authenticate.

To re-authenticate:

1. Select the re-authentication prompt and submit the first step.
1. Check the Client ID and Client Secret. If the client secret has expired, first create a new client secret in the App Registration and enter its value.
1. Follow the link to authorize, as when you set up the integration.

The integration then reloads with the new token. Reconfiguring the integration and re-authenticating there works as well.

Other token problems, such as a missing, corrupted or outdated token file, or a token without the permissions the integration needs, are still shown as a repair issue that asks you to reconfigure the integration.
