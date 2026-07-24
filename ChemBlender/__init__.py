_reader_api_handle = None


def register():
    global _reader_api_handle

    from . import auto_load

    auto_load.init()
    try:
        auto_load.register()
        from .runtime.reader_api_bridge import register_reader_api_handle

        _reader_api_handle = register_reader_api_handle(__package__)
    except Exception as publication_error:
        _reader_api_handle = None
        try:
            auto_load.unregister()
        except Exception as cleanup_error:
            publication_error.add_note(
                "registration rollback failed: "
                f"{type(cleanup_error).__name__}"
            )
        raise


def unregister():
    global _reader_api_handle

    from . import auto_load

    try:
        if _reader_api_handle is not None:
            from .runtime.reader_api_bridge import remove_reader_api_handle

            remove_reader_api_handle(_reader_api_handle)
    finally:
        _reader_api_handle = None
        auto_load.unregister()
