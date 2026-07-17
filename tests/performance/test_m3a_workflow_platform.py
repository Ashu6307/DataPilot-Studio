from __future__ import annotations

from packages.workflow_dag import build_execution_plan, validate_dag
from packages.workflow_dag.subflows import expand_subflows
from scripts.benchmark_m3a import branching_workflow, linear_workflow, subflow_expansion


def test_m3a_planning_and_validation_harness_reports_real_graph_counts() -> None:
    plan = build_execution_plan(linear_workflow(25))
    assert len(plan.nodes) == 25
    assert plan.nodes[-1].sequence == 25
    validation = validate_dag(linear_workflow(100))
    assert validation.valid
    assert len(validation.topological_order) == 100
    branch_plan = build_execution_plan(branching_workflow())
    assert max(node.parallel_group for node in branch_plan.nodes) == 3
    root, definitions = subflow_expansion()
    assert len(expand_subflows(root, definitions).nodes) == 20
