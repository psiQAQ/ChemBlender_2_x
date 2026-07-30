from dataclasses import dataclass


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
