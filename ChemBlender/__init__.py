def register():
    from .runtime.registration import register_extension

    register_extension(__package__)


def unregister():
    from .runtime.registration import unregister_extension

    unregister_extension()
