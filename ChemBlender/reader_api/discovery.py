from dataclasses import dataclass

from ..core.readers import ReaderAvailability
from .manifest import ExecutionMode, ReaderPluginManifest
from .registry import ReaderPluginRegistry


@dataclass(frozen=True, slots=True)
class DiscoveredReaderPlugin:
    plugin_id: str
    plugin_version: str
    reader_ids: tuple[str, ...]
    availability: ReaderAvailability


@dataclass(frozen=True, slots=True)
class ReaderDiscoverySnapshot:
    generation: int
    plugins: tuple[DiscoveredReaderPlugin, ...]
    descriptors: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _FailedRegistration:
    manifest: object
    state: DiscoveredReaderPlugin


def _safe_attribute(value, name, default=None):
    try:
        return getattr(value, name)
    except MemoryError:
        raise
    except Exception:
        return default


def _failure_state_from_values(manifest, descriptor, error, reason_code):
    plugin_id = _safe_attribute(descriptor, "plugin_id")
    if type(plugin_id) is not str or not plugin_id:
        plugin_id = _safe_attribute(manifest, "plugin_id", "unknown")
    plugin_version = _safe_attribute(descriptor, "plugin_version")
    if type(plugin_version) is not str or not plugin_version:
        plugin_version = _safe_attribute(
            manifest,
            "plugin_version",
            "0",
        )
    readers = _safe_attribute(manifest, "readers", ())
    try:
        readers = tuple(readers)
    except MemoryError:
        raise
    except Exception:
        readers = ()
    reader_ids = tuple(
        sorted(
            {
                reader_id
                for entry in readers
                if type(
                    reader_id := _safe_attribute(entry, "reader_id")
                )
                is str
                and reader_id
            }
        )
    )
    if not reader_ids:
        reader_id = _safe_attribute(descriptor, "reader_id")
        if type(reader_id) is str and reader_id:
            reader_ids = (reader_id,)
    mode = _safe_attribute(descriptor, "execution_mode")
    if not isinstance(mode, ExecutionMode):
        mode = _safe_attribute(manifest, "execution_mode")
    if not isinstance(mode, ExecutionMode):
        mode = ExecutionMode.EXTENSION
    return DiscoveredReaderPlugin(
        plugin_id if type(plugin_id) is str and plugin_id else "unknown",
        (
            plugin_version
            if type(plugin_version) is str and plugin_version
            else "0"
        ),
        reader_ids,
        ReaderAvailability(
            False,
            mode.value,
            reason_code,
            type(error).__name__,
        ),
    )


def _failure_state(plugin, error, reason_code):
    return _failure_state_from_values(
        _safe_attribute(plugin, "manifest"),
        _safe_attribute(plugin, "descriptor"),
        error,
        reason_code,
    )


class ReaderPluginDiscovery:
    def __init__(self, registry):
        if type(registry) is not ReaderPluginRegistry:
            raise TypeError("registry must be a ReaderPluginRegistry")
        self._registry = registry
        self._registered_manifests = []
        self._failed_registrations = []
        self._unregistration_failures = []
        self._generation = 0
        self._snapshot = None

    def _invalidate(self):
        self._generation += 1
        self._snapshot = None

    def register(self, plugin):
        manifest = _safe_attribute(plugin, "manifest")
        try:
            self._registry.register(plugin)
        except MemoryError:
            raise
        except Exception as error:
            state = _failure_state(
                plugin,
                error,
                "plugin_registration_failed",
            )
            self._failed_registrations.append(
                _FailedRegistration(manifest, state)
            )
            self._invalidate()
            return state
        self._registered_manifests.append(manifest)
        self._invalidate()
        descriptor = plugin.descriptor
        return DiscoveredReaderPlugin(
            descriptor.plugin_id,
            descriptor.plugin_version,
            (descriptor.reader_id,),
            ReaderAvailability(
                True,
                descriptor.execution_mode.value,
                "available",
                "",
            ),
        )

    def unregister(self, manifest):
        failed_count = len(self._failed_registrations)
        self._failed_registrations = [
            failed
            for failed in self._failed_registrations
            if failed.manifest is not manifest
        ]
        if len(self._failed_registrations) != failed_count:
            self._invalidate()
            return True
        if any(
            registered is manifest
            for registered in self._registered_manifests
        ):
            try:
                self._registry.unregister(manifest)
            except MemoryError:
                raise
            except Exception as error:
                state = _failure_state_from_values(
                    manifest,
                    None,
                    error,
                    "plugin_unregistration_failed",
                )
                self._unregistration_failures = [
                    failure
                    for failure in self._unregistration_failures
                    if failure.manifest is not manifest
                ]
                self._unregistration_failures.append(
                    _FailedRegistration(manifest, state)
                )
                self._invalidate()
                return state
            self._unregistration_failures = [
                failure
                for failure in self._unregistration_failures
                if failure.manifest is not manifest
            ]
            self._registered_manifests = [
                registered
                for registered in self._registered_manifests
                if registered is not manifest
            ]
            self._invalidate()
            return True
        state = _failure_state_from_values(
            manifest,
            None,
            KeyError("plugin registration is not owned"),
            "plugin_unregistration_failed",
        )
        self._unregistration_failures.append(
            _FailedRegistration(manifest, state)
        )
        self._invalidate()
        return state

    def refresh(self):
        if self._snapshot is not None:
            return self._snapshot
        descriptors = self._registry.descriptors
        groups = {}
        for descriptor in descriptors:
            key = (
                descriptor.plugin_id,
                descriptor.plugin_version,
                descriptor.execution_mode,
            )
            groups.setdefault(key, []).append(descriptor.reader_id)
        plugins = [
            DiscoveredReaderPlugin(
                plugin_id,
                plugin_version,
                tuple(sorted(reader_ids)),
                ReaderAvailability(
                    True,
                    execution_mode.value,
                    "available",
                    "",
                ),
            )
            for (
                plugin_id,
                plugin_version,
                execution_mode,
            ), reader_ids in groups.items()
        ]
        plugins.extend(
            failure.state for failure in self._failed_registrations
        )
        plugins.extend(
            failure.state for failure in self._unregistration_failures
        )
        plugins.sort(
            key=lambda state: (
                state.plugin_id,
                state.plugin_version,
                not state.availability.available,
                state.reader_ids,
                state.availability.reason_code,
            )
        )
        self._snapshot = ReaderDiscoverySnapshot(
            self._generation,
            tuple(plugins),
            descriptors,
        )
        return self._snapshot
