"""Accept an explicitly reviewed conformer candidate from a persistent CBQ."""

from concurrent.futures import CancelledError
from uuid import UUID

from cbq_core.model import ImportBatch
from .protocol import ProtocolError
from .wavefunction_operations import _output


def accept_group(context, request):
    from ..core.import_pipeline.conformer_grouping import (
        project_conformer_batch, suggest_conformer_groups, accept_conformer_group,
        ConformerGroupingCancelled,
    )
    parameters = dict(request.parameters)
    if set(parameters) - {"suggestion_id", "snapshot", "review_confirmed"} or not {"suggestion_id", "snapshot"} <= parameters.keys():
        raise ProtocolError("Conformer grouping requires suggestion_id and snapshot; optional review_confirmed")
    identity = UUID(parameters["suggestion_id"])
    batch = project_conformer_batch(context.project)
    try:
        group = next((value for value in suggest_conformer_groups(batch, is_cancelled=context.is_cancelled)
                      if value.id == identity), None)
        if group is None or group.snapshot != parameters["snapshot"]:
            raise ValueError("Conformer candidate is missing or stale; inspect this CBQ again")
        if {value.entity_id for value in request.inputs} != set(group.record_ids):
            raise ValueError("Inputs must contain exactly the selected molecular records")
        if len(group.evidence) > 100 or any(len(value.atom_mapping) > 100 for value in group.evidence):
            raise ValueError("Conformer evidence exceeds the inspection display limit; full review is required")
        accepted = accept_conformer_group(group, batch,
            review_confirmed=parameters.get("review_confirmed", False), is_cancelled=context.is_cancelled)
    except ConformerGroupingCancelled as error:
        raise CancelledError("Conformer grouping cancelled") from error
    return _output(ImportBatch(datasets=(*accepted.property_columns, accepted.conformer_set),
                               provenance=(accepted.provenance,)))
