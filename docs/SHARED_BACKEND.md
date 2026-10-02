# Shared backend services

The database-service foundation, Barras Armadas, and Maciel Romo share these modules:

- `src/security/sessions.py`: explicit signed-cookie renewal and expiry metadata.
- `src/services/system/emailing.py`: Brevo transactional email transport and access-email templates.
- `src/security/outbound_http.py`: bounded GET/POST JSON requests with destination validation, DNS pinning, verified TLS, and redirect rejection.
- `src/services/system/monitoring.py`: versioned metrics and structured HTTP operation/failure logging.

Keep changes and regression tests synchronized across the three repositories. Redis implementations, domain permissions, migrations, notification audiences, and business workflows remain application-owned. Shared session renewal calls the app's existing cache invalidation boundary; it does not replace that app's Redis service.

## Sessions

`GET /me` returns identity and the JWT's `session_expires_at` and `session_lifetime_seconds`. `POST /me/refresh` requires a currently valid, authorized session, reissues the signed cookie, and returns its new expiry. Missing, expired, revoked, or invalid sessions return 401. Authentication retains the app's existing IP protection, rate limits, and role checks. Barras Armadas permits inactive memberships to recover their account through these endpoints while keeping member-only operations protected.

New cookies have a random stable `sid` and a unique `jti`. Database rows and rate-limit keys use the full hash of `sid`; renewal keeps that identity, and logout revokes it. Valid older token-hash cookies are upgraded and their old rows revoked. Ordinary requests do not extend the database deadline without reissuing the JWT. Database service and Barras Armadas use `JWT_EXP_MINUTES`; Maciel Romo retains `COOKIE_EXPIRATION_DAYS` for its employee sessions. Frontend callers may renew before expiry using these endpoints; frontend polling is application-owned.

## Brevo

Configure each deployment independently in its environment:

```dotenv
BREVO_API_KEY=''
BREVO_FROM_EMAIL=''
BREVO_FROM_NAME='Your application name'
BREVO_REQUEST_TIMEOUT_SECONDS='10'
PUBLIC_APP_URL='https://your-application.example'
```

The sender must be verified in Brevo. Missing credentials fail when delivery is requested, rather than preventing applications without email from starting. No credentials are stored in source or shared between deployments.

`send_email` accepts recipient, subject, HTML, optional plain text, attachments and tags, and returns Brevo's accepted `messageId`. Acceptance does not establish inbox delivery. Account verification and password-reset helpers preserve caller-supplied one-time paths; the application continues to own token creation, expiry, and consumption. Sender branding comes from `BREVO_FROM_NAME`, and template fields are HTML-escaped. Adding this transport does not send panel notifications through email automatically or add account-reset routes to applications that do not already have them.

Email delivery runs off the event loop. Provider errors expose a status or generic transport error, never response bodies, recipient details, contents, or keys. POST delivery is not retried automatically because an ambiguous timeout can follow provider acceptance.

## HTTP protections

`get_json` and `post_json` validate public HTTPS destinations by default. All DNS answers must be public; the connection uses the validated IP while preserving the original HTTP Host and TLS hostname for certificate validation. Redirects are rejected before reading their bodies, and credentials are never forwarded to a redirected host. URLs with credentials, fragments, control characters, or invalid ports are rejected. Response bodies are capped at 2 MiB and request bodies at 8 MiB by default. Connect/read timeouts and size limits must be positive. Private destinations and plain HTTP require explicit opt-in from trusted application code; do not expose these flags to clients.

Brevo always uses its fixed HTTPS endpoint. Existing application-specific integrations retain their own behavior; the helpers are available when adding or adapting an integration. Redis configuration and implementation are not synchronized by this change.

## Verification

The shared tests mock provider transport, database sessions, and cache invalidation. They do not send mail, read production credentials, or connect to a live PostgreSQL/Redis instance.

```bash
python -m unittest tools.tests.test_shared_sessions tools.tests.test_shared_emailing tools.tests.test_shared_outbound_http tools.tests.test_monitoring_contract tools.tests.test_session_routes
```
