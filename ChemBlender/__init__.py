def register():
    from . import auto_load

    auto_load.init()
    auto_load.register()


def unregister():
    from . import auto_load

    auto_load.unregister()
