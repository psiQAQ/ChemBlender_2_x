from dataclasses import dataclass
from uuid import UUID


_BACKUP_COLLECTION = "ChemBlender Legacy Backup"
_BACKUP_CONTRACT = "v2"


@dataclass(frozen=True, slots=True)
class LegacyObjectDetection:
    name: str
    kind: str
    collections: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LegacySceneDetection:
    objects: tuple[LegacyObjectDetection, ...]


def detect_legacy_scene() -> LegacySceneDetection:
    import bpy

    objects = []
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        if _is_owned_backup(obj):
            continue
        if obj.get("cb_structure_contract") == "structure_view_v1":
            continue
        if obj.get("Type") == "scaffold":
            kind = "crystal" if "cell lengths" in obj else "scaffold"
        elif "cell lengths" in obj and "cell angles" in obj:
            kind = "cell"
        else:
            continue
        objects.append(
            LegacyObjectDetection(
                obj.name,
                kind,
                tuple(sorted(collection.name for collection in obj.users_collection)),
            )
        )
    return LegacySceneDetection(tuple(sorted(objects, key=lambda item: item.name)))


def _is_owned_backup(obj):
    collections = tuple(obj.users_collection)
    if len(collections) != 1 or collections[0].name != _BACKUP_COLLECTION:
        return False
    collection = collections[0]
    values = (
        collection.get("cb_legacy_migration_collection"),
        collection.get("cb_legacy_migration_project_id"),
        collection.get("cb_legacy_migration_transaction_id"),
        obj.get("cb_legacy_migration_backup"),
        obj.get("cb_legacy_migration_project_id"),
        obj.get("cb_legacy_migration_transaction_id"),
    )
    if values[0] != _BACKUP_CONTRACT or values[3] != _BACKUP_CONTRACT:
        return False
    if values[1] != values[4] or values[2] != values[5]:
        return False
    try:
        UUID(values[1])
        UUID(values[2])
    except (TypeError, ValueError):
        return False
    return True
