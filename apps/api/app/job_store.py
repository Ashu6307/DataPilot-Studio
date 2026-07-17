"""SQLite implementation of the replaceable background job persistence contract."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from packages.contracts import (
    BackgroundJobRecord,
    CheckpointRecord,
    JobProgressEvent,
    JobSubmission,
    RunStatus,
)

from .database import Database


class SQLiteJobStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, job: BackgroundJobRecord, submission: JobSubmission) -> BackgroundJobRecord:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(job.id),
                    str(job.project_id),
                    str(job.run_id) if job.run_id else None,
                    job.status,
                    submission.model_dump_json(),
                    job.model_dump_json(),
                    str(job.correlation_id),
                    int(job.cancel_requested),
                    str(job.retry_of) if job.retry_of else None,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )
        return job

    def get(self, job_id: UUID) -> BackgroundJobRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT record_json FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        return BackgroundJobRecord.model_validate_json(row["record_json"]) if row else None

    def submission(self, job_id: UUID) -> JobSubmission | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT request_json FROM jobs WHERE id = ?", (str(job_id),)).fetchone()
        return JobSubmission.model_validate_json(row["request_json"]) if row else None

    def update(self, job: BackgroundJobRecord) -> BackgroundJobRecord:
        with self.database.connect() as connection:
            changed = connection.execute(
                """
                UPDATE jobs SET run_id = ?, status = ?, record_json = ?, cancel_requested = ?,
                    updated_at = ? WHERE id = ?
                """,
                (
                    str(job.run_id) if job.run_id else None,
                    job.status,
                    job.model_dump_json(),
                    int(job.cancel_requested),
                    job.updated_at.isoformat(),
                    str(job.id),
                ),
            ).rowcount
        if changed != 1:
            raise KeyError("JOB_NOT_FOUND")
        return job

    def list_jobs(self, project_id: UUID | None = None) -> list[BackgroundJobRecord]:
        query = "SELECT record_json FROM jobs"
        parameters: tuple[str, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            parameters = (str(project_id),)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [BackgroundJobRecord.model_validate_json(row["record_json"]) for row in rows]

    def append_event(self, event: JobProgressEvent) -> JobProgressEvent:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO job_events(job_id, sequence, event_json, created_at) VALUES (?, ?, ?, ?)",
                (str(event.job_id), event.sequence, event.model_dump_json(), event.created_at.isoformat()),
            )
        return event

    def events(self, job_id: UUID) -> list[JobProgressEvent]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM job_events WHERE job_id = ? ORDER BY sequence", (str(job_id),)
            ).fetchall()
        return [JobProgressEvent.model_validate_json(row["event_json"]) for row in rows]

    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO checkpoints VALUES (?, ?, ?, ?)",
                (
                    str(checkpoint.id),
                    str(checkpoint.job_id),
                    checkpoint.model_dump_json(),
                    checkpoint.created_at.isoformat(),
                ),
            )
        return checkpoint

    def checkpoints(self, job_id: UUID) -> list[CheckpointRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT checkpoint_json FROM checkpoints WHERE job_id = ? ORDER BY created_at",
                (str(job_id),),
            ).fetchall()
        return [CheckpointRecord.model_validate_json(row["checkpoint_json"]) for row in rows]

    def recover_orphans(self) -> list[BackgroundJobRecord]:
        recovered: list[BackgroundJobRecord] = []
        for job in self.list_jobs():
            if job.status not in {RunStatus.RUNNING, RunStatus.CANCELLING}:
                continue
            resumable = any(item.resumable for item in self.checkpoints(job.id))
            recovered_job = job.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "retry_eligible": resumable,
                    "output_available": False,
                    "error_code": "ORPHANED_JOB_RECOVERED",
                    "error_message": "Application restarted before the job reached a terminal state",
                    "updated_at": datetime.now(UTC),
                }
            )
            self.update(recovered_job)
            self.append_event(
                JobProgressEvent(
                    job_id=job.id,
                    sequence=len(self.events(job.id)) + 1,
                    status=RunStatus.FAILED,
                    current_operation=job.current_operation,
                    rows_processed=job.rows_processed,
                    estimated_total_rows=job.estimated_total_rows,
                    progress_percent=job.progress_percent,
                    message="Orphaned job recovered after restart; explicit retry is required",
                )
            )
            recovered.append(recovered_job)
        return recovered
