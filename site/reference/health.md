# Health

<MethodBadge method="GET" path="/health" />
<MethodBadge method="GET" path="/health/scheduler" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'None' },
]" />

Both unauthenticated so an uptime monitor needs no credentials. Useful if
you're self-hosting and want to monitor your own instance - not
something a consumer calling a hosted instance typically needs.

## `/health`

Liveness - is the process up.

```json
{ "status": "ok", "service": "matchday-gateway" }
```

## `/health/scheduler`

Is the data actually still being kept up to date. Returns `503` the
moment any background sync job's heartbeat has gone stale, `200`
otherwise.

```json
{
  "status": "healthy",
  "stale_jobs": [],
  "jobs": [
    {
      "job_id": "sync_fixtures",
      "last_run_at": "2026-09-23T18:24:46Z",
      "age_seconds": 187,
      "threshold_seconds": 1800,
      "stale": false
    }
  ]
}
```

The status code is what matters for alerting - point an uptime monitor at
this and alert on non-2xx, not on parsing `status` out of the body.
