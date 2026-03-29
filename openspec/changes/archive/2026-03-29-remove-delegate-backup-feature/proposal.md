## Why

The HTTP backup-service delegation path (primary → `BACKUP_SERVICE_URL` → full pipeline on B) adds significant surface area: client, auth, API routes, tests, and ops docs. The project no longer wants to maintain this feature; acquisition should remain structured on **this host only**, with clear operator-visible failure—without automatic remote full-pipeline failover.

## What Changes

- Remove A-side delegation: `TranscriptionService` no longer calls `delegate_transcription` or builds delegated `TranscriptArtifacts` from `DelegationResponse`.
- Remove B-side HTTP API: `POST /delegate/transcribe`, `GET /delegate/health` (or replace health with a minimal non-delegation health if needed).
- Delete or inline-remove modules tied only to delegation: `backup_client`, `backup_service` contract models (if unused elsewhere), `backup_auth` (if only used by delegate router), and adjust `backup_health` if it only served `/delegate/health`.
- Update **fallback policy** so `FallbackRoute.DELEGATE_ALTERNATE_HOST` is never chosen, or is removed in favor of explicit routes (`MANUAL_FALLBACK`, `ABORT`, etc.) with updated reasons.
- Remove **H4 handoff** construction for remote backup when it only existed to support delegation—revisit `AlternateHostRequest` / `build_request_from_decision` usage in orchestration (keep or trim per design).
- Clean **env**, **README**, **`.env.example`**, **docker-compose.backup.yml** (delete or deprecate), and **docs** under `docs/backup-service-*.md` (archive, delete, or replace with a short “removed” note).
- Remove or rewrite tests: `test_delegation_*`, `test_backup_client`, affected acquisition orchestration tests.

## Capabilities

### Modified Capabilities
- `job-orchestration`: Orchestration SHALL NOT perform remote full-pipeline delegation to a backup service.

### Removed Capabilities (implicit)
- HTTP backup transcription delegation between services (H7-style `DelegationRequest` / `DelegationResponse` over the wire).

## Impact

- **Breaking** for any deployment that relied on A→B automatic failover via `BACKUP_SERVICE_URL`.
- **Simpler** codebase and fewer env vars for operators who only run single-host or CLI.
- May require reconciling older OpenSpec text (e.g. `harden-youtube-acquisition`) that assumed alternate-host priority—this change is explicitly **narrower** (remove delegate only, not necessarily all acquisition modes).
