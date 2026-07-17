from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from apps.api.app.database import Database
from apps.api.app.job_store import SQLiteJobStore
from packages.contracts import (
    BackgroundJobRecord,
    CheckpointRecord,
    JobSubmission,
    RunRecord,
    RunRequest,
    RunStatus,
    WorkflowConfiguration,
)
from packages.data_engine import JobControl, LocalJobExecutor
from packages.data_engine.background import workflow_hash


def _submission(workflow: WorkflowConfiguration) -> JobSubmission:
    return JobSubmission(run=RunRequest(source_id=uuid4(), workflow=workflow))


def _wait(store: SQLiteJobStore, job_id: UUID, statuses: set[RunStatus]) -> BackgroundJobRecord:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = store.get(job_id)
        assert job is not None
        if job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job did not reach {statuses}")


def _run_record(submission: JobSubmission, status: RunStatus = RunStatus.SUCCEEDED) -> RunRecord:
    workflow = submission.run.workflow
    return RunRecord(
        project_id=workflow.project_id,
        workflow_id=workflow.id,
        workflow_version=workflow.workflow_version,
        status=status,
        ended_at=datetime.now(UTC),
        source_filename="anonymised.csv",
        source_fingerprint="a" * 64,
        rows_read=10,
        rows_written=10 if status == RunStatus.SUCCEEDED else 5,
    )


def test_background_job_lifecycle_progress_and_checkpoint(workflow: WorkflowConfiguration, tmp_path: Path) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    store = SQLiteJobStore(database)

    def handler(submission: JobSubmission, control: JobControl) -> RunRecord:
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=submission.run.workflow.id,
                workflow_version=submission.run.workflow.workflow_version,
                workflow_hash=workflow_hash(submission),
                source_fingerprint="a" * 64,
                completed_stage="validated",
                resumable=True,
            )
        )
        control.progress("clean", 5, 10, "Processed first bounded batch")
        control.check_cancelled()
        control.progress("export", 10, 10, "Processed final bounded batch")
        return _run_record(submission)

    executor = LocalJobExecutor(store, handler)
    try:
        job = executor.submit(_submission(workflow))
        completed = _wait(store, job.id, {RunStatus.SUCCEEDED})
        assert completed.output_available
        assert completed.progress_percent == 100
        events = store.events(job.id)
        assert [event.sequence for event in events] == list(range(1, len(events) + 1))
        assert store.checkpoints(job.id)[0].resumable
    finally:
        executor.shutdown()


def test_cancellation_never_becomes_successful(workflow: WorkflowConfiguration, tmp_path: Path) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    store = SQLiteJobStore(database)

    def handler(submission: JobSubmission, control: JobControl) -> RunRecord:
        for batch in range(1, 51):
            control.progress("batched.clean", batch, 50, f"Batch {batch}")
            time.sleep(0.005)
            control.check_cancelled()
        return _run_record(submission)

    executor = LocalJobExecutor(store, handler)
    try:
        job = executor.submit(_submission(workflow))
        _wait(store, job.id, {RunStatus.RUNNING})
        executor.cancel(job.id)
        cancelled = _wait(store, job.id, {RunStatus.CANCELLED})
        assert not cancelled.output_available
        assert cancelled.error_code == "JOB_CANCELLED"
        time.sleep(0.03)
        final = store.get(job.id)
        assert final is not None and final.status == RunStatus.CANCELLED
    finally:
        executor.shutdown()


def test_failure_retry_policy_and_restart_recovery(workflow: WorkflowConfiguration, tmp_path: Path) -> None:
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    store = SQLiteJobStore(database)

    def retryable_failure(_: JobSubmission, __: JobControl) -> RunRecord:
        raise OSError("temporary locked output")

    executor = LocalJobExecutor(store, retryable_failure)
    try:
        failed_job = executor.submit(_submission(workflow))
        failed = _wait(store, failed_job.id, {RunStatus.FAILED})
        assert failed.retry_eligible
        retried = executor.retry(failed.id)
        assert retried.retry_of == failed.id
        _wait(store, retried.id, {RunStatus.FAILED})
    finally:
        executor.shutdown()

    submission = _submission(workflow)
    orphan = BackgroundJobRecord(
        project_id=workflow.project_id,
        source_id=submission.run.source_id,
        workflow_id=workflow.id,
        workflow_version=workflow.workflow_version,
        status=RunStatus.RUNNING,
    )
    store.create(orphan, submission)
    store.save_checkpoint(
        CheckpointRecord(
            job_id=orphan.id,
            workflow_id=workflow.id,
            workflow_version=workflow.workflow_version,
            workflow_hash=workflow_hash(submission),
            source_fingerprint="b" * 64,
            completed_stage="request_validated",
            resumable=True,
        )
    )
    recovered = store.recover_orphans()
    assert recovered[0].status == RunStatus.FAILED
    assert recovered[0].retry_eligible
    assert recovered[0].error_code == "ORPHANED_JOB_RECOVERED"
