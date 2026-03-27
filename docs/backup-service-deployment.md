# Backup Service Deployment & Acceptance

This document explains how to deploy and validate the A/B backup-service delegation flow for `youtube-transcripter`.

## Overview

### A host (primary)
Responsibilities:
- try local YouTube acquisition/transcription first
- if local acquisition fails and fallback policy says delegate, call B over internal HTTP
- consume B's final result and relay it to the caller

### B host (backup)
Responsibilities:
- expose internal backup endpoints
- validate bearer token
- run the full `youtube-transcripter` pipeline locally
- return final delegated result

## Required endpoints on B
- `GET /delegate/health`
- `POST /delegate/transcribe`

## Recommended deployment model
- Keep A and B on the same internal network
- Use the same repo version/commit on both hosts
- Use a shared bearer token
- Do not expose the backup endpoint publicly in the first version

## Environment variables

### A host
Required:
- `BACKUP_SERVICE_URL=http://<B_HOST>:8000`
- `BACKUP_SERVICE_TOKEN=<shared-secret>`
- `OPENAI_API_KEY=...`

Optional / existing extraction envs:
- `YT_DLP_COOKIES_FILE=...`
- `YT_DLP_COOKIES_FROM_BROWSER=...`
- `YT_DLP_BROWSER_PROFILE=...`
- `YT_DLP_BROWSER_CONTAINER=...`

### B host
Required:
- `BACKUP_SERVICE_TOKEN=<shared-secret>`
- `OPENAI_API_KEY=...`

Injected automatically by `docker-compose.backup.yml`:
- `SERVICE_ROLE=backup`

Optional / recommended if B is expected to succeed where A fails:
- `YT_DLP_COOKIES_FILE=/path/to/cookies.txt`
- or `YT_DLP_COOKIES_FROM_BROWSER=chrome`

## Deployment steps

### 1. Align repo version
Use the same commit on both hosts.

Recommended practice:
- push validated commits to remote first
- on both A and B:
  - `git fetch origin`
  - `git checkout <commit-sha>`

### 2. Start B service
Use the backup compose overlay to start only the backend with backup-specific settings.
The overlay publishes the backend on host port 8000, injects `SERVICE_ROLE=backup` and `BACKUP_SERVICE_TOKEN`, and disables the frontend service.

```bash
# on B — set required env vars
export BACKUP_SERVICE_TOKEN=...
export OPENAI_API_KEY=...
# plus any YouTube auth env you want B to use

# start backup deployment
docker compose -f docker-compose.yml -f docker-compose.backup.yml up -d
```

> **Note:** The frontend service is automatically excluded in backup mode via a compose profile.
> To start the default (primary) deployment with frontend, use `docker compose up -d` as usual.

### 3. Configure A
```bash
# on A
export BACKUP_SERVICE_URL=http://<B_HOST>:8000
export BACKUP_SERVICE_TOKEN=...
export OPENAI_API_KEY=...
```

## Acceptance sequence

### Phase 0 — Health check
From A, verify B is reachable:

```bash
curl http://<B_HOST>:8000/delegate/health
```

Expected response includes:
- `healthy`
- `auth_configured`
- `openai_configured`
- `yt_auth_configured`
- `yt_auth_mode` (when configured)

> Important: `yt_auth_configured=true` means the backup host has some YouTube auth mode configured, not that the cookies are guaranteed fresh. A green health response can still coexist with delegated failures of category `auth_required` if the configured cookies are stale or unreadable.

### Phase 1 — Direct delegated request to B
Manually POST a delegated request to B:

```bash
curl -X POST http://<B_HOST>:8000/delegate/transcribe \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=<VIDEO_ID>",
    "language": "en",
    "skip_correction": true,
    "originator": "acceptance-a",
    "delegation_reason": "manual acceptance test"
  }'
```

Expected:
- success → `status=success`, `delegated=true`, `result` present
- failure → `status=failed`, classified `failure_category`, `error_message`

### Phase 2 — A-side client test
On A, verify the backup client can call B successfully using the configured URL and token.

### Phase 3 — Local-fail → remote-success
Create a scenario where:
- A fails locally (e.g. no valid YouTube cookies / blocked path)
- B is configured to succeed
- B has usable YouTube auth configured (`YT_DLP_COOKIES_FILE` or `YT_DLP_COOKIES_FROM_BROWSER`) when the test video is auth-gated

Expected:
1. A attempts local acquisition
2. H3 policy chooses delegation
3. A calls B
4. B returns final result
5. A returns that delegated result instead of a raw local acquisition failure

## Pass/fail checklist

### PASS
- [ ] B `/delegate/health` is reachable from A
- [ ] B `/delegate/transcribe` works directly
- [ ] A backup client can call B successfully
- [ ] Local-fail → remote-success works end-to-end
- [ ] Final transcript result is returned to the caller

### FAIL
- [ ] A cannot reach B
- [ ] bearer token mismatch
- [ ] B itself cannot extract YouTube
- [ ] B health is green but delegated auth-gated videos still fail with `auth_required`
- [ ] A never enters delegate branch
- [ ] delegated response cannot be parsed/consumed

## Operational notes
- Use the same validated commit on both A and B for acceptance.
- Prefer `skip_correction=true` for the first acceptance run to reduce variables/cost.
- If B is also blocked by YouTube, the issue is now environmental on both hosts, not an A-side fallback bug.
- Keep `docs/acquisition-runbook.md` as the reasoning/diagnostics companion to this deployment guide.
