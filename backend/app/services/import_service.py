"""Import pipeline orchestration.

Upload is LLM-free: stores the file and creates a pending ImportJob.
Processing (LLM-dependent) is triggered separately and runs in a background
thread so the app stays responsive. The service manages its own DB sessions so
background tasks work correctly after the HTTP request session has closed.
"""
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.adapters.extractor_registry import ExtractorRegistry, UnsupportedFormatError
from app.adapters.format_detection import detect_format
from app.config import settings
from app.models import (
    RECIPE_ACCEPTED,
    RECIPE_DRAFT,
    ImportJob,
    ImportJobRead,
    ImportJobSummary,
    Ingredient,
    InstructionStep,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_PROCESSING,
    Recipe,
    RecipeSummary,
)
from app.ports.recipe_extractor import ExtractedRecipe, RecipeExtractor
from app.services import units

logger = logging.getLogger(__name__)

# Job IDs for which the user has requested cancellation.
# Module-level so it's shared across all ImportService instances within the process.
_ABORT_REQUESTED: set[int] = set()


class _AbortRequested(Exception):
    pass


class ImportService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        text_registry: ExtractorRegistry,
        recipe_extractor: RecipeExtractor,
    ) -> None:
        self._sf = session_factory
        self._registry = text_registry
        self._extractor = recipe_extractor

    # ------------------------------------------------------------------
    # LLM health probe (live, not cached)
    # ------------------------------------------------------------------
    def llm_status(self) -> dict:
        available = self._extractor.is_available()
        if settings.llm_provider == "anthropic":
            return {
                "available": available,
                "provider": "anthropic",
                "model": settings.anthropic_model,
                "base_url": "https://api.anthropic.com",
            }
        return {
            "available": available,
            "provider": "ollama",
            "model": settings.ollama_model,
            "base_url": settings.ollama_base_url,
        }

    # ------------------------------------------------------------------
    # Upload (LLM-free)
    # ------------------------------------------------------------------
    def upload(self, file_bytes: bytes, filename: str) -> ImportJobSummary:
        fmt = detect_format(file_bytes, filename)
        if not self._registry.has(fmt):
            raise UnsupportedFormatError(fmt)

        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{filename}"
        (settings.uploads_dir / stored_name).write_bytes(file_bytes)

        with self._sf() as session:
            job = ImportJob(filename=filename, stored_file=stored_name, source_format=fmt)
            session.add(job)
            session.commit()
            session.refresh(job)
            return _job_summary(job)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------
    def list_jobs(self) -> list[ImportJobSummary]:
        with self._sf() as session:
            jobs = session.exec(select(ImportJob).order_by(ImportJob.created_at.desc())).all()
            return [_job_summary(j) for j in jobs]

    def get_job(self, job_id: int) -> ImportJobRead | None:
        with self._sf() as session:
            job = session.get(ImportJob, job_id)
            if job is None:
                return None
            recipes = session.exec(
                select(Recipe).where(Recipe.import_job_id == job_id)
            ).all()
            recipe_summaries = [
                RecipeSummary(
                    id=r.id,
                    title=r.title,
                    base_servings=r.base_servings,
                    course=r.course,
                    calories_per_person=r.calories_per_person,
                    protein_per_person=r.protein_per_person,
                    verification_status=r.verification_status,
                    status=r.status,
                    created_at=r.created_at,
                )
                for r in recipes
            ]
            return ImportJobRead(
                id=job.id,
                filename=job.filename,
                source_format=job.source_format,
                status=job.status,
                error=job.error,
                recipe_count=job.recipe_count,
                progress_current=job.progress_current,
                progress_total=job.progress_total,
                phase=job.phase,
                created_at=job.created_at,
                processed_at=job.processed_at,
                recipes=recipe_summaries,
            )

    # ------------------------------------------------------------------
    # Trigger processing of pending jobs
    # Returns list of job IDs that were queued.
    # ------------------------------------------------------------------
    def queue_pending(self) -> list[int]:
        """Mark all pending jobs as processing; return their IDs.
        Call process_job(id) for each in a background thread."""
        with self._sf() as session:
            pending = session.exec(
                select(ImportJob).where(ImportJob.status == JOB_PENDING)
            ).all()
            ids = []
            for job in pending:
                job.status = JOB_PROCESSING
                session.add(job)
                ids.append(job.id)
            session.commit()
            return ids

    # ------------------------------------------------------------------
    # Process one job (runs in background thread)
    # ------------------------------------------------------------------
    def process_job(self, job_id: int) -> None:
        logger.info("Processing import job %d", job_id)
        with self._sf() as session:
            job = session.get(ImportJob, job_id)
            if job is None:
                return

            try:
                file_path = settings.uploads_dir / job.stored_file
                data = file_path.read_bytes()
                text_extractor = self._registry.get(job.source_format)
                segments = text_extractor.extract(data)

                def _on_progress(phase: str, current: int, total: int) -> None:
                    if job_id in _ABORT_REQUESTED:
                        raise _AbortRequested()
                    logger.info("Job %d progress: %s %d/%d", job_id, phase, current, total)
                    job.phase = phase
                    job.progress_current = current
                    job.progress_total = total
                    session.add(job)
                    session.commit()

                extracted = self._extractor.extract_recipes(
                    segments, on_progress=_on_progress
                )
                saved = [self._save_recipe(session, job.id, r) for r in extracted]
                job.recipe_count = len(saved)
                job.status = JOB_COMPLETED
                job.phase = None
                job.processed_at = datetime.now(timezone.utc)
            except _AbortRequested:
                _ABORT_REQUESTED.discard(job_id)
                logger.info("Job %d aborted by user — resetting to pending", job_id)
                job.status = JOB_PENDING
                job.phase = None
                job.error = None
                job.progress_current = 0
                job.progress_total = 0
                job.processed_at = None
            except Exception as exc:
                logger.exception("Job %d failed", job_id)
                job.status = JOB_FAILED
                job.phase = None
                job.error = str(exc)
                job.processed_at = datetime.now(timezone.utc)

            session.add(job)
            session.commit()

    def _save_recipe(
        self, session: Session, job_id: int, ext: ExtractedRecipe
    ) -> Recipe:
        servings = ext.base_servings or 1
        recipe = Recipe(
            title=ext.title,
            base_servings=ext.base_servings,
            notes=ext.notes,
            course=ext.course,
            calories_per_person=round(ext.calories_total / servings, 1) if ext.calories_total else None,
            protein_per_person=round(ext.protein_total / servings, 1) if ext.protein_total else None,
            source_pages=ext.source_pages,
            raw_source_text=ext.raw_source_text,
            verification_status=ext.verification_status,
            verification_notes=ext.verification_notes,
            import_job_id=job_id,
            status=RECIPE_DRAFT,
        )
        session.add(recipe)
        session.flush()  # get recipe.id

        for idx, ing in enumerate(ext.ingredients):
            # Normalize: LLM returned book quantity — convert to metric, then per person.
            mq, mu = units.to_metric(ing.quantity, ing.unit)
            qty_pp = units.per_person(mq, ext.base_servings)
            session.add(Ingredient(
                recipe_id=recipe.id,
                name=ing.name,
                quantity_per_person=qty_pp,
                unit=mu,
                category=ing.category,
                raw_text=ing.raw_text,
                sort_order=idx,
            ))

        for idx, text in enumerate(ext.steps):
            session.add(InstructionStep(recipe_id=recipe.id, step_number=idx + 1, text=text))

        session.commit()
        session.refresh(recipe)
        return recipe

    # ------------------------------------------------------------------
    # Abort a processing job (resets it to pending)
    # ------------------------------------------------------------------
    def abort_job(self, job_id: int) -> bool:
        with self._sf() as session:
            job = session.get(ImportJob, job_id)
            if job is None or job.status != JOB_PROCESSING:
                return False
            _ABORT_REQUESTED.add(job_id)
            return True

    # ------------------------------------------------------------------
    # Delete a job, all its recipes, and the uploaded source file
    # ------------------------------------------------------------------
    def delete_job(self, job_id: int) -> dict:
        with self._sf() as session:
            job = session.get(ImportJob, job_id)
            if job is None:
                return {"deleted": False}
            stored_file = job.stored_file
            recipes = session.exec(
                select(Recipe).where(Recipe.import_job_id == job_id)
            ).all()
            accepted_count = sum(1 for r in recipes if r.status == RECIPE_ACCEPTED)
            for r in recipes:
                session.delete(r)
            session.delete(job)
            session.commit()
        file_path = settings.uploads_dir / stored_file
        try:
            file_path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete uploaded file %s", file_path)
        return {"deleted": True, "accepted_removed": accepted_count}

    # ------------------------------------------------------------------
    # Retry a failed job
    # ------------------------------------------------------------------
    def retry_job(self, job_id: int) -> ImportJobSummary | None:
        with self._sf() as session:
            job = session.get(ImportJob, job_id)
            if job is None or job.status != JOB_FAILED:
                return None
            # Remove any draft recipes left over from the failed run
            drafts = session.exec(
                select(Recipe).where(Recipe.import_job_id == job_id)
            ).all()
            for r in drafts:
                session.delete(r)
            job.status = JOB_PENDING
            job.error = None
            job.processed_at = None
            job.recipe_count = 0
            job.phase = None
            job.progress_current = 0
            job.progress_total = 0
            session.add(job)
            session.commit()
            session.refresh(job)
            return _job_summary(job)

    # ------------------------------------------------------------------
    # Accept drafts
    # ------------------------------------------------------------------
    def accept(self, job_id: int, recipe_ids: list[int] | None = None) -> list[int]:
        with self._sf() as session:
            stmt = select(Recipe).where(
                Recipe.import_job_id == job_id,
                Recipe.status == RECIPE_DRAFT,
            )
            if recipe_ids is not None:
                stmt = stmt.where(Recipe.id.in_(recipe_ids))
            recipes = session.exec(stmt).all()
            accepted_ids = []
            for r in recipes:
                r.status = RECIPE_ACCEPTED
                session.add(r)
                accepted_ids.append(r.id)
            session.commit()
            return accepted_ids


def _job_summary(j: ImportJob) -> ImportJobSummary:
    return ImportJobSummary(
        id=j.id,
        filename=j.filename,
        source_format=j.source_format,
        status=j.status,
        error=j.error,
        recipe_count=j.recipe_count,
        progress_current=j.progress_current,
        progress_total=j.progress_total,
        phase=j.phase,
        created_at=j.created_at,
        processed_at=j.processed_at,
    )
