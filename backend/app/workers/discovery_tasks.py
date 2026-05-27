"""Celery tasks for product discovery."""
import asyncio
from app.workers.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.services.discovery import run_discovery
from app.models.job import DiscoveryJob, JobStatus
from datetime import datetime, timezone
import structlog

log = structlog.get_logger()


@celery_app.task(bind=True, name="app.workers.discovery_tasks.discover_product")
def discover_product(self, model_number: str, job_id: int):
    """Celery task: run full product discovery for a model number."""
    log.info("celery.discovery_start", model=model_number, job_id=job_id)
    try:
        asyncio.run(_run(model_number, job_id))
        log.info("celery.discovery_done", model=model_number, job_id=job_id)
    except Exception as e:
        log.error("celery.discovery_failed", model=model_number, error=str(e))
        asyncio.run(_mark_failed(job_id, str(e)))
        raise


async def _run(model_number: str, job_id: int):
    async with AsyncSessionLocal() as db:
        await run_discovery(model_number, job_id, db)


async def _mark_failed(job_id: int, error: str):
    async with AsyncSessionLocal() as db:
        job = await db.get(DiscoveryJob, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = error
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
