from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "pricewatch",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.discovery_tasks",
        "app.workers.scrape_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Periodic scrape schedule — every 6 hours
    beat_schedule={
        "scrape-active-monitors-every-6h": {
            "task": "app.workers.scrape_tasks.scrape_all_active_monitors",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
