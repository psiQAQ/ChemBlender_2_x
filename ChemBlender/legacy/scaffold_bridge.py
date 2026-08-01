"""Map familiar legacy scaffold controls to unified project actions."""


UNIFIED_EXPORT_OPERATOR = "chemblender.export_project_entity"
UNIFIED_SCIENTIFIC_EDIT_OPERATOR = "chemblender.apply_scientific_edits"
_STRUCTURE_VIEW_CONTRACT = "structure_view_v1"


def is_unified_structure_view(obj):
    return obj is not None and obj.get("cb_structure_contract") == _STRUCTURE_VIEW_CONTRACT


def legacy_scaffold_write_blocked(obj, report):
    if not is_unified_structure_view(obj):
        return False
    report(
        {"ERROR"},
        "Unified Structure Views require Apply Scientific Edits",
    )
    return True


def route_legacy_export(invoke):
    return invoke(UNIFIED_EXPORT_OPERATOR)


def route_legacy_scientific_edit(invoke):
    return invoke(UNIFIED_SCIENTIFIC_EDIT_OPERATOR)
