# Monitoring contract

Every backend exposes the same detailed monitoring payload at:

```http
GET /monitoring/metrics
Authorization: Bearer <view-or-higher API key>
Accept: application/json
```

`/health` remains the unauthenticated aggregate health endpoint. The detailed
endpoint requires a registered API key with permission level `VIEW` (`0`) or
higher and is subject to the key's normal Redis-backed rate limit.

The response is versioned so a central dashboard can reject incompatible
backends safely:

```json
{
  "schema_version": 1,
  "generated_at": "2026-09-10T18:00:00+00:00",
  "metrics": {
    "api_total_requests": 120,
    "api_total_exceptions": 1,
    "api_avg_response_time": 0.024
  },
  "recent": {
    "api": [],
    "database": [],
    "redis": []
  }
}
```

Recent API, database and Redis samples include `recorded_at` as an ISO-8601 UTC
timestamp. API samples also preserve the actual HTTP method observed on the
request.

## Central collector guidance

- Create a dedicated `VIEW` API key for monitoring; do not reuse an admin key.
- Send credentials only from a trusted server. Never expose them to browser code.
- Do not follow redirects when sending the Authorization header.
- Treat timeouts, non-200 statuses and schema mismatches as missing responses.
- Poll no more frequently than the API key's configured rate limit permits.

In Maciel Romo, the Web Development monitor follows this contract every 15
seconds. Its target URL and API key are encrypted at rest with PostgreSQL
`pgcrypto`, configured and viewable only by the `ceo` role, and used only by the
server-side proxy.
