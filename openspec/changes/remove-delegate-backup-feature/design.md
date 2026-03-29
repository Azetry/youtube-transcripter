## Goals

- Fully remove the **delegate feature**: no runtime path, no public API, no unused modules left behind.
- Keep **this-host acquisition** (H2), **failure classification** (H1), and **fallback policy** (H3) in a coherent state after removal.

## Non-goals

- Rewriting the entire acquisition story or implementing a new transport for H4 alternate-host acquisition-only (out of scope unless explicitly follow-up).
- Changing Whisper/GPT/speaker pipelines beyond what is needed to delete delegation parameters from `TranscriptionService.run` call sites.

## Current touchpoints (inventory)

| Area | Role today |
|------|------------|
| `src/services/transcription_service.py` | `_try_delegate`, `delegated` outcome, `_build_delegated_artifacts` |
| `src/integrations/backup_client.py` | HTTP client to `/delegate/transcribe` |
| `src/integrations/backup_service.py` | `DelegationRequest` / `DelegationResponse` models |
| `src/integrations/backup_auth.py` | Bearer validation for delegate router |
| `src/integrations/backup_health.py` | Health payload; used by `/delegate/health` |
| `api/delegation.py` | FastAPI router for delegate endpoints |
| `api/main.py` | `include_router(delegation_router)` |
| `src/services/fallback_policy.py` | May emit `DELEGATE_ALTERNATE_HOST` |
| `src/integrations/alternate_host.py` | `AlternateHostRequest` built in orchestration for audit |
| `docker-compose.backup.yml` | B-only deployment overlay |
| Docs | `docs/backup-service-*.md`, README env tables |

## Target architecture (after)

- Acquisition failure ends with a **local terminal outcome**: `AcquisitionError` with `FallbackDecision` / diagnostics, **without** attempting remote HTTP pipeline.
- **Optional**: retain `AlternateHostRequest` in diagnostics only if still useful for manual ops; otherwise remove `build_request_from_decision` wiring from `_acquire` to reduce dead code.

## Open questions (resolve during implementation)

1. Should **`GET /api/health`** merge any useful fields from `check_backup_health` (e.g. `yt_auth_configured`) for single-host ops, or keep health minimal?
2. Delete **`docker-compose.backup.yml`** entirely vs. leave a stub file pointing to this OpenSpec change?

## Risks

- Missed import or router registration causes startup failure — run full test suite and a manual API smoke test.
- External operators still documented in old blog/wiki — README should state removal clearly.
