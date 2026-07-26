"""Illustrative callback shape; connect it to a real solver callback in your project."""

from runbuoy import progress


def report_solver_progress(nodes_processed: int, node_limit: int, gap: float) -> None:
    progress(
        nodes_processed,
        node_limit,
        unit="nodes",
        phase="optimizing",
        message=f"Solver gap {gap:.2%}",
    )
