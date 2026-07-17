from __future__ import annotations

from uuid import uuid4

from apps.api.app.database import Database
from apps.api.app.repositories import SQLiteMetadataRepository
from packages.contracts import (
    DecisionMemory,
    DecisionMemoryKind,
    Project,
    ReconciliationRunRecord,
    ReconciliationSummary,
    ReviewDecision,
    ReviewDecisionEvent,
    ReviewQueueItem,
    RunStatus,
)


def _summary() -> ReconciliationSummary:
    return ReconciliationSummary(
        total_left_rows=1,
        total_right_rows=1,
        matched=0,
        exact_matches=0,
        normalised_matches=0,
        tolerance_matches=0,
        fuzzy_matches=0,
        weighted_matches=0,
        review_pending=1,
        left_unmatched=1,
        right_unmatched=1,
    )


def test_review_decisions_are_append_only_and_superseding(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    repository = SQLiteMetadataRepository(database)
    project = repository.create_project(Project(name="Review persistence"))
    run_id = uuid4()
    repository.save_reconciliation_run(
        ReconciliationRunRecord(
            run_id=run_id,
            project_id=project.id,
            workflow_id=uuid4(),
            workflow_version=1,
            status=RunStatus.SUCCEEDED,
            summary=_summary(),
            audit=["created"],
        )
    )
    item = ReviewQueueItem(
        reconciliation_run_id=run_id,
        left_record={"key": "01"},
        right_candidates=[{"key": "02"}],
        candidates=[],
        match_stage_id="review",
        review_reason="policy",
    )
    repository.save_review_items([item])
    first = ReviewDecisionEvent(
        review_item_id=item.id,
        decision=ReviewDecision.DEFER,
        reviewer="reviewer-a",
        comment="needs evidence",
    )
    repository.append_review_decision(first)
    second = ReviewDecisionEvent(
        review_item_id=item.id,
        decision=ReviewDecision.REJECT_ALL,
        reviewer="reviewer-b",
        supersedes_event_id=first.id,
    )
    repository.append_review_decision(second)
    events = repository.list_review_decisions(item.id)
    assert events == [first, second]
    assert events[0].decision == ReviewDecision.DEFER
    current = repository.list_review_items(run_id)[0]
    assert current.status == "rejected"
    assert current.audit_event_ids == [first.id, second.id]


def test_decision_memory_is_project_scoped_deletable_and_audited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    database = Database(tmp_path / "metadata.sqlite3")
    database.initialize()
    repository = SQLiteMetadataRepository(database)
    project = repository.create_project(Project(name="Decision memory"))
    memory = DecisionMemory(
        project_id=project.id,
        kind=DecisionMemoryKind.APPROVED_SYNONYM,
        source_value="alpha co",
        canonical_value="alpha company",
    )
    repository.save_decision_memory(memory)
    assert repository.list_decision_memory(project.id) == [memory]
    deactivated = repository.deactivate_decision_memory(memory.id, "owner", "user requested deletion")
    assert not deactivated.active
    assert deactivated.source_value == "[deleted]"
    assert deactivated.canonical_value == "[deleted]"
    assert repository.list_decision_memory(project.id) == []
    with database.connect() as connection:
        actions = [
            row[0]
            for row in connection.execute(
                "SELECT action FROM decision_memory_events WHERE memory_id = ? ORDER BY created_at",
                (str(memory.id),),
            ).fetchall()
        ]
    assert actions == ["created", "deactivated"]
