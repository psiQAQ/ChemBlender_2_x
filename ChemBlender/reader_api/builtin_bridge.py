from uuid import uuid4 as _uuid4

from ..core import ImportBatch as _ImportBatch, QCProject as _QCProject
from ..core.sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION as _CURRENT_PROJECT_SCHEMA_VERSION
from .public_model import (
    PublicImportBatch as _PublicImportBatch,
    _validate_public_batch_values,
)


__all__ = (
    "PublicBatchError",
    "PublicBatchValidationError",
    "public_batch_from_internal",
    "internal_batch_from_public",
)


class PublicBatchError(Exception):
    pass


class PublicBatchValidationError(PublicBatchError):
    pass


_BATCH_FIELDS = (
    "sources", "source_revisions", "structures", "cif_envelopes",
    "qcschema_envelopes", "cjson_envelopes", "symmetry_results",
    "calculations", "datasets", "basis_sets", "orbital_sets",
    "density_matrices", "provenance", "report", "diagnostics",
)


def public_batch_from_internal(batch) -> _PublicImportBatch:
    if type(batch) is not _ImportBatch:
        raise TypeError("batch must be an ImportBatch")
    public = _PublicImportBatch(
        **{name: getattr(batch, name) for name in _BATCH_FIELDS}
    )
    _validate_public_batch_values(public)
    return public


def internal_batch_from_public(batch) -> _ImportBatch:
    if type(batch) is not _PublicImportBatch:
        raise TypeError("batch must be a PublicImportBatch")
    try:
        _validate_public_batch_values(batch)
        candidate = _ImportBatch(**{name: getattr(batch, name) for name in _BATCH_FIELDS})
        _QCProject(_uuid4(), _CURRENT_PROJECT_SCHEMA_VERSION).commit(candidate)
    except (TypeError, ValueError, KeyError) as error:
        raise PublicBatchValidationError(str(error)) from error
    return candidate
