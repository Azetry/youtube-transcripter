# Backup HTTP delegation removed

The previous A→B feature (`BACKUP_SERVICE_URL`, `POST /delegate/transcribe`, `GET /delegate/health`, shared `BACKUP_SERVICE_TOKEN`) has been **removed** from this repository. Acquisition runs **only on the local host**; failures surface as structured fallback decisions (`MANUAL_FALLBACK`, `ABORT`, etc.) without automatic remote full-pipeline failover.

For background, see the OpenSpec change `openspec/changes/remove-delegate-backup-feature/`.
