# Backup Service YouTube Auth Ops Guide

This guide covers the operational gap discovered during delegated fallback acceptance:

- A → B delegation can be healthy
- but B can still fail all delegated YouTube jobs if it has no YouTube auth credentials configured

## Key lesson

`GET /delegate/health` only proves that:
- the backup service is reachable
- backup bearer auth is configured
- OpenAI is configured

It does **not** prove that B can extract auth-gated YouTube videos.

## Minimum requirement for B

To handle `auth_required` delegation successfully, B should have at least one of:

- `YT_DLP_COOKIES_FILE=/path/to/cookies.txt`
- `YT_DLP_COOKIES_FROM_BROWSER=chrome`

Optional related envs if needed by your environment:
- `YT_DLP_BROWSER_PROFILE=<profile>`
- `YT_DLP_BROWSER_CONTAINER=<container>`

## Operator checklist

### On B host
1. Confirm backup service env includes:
   - `BACKUP_SERVICE_TOKEN`
   - `OPENAI_API_KEY`
   - one YouTube auth env (`YT_DLP_COOKIES_FILE` or `YT_DLP_COOKIES_FROM_BROWSER`)
2. If using cookie file:
   - verify the file exists
   - verify file permissions allow the service user to read it
   - refresh cookies when YouTube auth expires
3. If using cookies-from-browser:
   - verify the browser exists on B
   - verify the selected browser profile has a valid logged-in YouTube session
   - verify the service user can access that browser profile

### On A host
1. Confirm `.env` / runtime env includes:
   - `BACKUP_SERVICE_URL`
   - `BACKUP_SERVICE_TOKEN`
2. Do not assume health means extraction-ready.
3. For auth-gated videos, treat direct delegated transcription as the real readiness test.

## Readiness test sequence

### Step 1 — health
```bash
curl http://<B_HOST>:8000/delegate/health
```

Expected: `healthy=true`

### Step 2 — auth-gated delegated smoke test
Run one delegated transcription against a known auth-gated YouTube URL.

Expected outcomes:
- success → B has working YouTube auth
- `failure_category=auth_required` → B still lacks usable YouTube auth

## Common failure interpretation

### Case: health passes, delegated job fails with `auth_required`
This means:
- routing works
- token works
- B is alive
- but B does **not** currently have usable YouTube cookies/auth

This is an environment/config problem on B, not a delegation transport bug.

## Recommended ops policy

For acceptance and ongoing operation:
- keep one known auth-gated YouTube URL as a smoke test case
- rerun that test whenever cookies are rotated, browser profile changes, or B is rebuilt
- document cookie refresh ownership explicitly

## Health payload update

The backup-service health payload now includes:
- `yt_auth_configured`
- `yt_auth_mode`

Interpretation:
- `yt_auth_configured=false` → do not expect delegated auth-gated YouTube jobs to succeed
- `yt_auth_configured=true` → auth mode exists, but cookies may still be stale; direct delegated smoke test is still required

## Related checklist

After changing B config or redeploying the backup service, use:
- `docs/backup-service-redeploy-checklist.md`
