"""Persistent local background executor for reconciliation workflows."""

from __future__ import annotations

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
    ReconciliationJobSubmission,
    RunRecord,
    RunStatus,
)
from packages.data_engine.background import BackgroundJobCancelled, JobControl


class ReconciliationJobStore(Protocol):
    def create(self, job: BackgroundJobRecord, submission: ReconciliationJobSubmission) -> BackgroundJobRecord: ...
    def get(self, job_id: UUID) -> BackgroundJobRecord | None: ...
    def submission(self, job_id: UUID) -> ReconciliationJobSubmission | None: ...
    def update(self, job: BackgroundJobRecord) -> BackgroundJobRecord: ...
    def list_jobs(self, project_id: UUID | None = None) -> list[BackgroundJobRecord]: ...
    def append_event(self, event: JobProgressEvent) -> JobProgressEvent: ...
    def events(self, job_id: UUID) -> list[JobProgressEvent]: ...
    def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord: ...
    def checkpoints(self, job_id: UUID) -> list[CheckpointRecord]: ...
    def recover_orphans(self) -> list[BackgroundJobRecord]: ...


ReconciliationJobHandler = Callable[[ReconciliationJobSubmission, JobControl], RunRecord]


class LocalReconciliationJobExecutor:
    def __init__(
        self,
        store: ReconciliationJobStore,
        handler: ReconciliationJobHandler,
        max_workers: int = 1,
    ) -> None:
        self.store = store
        self.handler = handler
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="datapilot-reconciliation")
        self._futures: dict[UUID, Future[None]] = {}
        self._lock = threading.Lock()
        self.store.recover_orphans()

    def submit(self, submission: ReconciliationJobSubmission) -> BackgroundJobRecord:
        workflow = submission.run.workflow
        job = BackgroundJobRecord(
            project_id=workflow.project_id,
            source_id=workflow.left_dataset_id,
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            retry_of=submission.retry_of,
        )
        self.store.create(job, submission)
        self.store.append_event(
            JobProgressEvent(
                job_id=job.id,
                sequence=1,
                status=RunStatus.QUEUED,
                message="Reconciliation queued for local background execution",
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
        control.progress("reconciliation.validate", 0, None, "Validating immutable reconciliation workflow")
        try:
            control.check_cancelled()
            run = self.handler(submission, control)
            control.check_cancelled()
            if run.status not in {RunStatus.SUCCEEDED, RunStatus.PARTIAL}:
                raise RuntimeError(f"RUN_TERMINATED_WITH_{run.status.value.upper()}")
            current = self.store.get(job_id) or running
            self.store.update(
                current.model_copy(
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
            )
            control.progress("complete", run.rows_read, run.rows_read, "Reconciliation completed")
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
                    message="Cancelled reconciliation artifacts remain isolated and unpublished",
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
                    message=f"Reconciliation failed; correlation ID {failed.correlation_id}",
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
        return self.submit(ReconciliationJobSubmission(run=submission.run, retry_of=job.id))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
