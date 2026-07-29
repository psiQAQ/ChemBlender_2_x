import importlib


REGISTER_MODULE_NAMES: tuple[str, ...] = (
    ".chem_utils",
    ".crys_utils",
    ".extension",
    ".output",
    ".panel",
    ".periodictable",
    ".read",
    ".scaffold",
    ".trajectory_view",
    ".ui.session",
    ".ui.properties",
    ".ui.quick_import",
    ".ui.import_preview",
    ".ui.topology",
    ".ui.biological",
    ".ui.scientific_edit",
    ".ui.export",
    ".ui.grid",
    ".ui.project_browser.panel",
    ".ui.file_handlers",
    ".ui.workspace",
)

_package_root = None
_registered_classes = ()
_registered_callback_modules = ()
_reader_api_handle = None


def _reader_api_load_post_handler(_dummy):
    global _reader_api_handle

    if _package_root is None:
        return
    bridge = importlib.import_module(
        ".runtime.reader_api_bridge",
        _package_root,
    )
    _reader_api_handle = bridge.register_reader_api_handle(_package_root)


def _reader_api_load_handler_list():
    try:
        import bpy
    except ModuleNotFoundError:
        return None
    return bpy.app.handlers.load_post


def _register_reader_api_load_handler():
    handlers = _reader_api_load_handler_list()
    if handlers is None:
        return
    import bpy

    bpy.app.handlers.persistent(_reader_api_load_post_handler)
    while _reader_api_load_post_handler in handlers:
        handlers.remove(_reader_api_load_post_handler)
    handlers.append(_reader_api_load_post_handler)


def _remove_reader_api_load_handler():
    handlers = _reader_api_load_handler_list()
    if handlers is not None:
        while _reader_api_load_post_handler in handlers:
            handlers.remove(_reader_api_load_post_handler)


def _note_cleanup_failure(error, action, cleanup_error):
    error.add_note(
        f"{action} failed: {type(cleanup_error).__name__}"
    )


def _cleanup_owned_state(
    auto_load,
    bridge,
    registered_classes,
    callback_modules,
    handle,
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

    remaining_handle = handle
    if handle is not None and cleanup(
        lambda: bridge.remove_reader_api_handle(handle),
        "reader API handle removal",
    ):
        remaining_handle = None
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
        remaining_handle,
        failure,
    )


def register_extension(package_root: str) -> None:
    global _package_root
    global _registered_classes
    global _registered_callback_modules
    global _reader_api_handle

    if _package_root is not None:
        if package_root == _package_root:
            return
        raise RuntimeError("another extension package is already registered")

    auto_load = importlib.import_module(".auto_load", package_root)
    bridge = importlib.import_module(
        ".runtime.reader_api_bridge",
        package_root,
    )
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
        handle = bridge.register_reader_api_handle(package_root)
        _register_reader_api_load_handler()
    except BaseException as error:
        _remove_reader_api_load_handler()
        (
            _registered_classes,
            _registered_callback_modules,
            _reader_api_handle,
            _,
        ) = _cleanup_owned_state(
            auto_load,
            bridge,
            registered_classes,
            callback_modules,
            None,
            error,
        )
        if _registered_classes or _registered_callback_modules:
            _package_root = package_root
        raise

    _package_root = package_root
    _registered_classes = tuple(registered_classes)
    _registered_callback_modules = tuple(callback_modules)
    _reader_api_handle = handle


def unregister_extension() -> None:
    global _package_root
    global _registered_classes
    global _registered_callback_modules
    global _reader_api_handle

    if _package_root is None:
        return

    _remove_reader_api_load_handler()

    package_root = _package_root
    auto_load = importlib.import_module(".auto_load", package_root)
    bridge = importlib.import_module(
        ".runtime.reader_api_bridge",
        package_root,
    )
    (
        _registered_classes,
        _registered_callback_modules,
        _reader_api_handle,
        failure,
    ) = _cleanup_owned_state(
        auto_load,
        bridge,
        _registered_classes,
        _registered_callback_modules,
        _reader_api_handle,
    )
    if not (
        _registered_classes
        or _registered_callback_modules
        or _reader_api_handle is not None
    ):
        _package_root = None

    if failure is not None:
        raise failure
