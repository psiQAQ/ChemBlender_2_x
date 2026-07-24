import hashlib
from dataclasses import dataclass

from ..core.model import IssueKind, ParserIssue, ParserReport
from ..core.readers import (
    AmbiguousReaderError,
    CapabilitySupport,
    ReaderDescriptor,
    ReaderNotFoundError,
    SniffMatch,
    SniffResult,
)
from .builtin_bridge import public_batch_from_internal
from .descriptors import (
    PublicReaderDescriptor,
    ReaderAvailability,
    _probe_availability,
)
from .manifest import (
    ExecutionMode,
    ReaderManifestEntry,
    ReaderPluginManifest,
)
from .protocol import ParseRequest, ProgressEvent, ReaderPlugin, SniffRequest
from .public_model import PublicImportBatch


_BUILTIN_PLUGIN_ID = "chemblender.builtin"
_BUILTIN_PLUGIN_VERSION = "2.3.0"
_HASH_CHUNK_BYTES = 65536


def _builtin_availability(reader_id):
    from ..core.reader_catalog import _OPTIONAL_READER_DEPENDENCIES

    module = _OPTIONAL_READER_DEPENDENCIES.get(reader_id)
    if module is None:
        return ReaderAvailability(True, "built_in", "available", "")
    return _probe_availability(module, ExecutionMode.BUILT_IN)


@dataclass(frozen=True, slots=True)
class _BuiltinReaderPlugin:
    core_descriptor: ReaderDescriptor
    descriptor: PublicReaderDescriptor
    manifest: ReaderPluginManifest
    priority: int

    def sniff(self, request):
        return self.core_descriptor.sniff(request.source_path, request.prefix)

    def parse(self, request):
        return public_batch_from_internal(
            self.core_descriptor.parse(request.source_path)
        )


def _manifest_entry(descriptor):
    return ReaderManifestEntry(
        reader_id=descriptor.reader_id,
        reader_version=descriptor.reader_version,
        extensions=descriptor.extensions,
        capabilities=tuple(
            name
            for name, support in descriptor.capabilities.items()
            if support is CapabilitySupport.SUPPORTED
        ),
    )


def _builtin_manifest(descriptors):
    return ReaderPluginManifest(
        schema_version="1",
        plugin_id=_BUILTIN_PLUGIN_ID,
        plugin_version=_BUILTIN_PLUGIN_VERSION,
        chemblender_api=">=0.1,<1.0",
        execution_mode=ExecutionMode.BUILT_IN,
        license=("SPDX:GPL-3.0-or-later",),
        readers=tuple(_manifest_entry(item) for item in descriptors),
    )


def _builtin_plugin(descriptor, manifest):
    if type(descriptor) is not ReaderDescriptor:
        raise TypeError("descriptor must be a ReaderDescriptor")
    public = PublicReaderDescriptor(
        plugin_id=_BUILTIN_PLUGIN_ID,
        plugin_version=_BUILTIN_PLUGIN_VERSION,
        reader_id=descriptor.reader_id,
        reader_version=descriptor.reader_version,
        execution_mode=ExecutionMode.BUILT_IN,
        extensions=descriptor.extensions,
        capabilities=descriptor.capabilities,
        availability=_builtin_availability(descriptor.reader_id),
    )
    return _BuiltinReaderPlugin(
        descriptor,
        public,
        manifest,
        descriptor.priority,
    )


def builtin_reader_plugins():
    from ..core.reader_catalog import builtin_reader_descriptors

    descriptors = builtin_reader_descriptors()
    manifest = _builtin_manifest(descriptors)
    return tuple(_builtin_plugin(item, manifest) for item in descriptors)


def builtin_reader_plugin_registry():
    return ReaderPluginRegistry(builtin_reader_plugins())


def _failure_batch(descriptor, kind, path, message):
    return PublicImportBatch(
        report=ParserReport(
            reader_id=descriptor.reader_id,
            reader_version=descriptor.reader_version,
            created_entity_ids=(),
            parsed_capabilities=(),
            issues=(ParserIssue(kind, path, message),),
        )
    )


def _cancelled(request):
    result = request.is_cancelled()
    if type(result) is not bool:
        raise TypeError("is_cancelled must return bool")
    return result


class _SourceCancelled(Exception):
    pass


class _SourceReadError(Exception):
    def __init__(self, error):
        self.error_type = type(error).__name__
        super().__init__(self.error_type)


def _source_hash(request, stage):
    request.progress(ProgressEvent(stage, 0, 1))
    if _cancelled(request):
        raise _SourceCancelled
    digest = hashlib.sha256()
    try:
        stream = request.source_path.open("rb")
    except OSError as error:
        raise _SourceReadError(error) from error
    try:
        while True:
            try:
                chunk = stream.read(_HASH_CHUNK_BYTES)
            except OSError as error:
                raise _SourceReadError(error) from error
            if not chunk:
                break
            digest.update(chunk)
            if _cancelled(request):
                raise _SourceCancelled
    finally:
        try:
            stream.close()
        except OSError as error:
            raise _SourceReadError(error) from error
    request.progress(ProgressEvent(stage, 1, 1))
    return digest.hexdigest()


def _cancelled_batch(descriptor):
    return _failure_batch(
        descriptor,
        IssueKind.WARNING,
        "reader.parse",
        "reader parse cancelled",
    )


def _validate_plugin(plugin):
    if not isinstance(plugin, ReaderPlugin):
        raise TypeError("plugin must implement ReaderPlugin")
    if type(plugin.manifest) is not ReaderPluginManifest:
        raise TypeError("plugin manifest must be ReaderPluginManifest")
    if type(plugin.descriptor) is not PublicReaderDescriptor:
        raise TypeError("plugin descriptor must be PublicReaderDescriptor")
    if type(plugin.priority) is not int:
        raise TypeError("plugin priority must be an integer")

    manifest = plugin.manifest
    descriptor = plugin.descriptor
    if (
        manifest.plugin_id != descriptor.plugin_id
        or manifest.plugin_version != descriptor.plugin_version
        or manifest.execution_mode is not descriptor.execution_mode
    ):
        raise ValueError("plugin manifest metadata does not match descriptor")
    entries = tuple(
        entry
        for entry in manifest.readers
        if entry.reader_id == descriptor.reader_id
    )
    if len(entries) != 1:
        raise ValueError("plugin manifest must contain the reader descriptor")
    entry = entries[0]
    supported = tuple(
        sorted(
            name
            for name, support in descriptor.capabilities.items()
            if support is CapabilitySupport.SUPPORTED
        )
    )
    if (
        entry.reader_version != descriptor.reader_version
        or entry.extensions != descriptor.extensions
        or entry.capabilities != supported
    ):
        raise ValueError("plugin manifest reader entry does not match descriptor")


class ReaderPluginRegistry:
    def __init__(self, plugins=()):
        self._plugins = {}
        self._plugin_manifests = {}
        self._last_sniff_diagnostics = ()
        for plugin in plugins:
            self.register(plugin)

    @property
    def descriptors(self):
        return tuple(
            self._plugins[reader_id].descriptor
            for reader_id in sorted(self._plugins)
        )

    @property
    def last_sniff_diagnostics(self):
        return self._last_sniff_diagnostics

    def register(self, plugin):
        _validate_plugin(plugin)
        plugin_id = plugin.descriptor.plugin_id
        existing_manifest = self._plugin_manifests.get(plugin_id)
        if (
            existing_manifest is not None
            and plugin.manifest != existing_manifest
        ):
            raise ValueError("plugin_id must use one complete manifest")
        reader_id = plugin.descriptor.reader_id
        if reader_id in self._plugins:
            raise ValueError(f"duplicate reader_id: {reader_id}")
        self._plugins[reader_id] = plugin
        self._plugin_manifests[plugin_id] = plugin.manifest

    def unregister(self, manifest):
        if type(manifest) is not ReaderPluginManifest:
            raise TypeError("manifest must be a ReaderPluginManifest")
        existing = self._plugin_manifests.get(manifest.plugin_id)
        if existing is None:
            raise KeyError(manifest.plugin_id)
        if existing != manifest:
            raise ValueError("manifest does not match registered plugin")
        reader_ids = tuple(
            reader_id
            for reader_id, plugin in self._plugins.items()
            if plugin.descriptor.plugin_id == manifest.plugin_id
        )
        for reader_id in reader_ids:
            del self._plugins[reader_id]
        del self._plugin_manifests[manifest.plugin_id]

    def select(self, request, reader_id=None):
        if type(request) is not SniffRequest:
            raise TypeError("request must be a SniffRequest")
        self._last_sniff_diagnostics = ()
        if reader_id is not None:
            return self._plugin(reader_id).descriptor
        if not self._plugins:
            raise ReaderNotFoundError(str(request.source_path))

        suffix = request.source_path.suffix.lower()
        plugins = sorted(
            self._plugins.values(),
            key=lambda plugin: (
                suffix not in plugin.descriptor.extensions,
                plugin.descriptor.reader_id,
            ),
        )
        matches = []
        diagnostics = []
        for plugin in plugins:
            try:
                result = plugin.sniff(request)
                if type(result) is not SniffResult:
                    raise TypeError("sniff must return SniffResult")
            except Exception as error:
                diagnostics.append(
                    ParserIssue(
                        IssueKind.WARNING,
                        "reader.sniff",
                        (
                            f"{plugin.descriptor.reader_id} sniff failed: "
                            f"{type(error).__name__}"
                        ),
                    )
                )
                continue
            if result.match > SniffMatch.NONE:
                matches.append((result, plugin))
        self._last_sniff_diagnostics = tuple(diagnostics)
        if not matches:
            raise ReaderNotFoundError(str(request.source_path))

        best_match = max(result.match for result, _ in matches)
        matches = [
            (result, plugin)
            for result, plugin in matches
            if result.match == best_match
        ]
        best_priority = max(plugin.priority for _, plugin in matches)
        winners = [
            plugin for _, plugin in matches if plugin.priority == best_priority
        ]
        if len(winners) != 1:
            raise AmbiguousReaderError(
                sorted(plugin.descriptor.reader_id for plugin in winners)
            )
        return winners[0].descriptor

    def parse(self, reader_id, request):
        if type(request) is not ParseRequest:
            raise TypeError("request must be a ParseRequest")
        plugin = self._plugin(reader_id)
        descriptor = plugin.descriptor
        availability = descriptor.availability
        if not availability.available:
            detail = f": {availability.detail}" if availability.detail else ""
            return _failure_batch(
                descriptor,
                IssueKind.UNSUPPORTED,
                "reader.availability",
                f"{availability.reason_code}{detail}",
            )
        try:
            actual_hash = _source_hash(request, "source_hash")
        except _SourceCancelled:
            return _cancelled_batch(descriptor)
        except _SourceReadError as error:
            return _failure_batch(
                descriptor,
                IssueKind.INVALID,
                "reader.source",
                f"source verification failed: {error.error_type}",
            )
        if actual_hash != request.source_content_hash:
            return _failure_batch(
                descriptor,
                IssueKind.INVALID,
                "reader.source",
                "source content hash mismatch",
            )
        request.progress(ProgressEvent("parse", 0, 1))
        try:
            result = plugin.parse(request)
            if type(result) is not PublicImportBatch:
                raise TypeError("parse must return PublicImportBatch")
        except Exception as error:
            request.progress(ProgressEvent("parse", 1, 1))
            return _failure_batch(
                descriptor,
                IssueKind.INVALID,
                "reader.parse",
                f"reader parse failed: {type(error).__name__}",
            )
        try:
            current_hash = _source_hash(request, "source_recheck")
        except _SourceCancelled:
            return _cancelled_batch(descriptor)
        except _SourceReadError as error:
            return _failure_batch(
                descriptor,
                IssueKind.INVALID,
                "reader.source",
                f"source recheck failed: {error.error_type}",
            )
        if current_hash != request.source_content_hash:
            return _failure_batch(
                descriptor,
                IssueKind.INVALID,
                "reader.source",
                "source content changed during parse",
            )
        request.progress(ProgressEvent("parse", 1, 1))
        return result

    def _plugin(self, reader_id):
        if type(reader_id) is not str:
            raise TypeError("reader_id must be a string")
        try:
            return self._plugins[reader_id]
        except KeyError as error:
            raise ReaderNotFoundError(reader_id) from error
