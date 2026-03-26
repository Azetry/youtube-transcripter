"""Backup-service delegation endpoint (H7b).

Accepts delegated transcription requests from a primary service,
runs the full pipeline locally, and returns a DelegationResponse.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from src.integrations.backup_auth import validate_request_token
from src.integrations.backup_health import check_backup_health
from src.integrations.backup_service import (
    DelegationRequest,
    DelegationResponse,
    DelegationResult,
    DelegationStatus,
)
from src.models.acquisition import FailureCategory
from src.services.transcription_service import AcquisitionError, TranscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_host_id() -> str:
    """Return a short identifier for this backup host."""
    try:
        return socket.gethostname()
    except Exception:
        return "backup-unknown"


def _classify_error(exc: Exception) -> FailureCategory:
    """Map a pipeline exception to a FailureCategory."""
    if isinstance(exc, AcquisitionError):
        # If the acquisition error carries a fallback_decision with a
        # classified failure, propagate it.
        if exc.fallback_decision and exc.fallback_decision.failure_category:
            return exc.fallback_decision.failure_category
        return FailureCategory.UNKNOWN
    msg = str(exc).lower()
    if "rate" in msg or "429" in msg:
        return FailureCategory.RATE_LIMITED
    if "geo" in msg or "region" in msg:
        return FailureCategory.GEO_BLOCKED
    if "unavailable" in msg or "private" in msg or "deleted" in msg:
        return FailureCategory.UNAVAILABLE
    return FailureCategory.UNKNOWN


# ---- Endpoints -----------------------------------------------------------

@router.post("/delegate/transcribe")
async def delegate_transcribe(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Accept a delegated transcription request and run the full pipeline."""

    # 1. Auth check
    if not validate_request_token(authorization):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    # 2. Parse body into DelegationRequest
    try:
        body = await request.json()
        delegation_req = DelegationRequest.from_dict(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {exc}")

    host_id = _get_host_id()

    # 3. Run the pipeline
    svc = TranscriptionService()
    try:
        artifacts = await asyncio.to_thread(
            svc.run,
            url=delegation_req.url,
            language=delegation_req.language,
            skip_correction=delegation_req.skip_correction,
            custom_terms=list(delegation_req.custom_terms) or None,
            job_id=delegation_req.job_id,
        )
    except AcquisitionError as exc:
        logger.warning("Delegation acquisition failed: %s", exc)
        diag = None
        if exc.acquisition_result:
            diag = str(exc.acquisition_result.diagnostics())
        return DelegationResponse(
            status=DelegationStatus.FAILED,
            remote_host=host_id,
            error_message=str(exc),
            failure_category=_classify_error(exc),
            acquisition_diagnostics=diag,
        ).to_dict()
    except Exception as exc:
        logger.exception("Delegation pipeline error")
        return DelegationResponse(
            status=DelegationStatus.FAILED,
            remote_host=host_id,
            error_message=str(exc),
            failure_category=_classify_error(exc),
        ).to_dict()

    # 4. Build success response
    result = DelegationResult(
        video_id=artifacts.video_info.video_id,
        title=artifacts.video_info.title,
        channel=artifacts.video_info.channel,
        duration=artifacts.video_info.duration,
        original_text=artifacts.original_text,
        corrected_text=artifacts.corrected_text,
        language=artifacts.language,
    )
    return DelegationResponse(
        status=DelegationStatus.SUCCESS,
        remote_host=host_id,
        result=result,
    ).to_dict()


@router.get("/delegate/health")
async def delegate_health():
    """Health check for the backup delegation service."""
    status = check_backup_health()
    return status.to_dict()
