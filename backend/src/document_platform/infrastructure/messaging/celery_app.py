"""Celery CLI entry point; validate deployment configuration before connecting."""

from document_platform.config import Settings
from document_platform.infrastructure.messaging.worker import create_celery

celery_app = create_celery(Settings())
