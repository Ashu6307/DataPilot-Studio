"""Persistent local background jobs with cooperative cancellation and recovery."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from packages.contracts import (
    BackgroundJobRecord,
    CheckpointRecord,
    JobProgressEvent,
    JobSubmission,
    RunRecord,
    RunStatus,
)


class JobStore(Protocol):
    def create(self, job: BackgroundJobRecord, submission: JobSubmission) -> BackgroundJobRecord: ...
    def get(self, job_id: UUID) -> BackgroundJobRecord | None: ...
    def submission(self, job_id: UUID) -> JobSubmission | None: ...
    def update(self, job: BackgroundJobRecord) -> BackgroundJobRecord: ...
    def list_jobs(self, project_id: UUID | None = None) -> list[BackgroundJobRecord]: ...
    def append_event(self, event: JobProgressEvent) -> JobProgressEvent: ...
    def events(self, job_id: UUID) -> list[JobProgressEvent]: ...
    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord: ...
    def checkpoints(self, job_id: UUID) -> list[CheckpointRecord]: ...
    def recover_orphans(self) -> list[BackgroundJobRecord]: ...


class BackgroundJobCancelled(RuntimeError):
    pass


class JobControl:
    def __init__(self, store: JobStore, job_id: UUID) -> None:
        self.store = store
        self.job_id = job_id

    def check_cancelled(self) -> None:
        job = self.store.get(self.job_id)
        if job is None:
            raise BackgroundJobCancelled("JOB_NOT_FOUND_DURING_EXECUTION")
        if job.cancel_requested or job.status in {RunStatus.CANCELLING, RunStatus.CANCELLED}:
            raise BackgroundJobCancelled("JOB_CANCELLED_BY_USER")

    def progress(
        self,
        operation: str,
        rows_processed: int,
        estimated_total_rows: int | None,
        message: str,
    ) -> None:
        job = self.store.get(self.job_id)
        if job is None:
            return
        percent = (
            min(100.0, rows_processed * 100 / estimated_total_rows)
            if estimated_total_rows and estimated_total_rows > 0
            else None
        )
        updated = job.model_copy(
            update={
                "current_operation": operation,
                "rows_processed": rows_processed,
                "estimated_total_rows": estimated_total_rows,
                "progress_percent": percent,
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.update(updated)
        sequence = len(self.store.events(self.job_id)) + 1
        self.store.append_event(
            JobProgressEvent(
                job_id=self.job_id,
                sequence=sequence,
                status=updated.status,
                current_operation=operation,
                rows_processed=rows_processed,
                estimated_total_rows=estimated_total_rows,
                progress_percent=percent,
                message=message,
            )
        )


JobHandler = Callable[[JobSubmission, JobControl], RunRecord]


class LocalJobExecutor:
    def __init__(self, store: JobStore, handler: JobHandler, max_workers: int = 1) -> None:
        self.store = store
        self.handler = handler
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="datapilot-job")
        self._futures: dict[UUID, Future[None]] = {}
        self._lock = threading.Lock()
        self.store.recover_orphans()

    def submit(self, submission: JobSubmission) -> BackgroundJobRecord:
        request = submission.run
        job = BackgroundJobRecord(
            project_id=request.workflow.project_id,
            source_id=request.source_id,
            workflow_id=request.workflow.id,
            workflow_version=request.workflow.workflow_version,
            retry_of=submission.retry_of,
        )
        self.store.create(job, submission)
        self.store.append_event(
            JobProgressEvent(
                job_id=job.id,
                sequence=1,
                status=RunStatus.QUEUED,
                message="Run queued for local background execution",
            )
        )
        with self._lock:
            self._futures[job.id] = self.executor.submit(self._run, job.id)
        return job

    def _run(self, job_id: UUID) -> None:
        job = self.store.get(job_id)
        submission = self.store.submission(job_id)
        if job is None or submission is None:
            return
        running = job.model_copy(
            update={"status": RunStatus.RUNNING, "updated_at": datetime.now(UTC)}
        )
        self.store.update(running)
        control = JobControl(self.store, job_id)
        control.progress("request.validate", 0, None, "Validating immutable run request")
        try:
            control.check_cancelled()
            run = self.handler(submission, control)
            control.check_cancelled()
            final_status = run.status
            if final_status not in {RunStatus.SUCCEEDED, RunStatus.PARTIAL}:
                raise RuntimeError(f"RUN_TERMINATED_WITH_{final_status.value.upper()}")
            completed = self.store.get(job_id) or running
            self.store.update(
                completed.model_copy(
                    update={
                        "status": final_status,
                        "run_id": run.id,
                        "current_operation": "complete",
                        "rows_processed": run.rows_read,
                        "estimated_total_rows": run.rows_read,
                        "progress_percent": 100.0,
                        "output_available": final_status == RunStatus.SUCCEEDED,
                        "updated_at": datetime.now(UTC),
                    }
                )
            )
            control.progress("complete", run.rows_read, run.rows_read, f"Run finished as {final_status}")
        except BackgroundJobCancelled as error:
            current = self.store.get(job_id) or running
            cancelled = current.model_copy(
                update={
                    "status": RunStatus.CANCELLED,
                    "output_available": False,
                    "error_code": "JOB_CANCELLED",
                    "error_message": str(error),
                    "updated_at": datetime.now(UTC),
                }
            )
            self.store.update(cancelled)
            self.store.append_event(
                JobProgressEvent(
                    job_id=job_id,
                    sequence=len(self.store.events(job_id)) + 1,
                    status=RunStatus.CANCELLED,
                    current_operation=cancelled.current_operation,
                    rows_processed=cancelled.rows_processed,
                    estimated_total_rows=cancelled.estimated_total_rows,
                    progress_percent=cancelled.progress_percent,
                    message="Cancellation completed; unpublished artifacts remain isolated",
                )
            )
        except Exception as error:
            current = self.store.get(job_id) or running
            failed = current.model_copy(
                update={
                    "status": RunStatus.FAILED,
                    "output_available": False,
                    "retry_eligible": isinstance(error, OSError),
                    "error_code": type(error).__name__.upper(),
                    "error_message": str(error),
                    "updated_at": datetime.now(UTC),
                }
            )
            self.store.update(failed)
            self.store.append_event(
                JobProgressEvent(
                    job_id=job_id,
                    sequence=len(self.store.events(job_id)) + 1,
                    status=RunStatus.FAILED,
                    current_operation=failed.current_operation,
                    rows_processed=failed.rows_processed,
                    estimated_total_rows=failed.estimated_total_rows,
                    progress_percent=failed.progress_percent,
                    message=f"Run failed; correlation ID {failed.correlation_id}",
                )
            )

    def cancel(self, job_id: UUID) -> BackgroundJobRecord:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        if job.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}:
            return job
        updated = job.model_copy(
            update={
                "status": RunStatus.CANCELLING,
                "cancel_requested": True,
                "updated_at": datetime.now(UTC),
            }
        )
        return self.store.update(updated)

    def retry(self, job_id: UUID) -> BackgroundJobRecord:
        job = self.store.get(job_id)
        submission = self.store.submission(job_id)
        if job is None or submission is None:
            raise KeyError("JOB_NOT_FOUND")
        if not job.retry_eligible:
            raise ValueError("JOB_RETRY_NOT_SAFE")
        return self.submit(JobSubmission(run=submission.run, retry_of=job.id))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def workflow_hash(submission: JobSubmission) -> str:
    payload = submission.run.workflow.model_dump_json()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
