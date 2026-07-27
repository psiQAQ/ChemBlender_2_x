"""Pure extXYZ preview summary shared by UI and benchmarks."""

from dataclasses import dataclass

from ..core import (
    AtomFrameProperty,
    CellFrameProperty,
    FrameProperty,
    FrameSet,
    IssueKind,
)


@dataclass(frozen=True, slots=True)
class ExtXYZPreviewSummary:
    frame_count: int
    atom_properties: tuple[str, ...]
    frame_properties: tuple[str, ...]
    has_lattice: bool
    pbc: tuple[bool, bool, bool] | None
    pbc_changes: bool
    assumed_units: tuple[str, ...]


def extxyz_preview_summary(batch):
    frames = tuple(
        dataset for dataset in batch.datasets if isinstance(dataset, FrameSet)
    )
    atom_properties = tuple(
        sorted(
            {
                dataset.semantic_role
                for dataset in batch.datasets
                if isinstance(dataset, AtomFrameProperty)
            }
        )
    )
    frame_properties = tuple(
        sorted(
            {
                dataset.semantic_role
                for dataset in batch.datasets
                if isinstance(dataset, (FrameProperty, CellFrameProperty))
            }
        )
    )
    pbc = next(
        (
            structure.periodic.pbc
            for structure in batch.structures
            if structure.periodic is not None
        ),
        None,
    )
    issues = () if batch.report is None else batch.report.issues
    return ExtXYZPreviewSummary(
        frame_count=sum(dataset.data.shape[0] for dataset in frames),
        atom_properties=atom_properties,
        frame_properties=frame_properties,
        has_lattice=any(
            structure.cell is not None for structure in batch.structures
        )
        or any(
            isinstance(dataset, CellFrameProperty)
            for dataset in batch.datasets
        ),
        pbc=pbc,
        pbc_changes=any(
            isinstance(dataset, FrameProperty)
            and dataset.semantic_role == "pbc"
            for dataset in batch.datasets
        ),
        assumed_units=tuple(
            sorted(
                {
                    issue.message
                    for issue in issues
                    if issue.kind is IssueKind.AMBIGUOUS
                    and " was assumed " in issue.message
                }
            )
        ),
    )


__all__ = ("ExtXYZPreviewSummary", "extxyz_preview_summary")
