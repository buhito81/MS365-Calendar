---
title: Errors
nav_order: 19
---

# Errors

Guidance on logged errors for the MS365 Integrations can be found on the MS365 Home Assistant [Errors](https://rogerselwyn.github.io/MS365-HomeAssistant/errors.html) page.

The warnings `Token has expired for account`, `Client Secret expired for account` and `Token error for account` mean Microsoft no longer accepts the token or the client secret. Home Assistant then asks you to re-authenticate the integration, see [Re-authentication](./authentication.md#re-authentication).
