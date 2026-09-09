import importlib


REGISTER_MODULE_NAMES: tuple[str, ...] = (
    ".extension",
    ".trajectory_view",
    ".ui.processor",
    ".ui.processor_operations",
    ".ui.session",
    ".ui.properties",
    ".ui.cbq_import",
    ".ui.mesh_edit",
    ".ui.diagnostics",
    ".ui.topology",
    ".ui.biological",
    ".ui.grid",
    ".ui.wavefunction",
    ".ui.orbital_export",
    ".ui.scientific_view",
    ".ui.scientific_export",
    ".ui.project_browser.panel",
    ".ui.file_handlers",
    ".ui.workspace",
)

_package_root = None
_registered_classes = ()
_registered_callback_modules = ()


def _note_cleanup_failure(error, action, cleanup_error):
    error.add_note(
        f"{action} failed: {type(cleanup_error).__name__}"
    )


def _cleanup_owned_state(
    auto_load,
    registered_classes,
    callback_modules,
    failure=None,
):
    remaining_classes = []
    remaining_callbacks = []

    def cleanup(action, label, *, false_is_success=False):
        nonlocal failure
        try:
            if action() is False and not false_is_success:
                raise RuntimeError(f"{label} did not release owned state")
        except BaseException as error:
            if failure is None:
                failure = error
            else:
                _note_cleanup_failure(failure, label, error)
            return False
        return True

    for module in reversed(callback_modules):
        if not cleanup(module.unregister, f"{module.__name__}.unregister"):
            remaining_callbacks.append(module)
    for cls in reversed(registered_classes):
        if not cleanup(
            lambda cls=cls: auto_load._safe_unregister_class(cls),
            f"{cls.__name__} unregister",
            false_is_success=True,
        ):
            remaining_classes.append(cls)

    remaining_callbacks.reverse()
    remaining_classes.reverse()
    return (
        tuple(remaining_classes),
        tuple(remaining_callbacks),
        failure,
    )


def register_extension(package_root: str) -> None:
    global _package_root
    global _registered_classes
    global _registered_callback_modules

    if _package_root is not None:
        if package_root == _package_root:
            return
        raise RuntimeError("another extension package is already registered")

    auto_load = importlib.import_module(".auto_load", package_root)
    modules = tuple(
        importlib.import_module(name, package_root)
        for name in REGISTER_MODULE_NAMES
    )
    ordered_classes = tuple(
        dict.fromkeys(auto_load.get_ordered_classes_to_register(modules))
    )
    registered_classes = []
    callback_modules = []

    try:
        for cls in ordered_classes:
            if auto_load._safe_register_class(cls):
                registered_classes.append(cls)
        for module in modules:
            callback = getattr(module, "register", None)
            if callable(callback):
                callback_modules.append(module)
                callback()
    except BaseException as error:
        (
            _registered_classes,
            _registered_callback_modules,
            _,
        ) = _cleanup_owned_state(
            auto_load,
            registered_classes,
            callback_modules,
            error,
        )
        if _registered_classes or _registered_callback_modules:
            _package_root = package_root
        raise

    _package_root = package_root
    _registered_classes = tuple(registered_classes)
    _registered_callback_modules = tuple(callback_modules)


def unregister_extension() -> None:
    global _package_root
    global _registered_classes
    global _registered_callback_modules

    if _package_root is None:
        return


    package_root = _package_root
    auto_load = importlib.import_module(".auto_load", package_root)
    (
        _registered_classes,
        _registered_callback_modules,
        failure,
    ) = _cleanup_owned_state(
        auto_load,
        _registered_classes,
        _registered_callback_modules,
    )
    if not (
        _registered_classes
        or _registered_callback_modules
    ):
        _package_root = None

    if failure is not None:
        raise failure
