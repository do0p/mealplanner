import logging
import mimetypes

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.adapters.extractor_registry import UnsupportedFormatError
from app.dependencies import get_import_service
from app.models import ImportJobRead, ImportJobSummary
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/llm-status")
def llm_status(svc: ImportService = Depends(get_import_service)):
    return svc.llm_status()


@router.get("/", response_model=list[ImportJobSummary])
def list_jobs(svc: ImportService = Depends(get_import_service)):
    return svc.list_jobs()


@router.post("/uploads", response_model=ImportJobSummary, status_code=201)
async def upload(
    file: UploadFile,
    svc: ImportService = Depends(get_import_service),
):
    data = await file.read()
    try:
        return svc.upload(data, file.filename or "upload")
    except UnsupportedFormatError as exc:
        raise HTTPException(
            415, f"Format '{exc.format}' is not yet supported"
        )


@router.post("/process", status_code=202)
def process_pending(
    background: BackgroundTasks,
    svc: ImportService = Depends(get_import_service),
):
    if not svc.llm_status()["available"]:
        raise HTTPException(503, "LLM server is not reachable")
    job_ids = svc.queue_pending()
    if not job_ids:
        return {"queued": 0, "message": "No pending jobs"}
    for jid in job_ids:
        background.add_task(svc.process_job, jid)
    return {"queued": len(job_ids), "job_ids": job_ids}


@router.get("/{job_id}/source")
def get_source(job_id: int, svc: ImportService = Depends(get_import_service)):
    result = svc.get_source_path(job_id)
    if result is None:
        raise HTTPException(404, "Import job not found")
    path, filename = result
    if not path.exists():
        raise HTTPException(404, "Source file not available")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(str(path), media_type=media_type, filename=filename)


@router.get("/{job_id}", response_model=ImportJobRead)
def get_job(job_id: int, svc: ImportService = Depends(get_import_service)):
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(404, "Import job not found")
    return job


@router.post("/{job_id}/retry", status_code=202)
def retry_job(
    job_id: int,
    background: BackgroundTasks,
    svc: ImportService = Depends(get_import_service),
):
    if not svc.llm_status()["available"]:
        raise HTTPException(503, "LLM server is not reachable")
    job = svc.retry_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found or not in failed state")
    job_ids = svc.queue_pending()
    for jid in job_ids:
        background.add_task(svc.process_job, jid)
    return {"queued": len(job_ids), "job_ids": job_ids}


@router.post("/{job_id}/abort", status_code=202)
def abort_job(job_id: int, svc: ImportService = Depends(get_import_service)):
    if not svc.abort_job(job_id):
        raise HTTPException(404, "Job not found or not currently processing")
    return {"aborted": True}


@router.delete("/{job_id}", status_code=200)
def delete_job(job_id: int, svc: ImportService = Depends(get_import_service)):
    result = svc.delete_job(job_id)
    if not result["deleted"]:
        raise HTTPException(404, "Import job not found")
    return result


