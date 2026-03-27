# Backup Service Redeploy Acceptance Checklist

Use this after updating the backup-service code or changing YouTube auth configuration on B.

## Goal

Confirm that:
1. B is running the new health payload
2. B advertises YouTube auth readiness accurately
3. delegated auth-gated YouTube transcription can actually succeed

## Phase 0 — Align code version
On both A and B, ensure the repo is on the intended validated commit.

Recommended:
- `git fetch origin`
- `git checkout <commit-sha>`

## Phase 1 — Restart / redeploy B
After updating code or env on B, restart the backup service.

Example (backup deployment model):
```bash
export BACKUP_SERVICE_TOKEN=...
export OPENAI_API_KEY=...
# and one of:
export YT_DLP_COOKIES_FILE=/path/to/cookies.txt
# or
export YT_DLP_COOKIES_FROM_BROWSER=chrome

docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d
```

## Phase 2 — Verify new health payload
From A (or any host that can reach B):

```bash
curl http://<B_HOST>:8000/delegate/health
```

Expected minimum fields:
- `healthy`
- `auth_configured`
- `openai_configured`
- `yt_auth_configured`
- `yt_auth_mode` (when configured)

### Pass conditions
- `healthy=true`
- `auth_configured=true`
- `openai_configured=true`
- `yt_auth_configured=true`
- `yt_auth_mode` is one of:
  - `cookie_file`
  - `cookie_browser`

### Fail conditions
- `yt_auth_configured=false`
- old payload is still returned (means B was not actually redeployed to new code)

## Phase 3 — Direct delegated smoke test to B
Use a known auth-gated YouTube URL.

```bash
curl -X POST http://<B_HOST>:8000/delegate/transcribe \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=<AUTH_GATED_VIDEO>",
    "originator": "acceptance-a",
    "delegation_reason": "post-redeploy smoke test",
    "skip_correction": true
  }'
```

### Pass conditions
- `status=success`
- `delegated=true`
- `result` present

### Fail interpretation
- `failure_category=auth_required`
  - B still lacks usable YouTube auth, or cookies are stale/unreadable
- `401`
  - token mismatch
- connection failure
  - B not reachable / redeploy failed

## Phase 4 — A-side end-to-end check
Trigger a real A-side job that is expected to fail locally and delegate to B.

Expected path:
1. A local acquisition fails
2. A enters delegate branch
3. B succeeds
4. A returns delegated transcript result to caller

## Operator notes
- `yt_auth_configured=true` is necessary but not sufficient; stale cookies can still fail.
- Keep one known auth-gated video URL for recurring smoke tests.
- Whenever B is rebuilt, browser profile changes, or cookies rotate, rerun this checklist.
- If B health is green but delegated jobs still fail with `auth_required`, treat it as a B-side YouTube auth problem, not a transport bug.
