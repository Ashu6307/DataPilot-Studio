"""SQLite persistence adapter for composition background submissions."""

from __future__ import annotations

from uuid import UUID

from packages.contracts import (
    BackgroundJobRecord,
    CheckpointRecord,
    CompositionJobSubmission,
    JobProgressEvent,
)

from .database import Database
from .job_store import SQLiteJobStore


class SQLiteCompositionJobStore:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.shared = SQLiteJobStore(database)

    def create(self, job: BackgroundJobRecord, submission: CompositionJobSubmission) -> BackgroundJobRecord:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO jobs
                (id, project_id, run_id, status, request_json, record_json, correlation_id,
                 cancel_requested, retry_of, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(job.id),
                    str(job.project_id),
                    None,
                    job.status,
                    submission.model_dump_json(),
                    job.model_dump_json(),
                    str(job.correlation_id),
                    0,
                    str(job.retry_of) if job.retry_of else None,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        return job

    def submission(self, job_id: UUID) -> CompositionJobSubmission | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT request_json FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        return CompositionJobSubmission.model_validate_json(row["request_json"]) if row else None

    def get(self, job_id: UUID) -> BackgroundJobRecord | None:
        return self.shared.get(job_id)

    def update(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        return self.shared.update(job)

    def list_jobs(self, project_id: UUID | None = None) -> list[BackgroundJobRecord]:
        return self.shared.list_jobs(project_id)

    def append_event(self, event: JobProgressEvent) -> JobProgressEvent:
        return self.shared.append_event(event)

    def events(self, job_id: UUID) -> list[JobProgressEvent]:
        return self.shared.events(job_id)

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        return self.shared.save_checkpoint(checkpoint)

    def checkpoints(self, job_id: UUID) -> list[CheckpointRecord]:
        return self.shared.checkpoints(job_id)

    def recover_orphans(self) -> list[BackgroundJobRecord]:
        return self.shared.recover_orphans()
