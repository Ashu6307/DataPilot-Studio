"""Persistent background executor specialised for composition plans."""

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
    CompositionJobSubmission,
    JobProgressEvent,
    RunRecord,
    RunStatus,
)
from packages.data_engine.background import BackgroundJobCancelled, JobControl


class CompositionJobStore(Protocol):
    def create(self, job: BackgroundJobRecord, submission: CompositionJobSubmission) -> BackgroundJobRecord: ...
    def get(self, job_id: UUID) -> BackgroundJobRecord | None: ...
    def submission(self, job_id: UUID) -> CompositionJobSubmission | None: ...
    def update(self, job: BackgroundJobRecord) -> BackgroundJobRecord: ...
    def list_jobs(self, project_id: UUID | None = None) -> list[BackgroundJobRecord]: ...
    def append_event(self, event: JobProgressEvent) -> JobProgressEvent: ...
    def events(self, job_id: UUID) -> list[JobProgressEvent]: ...
    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord: ...
    def checkpoints(self, job_id: UUID) -> list[CheckpointRecord]: ...
    def recover_orphans(self) -> list[BackgroundJobRecord]: ...


CompositionJobHandler = Callable[[CompositionJobSubmission, JobControl], RunRecord]


class LocalCompositionJobExecutor:
    def __init__(
        self,
        store: CompositionJobStore,
        handler: CompositionJobHandler,
        max_workers: int = 1,
    ) -> None:
        self.store = store
        self.handler = handler
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="datapilot-composition")
        self._futures: dict[UUID, Future[None]] = {}
        self._lock = threading.Lock()
        self.store.recover_orphans()

    def submit(self, submission: CompositionJobSubmission) -> BackgroundJobRecord:
        plan = submission.run.plan
        job = BackgroundJobRecord(
            project_id=plan.project_id,
            source_id=plan.source_ids[0],
            workflow_id=plan.id,
            workflow_version=plan.version,
            retry_of=submission.retry_of,
        )
        self.store.create(job, submission)
        self.store.append_event(
            JobProgressEvent(
                job_id=job.id,
                sequence=1,
                status=RunStatus.QUEUED,
                message="Composition run queued for local background execution",
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
        running = job.model_copy(update={"status": RunStatus.RUNNING, "updated_at": datetime.now(UTC)})
        self.store.update(running)
        control = JobControl(self.store, job_id)
        control.progress("composition.validate", 0, None, "Validating immutable composition plan")
        try:
            control.check_cancelled()
            run = self.handler(submission, control)
            control.check_cancelled()
            if run.status not in {RunStatus.SUCCEEDED, RunStatus.PARTIAL}:
                raise RuntimeError(f"RUN_TERMINATED_WITH_{run.status.value.upper()}")
            current = self.store.get(job_id) or running
            completed = current.model_copy(
                update={
                    "status": run.status,
                    "run_id": run.id,
                    "current_operation": "complete",
                    "rows_processed": run.rows_read,
                    "estimated_total_rows": run.rows_read,
                    "progress_percent": 100.0,
                    "output_available": run.status == RunStatus.SUCCEEDED,
                    "updated_at": datetime.now(UTC),
                }
            )
            self.store.update(completed)
            control.progress("complete", run.rows_read, run.rows_read, f"Composition finished as {run.status}")
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
                    message="Cancelled composition artifacts remain isolated and unpublished",
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
                    message=f"Composition failed; correlation ID {failed.correlation_id}",
                )
            )

    def cancel(self, job_id: UUID) -> BackgroundJobRecord:
        job = self.store.get(job_id)
        if job is None:
            raise KeyError("JOB_NOT_FOUND")
        if job.status in {RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.CANCELLED}:
            return job
        return self.store.update(
            job.model_copy(
                update={
                    "status": RunStatus.CANCELLING,
                    "cancel_requested": True,
                    "updated_at": datetime.now(UTC),
                }
            )
        )

    def retry(self, job_id: UUID) -> BackgroundJobRecord:
        job = self.store.get(job_id)
        submission = self.store.submission(job_id)
        if job is None or submission is None:
            raise KeyError("JOB_NOT_FOUND")
        if not job.retry_eligible:
            raise ValueError("JOB_RETRY_NOT_SAFE")
        return self.submit(CompositionJobSubmission(run=submission.run, retry_of=job.id))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)


def composition_hash(submission: CompositionJobSubmission) -> str:
    return hashlib.sha256(submission.run.plan.model_dump_json().encode("utf-8")).hexdigest()
