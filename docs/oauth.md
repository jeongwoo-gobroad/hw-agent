# SmartThings OAuth with ngrok

[English](oauth.md) · [한국어](oauth.ko.md)

Each installation needs its own Samsung account, eligible SmartThings API Access App, and ngrok account. Alter does not provide a shared OAuth client or access to another installation.

## Before you start

As of November 4, 2026, creating/editing OAuth apps requires an eligible paid SmartThings API plan; availability depends on country. Existing installations have a separate transition timeline. Check [Samsung's current policy](https://blog.smartthings.com/smartthings-updates/smartthings-api-additional-details-for-developers-and-business-partners/) before registering. The ngrok free plan does not pay for SmartThings API access.

## Connect

1. In your ngrok dashboard, find your assigned development domain and actual Authtoken (not its credential ID). Keep the token private.
2. Install the [official SmartThings CLI](https://github.com/SmartThingsCommunity/smartthings-cli), sign in, and follow the [official API Access App quickstart](https://developer.smartthings.com/docs/getting-started/quickstart). The current quickstart uses `smartthings smartapps:create`; older CLI versions use `apps:create`. Follow your installed CLI's help rather than mixing versions.
3. Register the exact callback `https://<your-assigned-domain>/oauth/callback`. Use location/device read and device execute permissions (`r:locations:*`, `r:devices:*`, `x:devices:*`) needed by Alter. Save the issued client ID and client secret privately.
4. In `~/hw-agent`, run `.venv/bin/python scripts/configure.py --smartthings --lang en`. Enter your HTTPS origin, Authtoken and OAuth credentials. It updates `.env`, adds the allowed host and preserves existing session keys.
5. Run `bash scripts/install-ngrok.sh`, then `sudo systemctl restart alter alter-oauth`. The installer uses the official ngrok apt repository and creates a service forwarding to the public entry point on loopback port 8080. Request inspection is disabled.
6. Log in to Alter on the LAN, open **Smart home → Connect Samsung account**, pass ngrok's browser notice if shown, select your location/devices, and authorize. Return to Alter and refresh device status. Do not reuse an old authorization link.

`DASHBOARD_URL` controls the return link; a LAN URL can remain configured for local setup, or use your HTTPS origin for remote setup. The callback must match on both sides. If the domain changes, update the registered app, `.env` and `ALLOWED_HOSTS`, restart services, and start a fresh authorization.

## Security and operation

The login session creates a one-time ticket. OAuth state is bound to a Secure/HttpOnly/Lax cookie and that session. Tokens are encrypted in SQLite using a key derived from `SESSION_SECRET`. Refresh is serialized across processes; the new token pair is saved together. Device commands are not automatically replayed after authorization failure. Disconnect removes local credentials; revoke permissions separately in SmartThings if needed.

ngrok uses your account's stable development domain and supplies HTTPS. Its [free limits](https://ngrok.com/docs/pricing-limits/free-plan-limits) currently include 1 GB outbound/month and 20,000 HTTP requests/month, so sustained camera streaming can exhaust the allowance. DDNS can also work with a valid HTTPS reverse proxy and reachable ports; DDNS alone does not provide a certificate.

All file/camera/device APIs retain dashboard authentication. Public 8080 adds CAPTCHA and configurable login blocking. Only OAuth entry/callback routes bypass dashboard login, and they still require their ticket/state checks. A short-lived PAT can help testing, but Samsung specifies OAuth for long-term integrations.

For diagnosis, inspect service status and HTTP status codes without publishing `.env`, authorization URLs, cookies, tokens, account/location/device IDs or screenshots of private configuration. Automatic refresh cannot restore revoked permissions; reconnect through the browser.
