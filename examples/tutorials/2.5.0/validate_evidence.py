#!/usr/bin/env python3
"""Read-only consistency checker for proposed ChemBlender tutorial evidence.

Execution copy: native GUI JPEG accepted by user on 2026-09-10.
Original research checker, result schema and independent review gates remain unchanged.

This does NOT run Blender, verify scientific algorithms, or authenticate GUI
captures. An integrity_ok result is never a substitute for real execution and
independent visual/scientific review. Python 3.10+; standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
STATUSES = {"not_run", "running", "blocked", "failed", "passed"}
GUI_TYPES = {"os_gui", "human_gui"}
MAX_JSON_BYTES = 16 * 1024 * 1024
LIMITATION = ("File/record consistency only: no Blender execution, no independent "
              "proof of GUI authenticity or scientific correctness.")


def read_json(path: Path) -> Any:
    if path.is_symlink() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError(f"unsafe or oversized JSON: {path.name}")
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")
    def unique_pairs(pairs: list) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      parse_constant=reject_constant,
                      object_pairs_hook=unique_pairs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("artifact path must be a POSIX relative path")
    if sys.platform == "win32" and not hasattr(Path(), "is_junction"):
        raise ValueError("Windows junction checks require Python 3.12+")
    parts = relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(x in {"", ".", ".."} for x in parts):
        raise ValueError("artifact path must not escape its run directory")
    candidate = root
    for part in parts:
        candidate /= part
        is_junction = getattr(candidate, "is_junction", lambda: False)
        if candidate.is_symlink() or is_junction():
            raise ValueError("artifact path must not contain a link or junction")
    candidate.resolve(strict=True).relative_to(root)
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError("artifact must be a nonempty regular file")
    return candidate


def _audit(manifest_path: Path, spec_path: Path, publish: bool,
           expected_extension: str | None, expected_prepare: str | None) -> dict:
    m, spec = read_json(manifest_path), read_json(spec_path)
    if not isinstance(m, dict) or not isinstance(spec, dict):
        raise ValueError("manifest and spec must be objects")
    root = manifest_path.resolve().parent
    errors: list[str] = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)
    require(m.get("schema_version") == 1 and spec.get("schema_version") == 1,
            "unsupported schema_version")
    require(m.get("case_id") == spec.get("case_id"), "case ID differs from spec")
    require(m.get("status") in STATUSES, "invalid run status")
    require(m.get("spec_sha256") == sha256(spec_path), "spec SHA-256 mismatch")
    if m.get("status") != "passed":
        require(bool(m.get("status_reason")), "non-passed run requires a reason")
        return {"verdict": "incomplete", "case_id": m.get("case_id"),
                "errors": errors + ["run is not passed"], "limitation": LIMITATION}
    baseline = m.get("baseline", {})
    require(bool(HEX40.fullmatch(str(baseline.get("reviewed_commit", "")))),
            "reviewed_commit must be a full commit SHA")
    for key in ("extension_sha256", "prepare_sha256"):
        require(bool(HEX64.fullmatch(str(baseline.get(key, "")))), f"invalid {key}")
    for value, key in ((expected_extension, "extension_sha256"),
                       (expected_prepare, "prepare_sha256")):
        if value is not None:
            require(baseline.get(key) == value, f"expected release {key} mismatch")
    if publish:
        require(not m.get("synthetic", False), "synthetic evidence cannot be published")
        require(bool(expected_extension and expected_prepare),
                "publish check requires both independent expected artifact hashes")
    env = m.get("environment", {})
    for key in ("blender_version", "operating_system", "profile_id", "run_id"):
        value = env.get(key)
        require(isinstance(value, str) and bool(value.strip()) and
                value.strip().lower() not in {"tbd", "...", "unknown"},
                f"missing real environment field: {key}")

    items = m.get("artifacts", [])
    require(isinstance(items, list), "artifacts must be a list")
    artifacts, paths, kinds = {}, {}, {}
    for a in items:
        aid = a.get("id")
        require(isinstance(aid, str) and bool(aid) and aid not in artifacts,
                "missing or duplicate artifact ID")
        if not isinstance(aid, str) or aid in artifacts:
            continue
        artifacts[aid] = a
        kinds.setdefault(a.get("kind"), []).append(aid)
        try:
            path = safe_file(root, a.get("path"))
            require(bool(HEX64.fullmatch(str(a.get("sha256", "")))) and
                    sha256(path) == a.get("sha256"), f"artifact hash mismatch: {aid}")
            paths[aid] = path
            if a.get("kind") in {"gui_raw", "render"}:
                with path.open("rb") as stream:
                    header = stream.read(24)
                png = header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR"
                jpeg = False
                if a.get("kind") == "gui_raw" and header[:3] == b"\xff\xd8\xff":
                    with path.open("rb") as stream:
                        stream.seek(-2, 2)
                        jpeg = stream.read(2) == b"\xff\xd9"
                require((png and path.suffix.lower() == ".png") or
                        (jpeg and path.suffix.lower() in {".jpg", ".jpeg"}),
                        f"expected native GUI PNG/JPEG or render PNG: {aid}")
                require(a.get("extension_sha256") == baseline.get("extension_sha256"),
                        f"image build differs from baseline: {aid}")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"invalid artifact {aid}: {exc}")
    for kind in spec.get("required_artifact_kinds", []):
        require(bool(kinds.get(kind)), f"missing artifact kind: {kind}")

    # Event records establish consistency, not proof that a click truly occurred.
    events = {}
    for aid in kinds.get("events", []):
        if aid not in paths:
            continue
        records = read_json(paths[aid])
        require(isinstance(records, list), "events file must be a JSON array")
        for event in records:
            eid = event.get("event_id")
            require(bool(eid) and eid not in events, "missing/duplicate event ID")
            events[eid] = event
    steps = {}
    for step in m.get("steps", []):
        sid = step.get("id")
        require(bool(sid) and sid not in steps, "missing/duplicate step ID")
        steps[sid] = step
    for expected in spec.get("required_steps", []):
        sid = expected["id"]
        step = steps.get(sid, {})
        require(step.get("status") == "passed", f"step not passed: {sid}")
        event = events.get(step.get("event_id"), {})
        require(event.get("step_id") == sid, f"event not linked to step: {sid}")
        if expected.get("requires_gui"):
            require(step.get("interaction") in GUI_TYPES, f"not real GUI interaction: {sid}")
            require(event.get("interaction") == step.get("interaction"),
                    f"event/step interaction mismatch: {sid}")
            require(bool(event.get("action")) and bool(event.get("timestamp_utc")) and
                    bool(event.get("session_id")), f"incomplete GUI event: {sid}")
            ids = [step.get("before_artifact_id"), step.get("after_artifact_id")]
            require(ids[0] != ids[1], f"pre/post capture IDs must differ: {sid}")
            for field, aid in zip(("before_artifact_id", "after_artifact_id"), ids):
                require(artifacts.get(aid, {}).get("kind") == "gui_raw",
                        f"missing raw GUI capture for {sid}: {field}")
                require(event.get(field) == aid, f"capture/event mismatch for {sid}")

    checks = {}
    for check in m.get("checks", []):
        cid = check.get("id")
        require(bool(cid) and cid not in checks, "missing/duplicate check ID")
        checks[cid] = check
    for cid in spec.get("required_checks", []):
        check = checks.get(cid, {})
        require(check.get("status") == "passed", f"check not passed: {cid}")
        require(check.get("expected") is not None and check.get("observed") is not None,
                f"check lacks expected/observed values: {cid}")
        refs = check.get("artifact_ids", [])
        require(bool(refs) and all(x in paths for x in refs), f"check lacks artifacts: {cid}")

    if spec.get("requires_project_pair"):
        scenes = [paths[x] for x in kinds.get("scene_blend", []) if x in paths]
        sidecars = [paths[x] for x in kinds.get("cbq_manifest", []) if x in paths]
        require(bool(scenes) and any(p.with_suffix(".cbq") / "manifest.json" in sidecars
                                     for p in scenes), "missing adjacent .blend/.cbq pair")
        for path in sidecars:
            require(isinstance(read_json(path), dict), "CBQ manifest must be an object")
        # Actual CBQ semantics must additionally pass chemblender-prepare validate.
    if spec.get("requires_cold_reopen"):
        lifecycle_ids = kinds.get("lifecycle", [])
        require(len(lifecycle_ids) == 1, "one lifecycle report is required")
        if len(lifecycle_ids) == 1 and lifecycle_ids[0] in paths:
            life = read_json(paths[lifecycle_ids[0]])
            require(bool(life.get("saved_session_id")) and bool(life.get("reopened_session_id"))
                    and life["saved_session_id"] != life["reopened_session_id"],
                    "cold reopen must record distinct process-session identities")
            before, after = life.get("before_scientific_hashes"), life.get("after_scientific_hashes")
            require(isinstance(before, dict) and bool(before) and before == after,
                    "scientific hashes not preserved after reopen")
            if isinstance(before, dict):
                require(all(HEX64.fullmatch(str(v)) for v in before.values()),
                        "invalid scientific hash")
            require(life.get("status") == "passed", "lifecycle check not passed")
    if spec.get("requires_independent_review"):
        rids = kinds.get("review", [])
        require(len(rids) == 1, "one independent review record is required")
        if len(rids) == 1 and rids[0] in paths:
            review = read_json(paths[rids[0]])
            require(review.get("status") == "passed" and bool(review.get("reviewer")) and
                    review.get("independent") is True, "independent review is incomplete")
    return {"verdict": "invalid" if errors else "integrity_ok",
            "case_id": m.get("case_id"), "errors": errors, "limitation": LIMITATION}


def audit(manifest_path: Path, spec_path: Path, publish: bool = False,
          expected_extension: str | None = None, expected_prepare: str | None = None) -> dict:
    try:
        return _audit(manifest_path, spec_path, publish, expected_extension, expected_prepare)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"verdict": "invalid", "errors": [str(exc)], "limitation": LIMITATION}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--publish", action="store_true", help="Strict candidate consistency check; does not publish anything")
    parser.add_argument("--expected-extension-sha256")
    parser.add_argument("--expected-prepare-sha256")
    args = parser.parse_args()
    result = audit(args.manifest, args.spec, args.publish,
                   args.expected_extension_sha256, args.expected_prepare_sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"integrity_ok": 0, "invalid": 1, "incomplete": 2}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
