# Acquisition Runbook

How youtube-transcripter acquires audio, what can go wrong, and what to do about it.

## Acquisition Modes

| Mode | Env Var | Description |
|------|---------|-------------|
| `unauthenticated` | *(none)* | Best-effort extraction, no cookies. Default first attempt. |
| `cookie_file` | `YT_DLP_COOKIES_FILE` | Netscape-format cookie file path. |
| `cookie_browser` | `YT_DLP_COOKIES_FROM_BROWSER` | Browser name (e.g. `chrome`) to extract cookies from. |
| `oauth` | *(future)* | OAuth token flow. Not yet implemented. |

## Strategy Order

On every acquisition request the service tries modes sequentially and stops on first success:

```
1. UNAUTHENTICATED   (always tried first by default)
2. auth mode         (cookie_file or cookie_browser, if configured)
```

Set `auth_first=True` in `ThisHostAcquisitionService` to reverse the order (useful when unauthenticated is known to fail for your IP).

If no auth env var is set, only `unauthenticated` is attempted.

## Fallback Decision Flow

When all this-host strategies fail, the fallback policy (`src/services/fallback_policy.py`) evaluates the classified failure and picks a route:

```
this-host strategies exhausted
        │
        ▼
  classify failure
        │
        ├─ AUTH_REQUIRED ──► auth available & untried? → ESCALATE_AUTH_THIS_HOST
        │                    auth tried or unavailable? → DELEGATE_ALTERNATE_HOST
        │
        ├─ TRANSIENT ──────► < 3 attempts? → RETRY_THIS_HOST
        │                    ≥ 3 attempts? → DELEGATE_ALTERNATE_HOST
        │
        ├─ RATE_LIMITED ───► < 2 attempts? → WAIT_RETRY_THIS_HOST (30s backoff)
        │                    ≥ 2 attempts? → DELEGATE_ALTERNATE_HOST
        │
        ├─ GEO_BLOCKED ───► DELEGATE_ALTERNATE_HOST (needs different IP)
        │
        ├─ UNAVAILABLE ────► ABORT (deleted/private/copyright — nothing helps)
        │
        ├─ FORMAT_ERROR ───► MANUAL_FALLBACK (adjust format/quality)
        │
        └─ UNKNOWN ────────► MANUAL_FALLBACK (operator review)
```

## Failure Categories — What They Mean and What to Do

| Category | Typical yt-dlp Error | Operator Action |
|----------|---------------------|-----------------|
| `auth_required` | "Sign in to confirm", "login required", "confirm your age", "use --cookies" | Set `YT_DLP_COOKIES_FILE` or `YT_DLP_COOKIES_FROM_BROWSER`. If auth already configured and still fails, the alternate host likely has fresher cookies. |
| `geo_blocked` | "not available in your country", "geo-restricted" | No local fix — requires acquisition from a host in an allowed region. |
| `unavailable` | "video unavailable", "has been removed", "private video", "copyright", HTTP 404 | Video is gone. No retry will help. Confirm the URL is correct. |
| `rate_limited` | HTTP 429, "too many requests", "rate-limit" | Wait and retry. If persistent, rotate IP or delegate to alternate host. Reduce request frequency. |
| `transient` | "connection reset", "timed out", HTTP 5xx, "page needs to be reloaded" | Usually self-resolving. Automatic retry handles most cases. If repeated, check network connectivity. |
| `format_error` | "format not available", "no suitable format" | Try different `--format` / `--quality` settings. Some videos lack certain codecs. |
| `unknown` | *(anything not matching above patterns)* | Check raw error in diagnostics output. May need a new classification pattern in `src/models/acquisition.py`. |

## Alternate-Host Delegation

When the fallback policy returns `DELEGATE_ALTERNATE_HOST`, the orchestrator builds an `AlternateHostRequest` (see `src/integrations/alternate_host.py`) containing:
- The YouTube URL
- Format/quality preferences
- A `FailureContext` summarising what was already tried

**Transport is not yet implemented.** The request object is attached to the `AcquisitionError` exception so the caller (CLI, API, or a future automation layer) can inspect and act on it.

To check if a failed transcription wanted to delegate:

```python
try:
    service.run(url)
except AcquisitionError as e:
    if e.alternate_host_request:
        print("Delegation requested:", e.alternate_host_request.to_json())
```

## Diagnostics

### CLI Quick Check

Use `acquire_only()` to test acquisition without running the full transcription pipeline:

```python
from src.services.transcription_service import TranscriptionService
svc = TranscriptionService()
outcome = svc.acquire_only("https://www.youtube.com/watch?v=VIDEO_ID")
print(outcome.diagnostics)
```

### Operator Summary

Use the diagnostics formatter for a human-readable summary:

```python
from src.services.acquisition_diagnostics import format_operator_summary
print(format_operator_summary(outcome))
```

This prints a structured text block showing: result status, each attempt with its mode/outcome/classification, the fallback decision and reason, and the recommended next step.

## Environment Variables Reference

| Variable | Purpose |
|----------|---------|
| `YT_DLP_COOKIES_FILE` | Path to Netscape-format cookies file for authenticated extraction |
| `YT_DLP_COOKIES_FROM_BROWSER` | Browser name to extract cookies from (e.g. `chrome`, `firefox`) |

## Key Source Files

| File | Responsibility |
|------|---------------|
| `src/models/acquisition.py` | Enums, failure patterns, classification |
| `src/services/acquisition_service.py` | This-host strategy execution |
| `src/services/fallback_policy.py` | Failure → route decision engine |
| `src/integrations/alternate_host.py` | Remote handoff request/response contract |
| `src/services/transcription_service.py` | Pipeline orchestration (wires H2-H4) |
| `src/services/acquisition_diagnostics.py` | Operator-facing summary formatter |
