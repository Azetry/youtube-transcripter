## 1. Orchestration and policy

- [x] 1.1 Remove `_try_delegate`, `_build_delegated_artifacts`, and `AcquisitionOutcome.delegated` / `delegation_response` from `TranscriptionService` (and any callers).
- [x] 1.2 Update `fallback_policy` so routing never selects remote full-pipeline delegation; remove `DELEGATE_ALTERNATE_HOST` from the decision table **or** map failures to `MANUAL_FALLBACK` / `ABORT` with clear operator reasons.
- [x] 1.3 Remove `build_request_from_decision` / `AlternateHostRequest` from `_acquire` if no longer needed for diagnostics.

## 2. HTTP API and integrations

- [x] 2.1 Remove `api/delegation.py` router and unregister from `api/main.py`.
- [x] 2.2 Delete `backup_client.py`, `backup_service.py`, `backup_auth.py` if nothing else imports them; otherwise split shared types.
- [x] 2.3 Resolve `backup_health.py`: delete or repoint to general health only.

## 3. Configuration and deployment

- [x] 3.1 Update `.env.example`: remove `BACKUP_SERVICE_URL`, `BACKUP_SERVICE_TOKEN`, and `SERVICE_ROLE` backup-only notes unless still used elsewhere.
- [x] 3.2 Remove or replace `docker-compose.backup.yml`; document in README.

## 4. Documentation

- [x] 4.1 Update `README.md` / `README.zh.md`: env table, endpoints table, backup deployment section.
- [x] 4.2 Archive or delete `docs/backup-service-*.md`; add a short note if URLs are linked externally.

## 5. Tests

- [x] 5.1 Remove or rewrite `test_delegation_flow.py`, `test_delegation_endpoint.py`, `test_backup_client.py`, `test_backup_*` as applicable.
- [x] 5.2 Run full `pytest` and fix acquisition/fallback tests.

## 6. Validation

- [x] 6.1 Run `openspec validate --changes` for this change after spec files are final.
