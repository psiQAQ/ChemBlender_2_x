#!/usr/bin/env python3
"""Read-only consistency checker for proposed ChemBlender tutorial evidence.

Execution copy: native GUI JPEG accepted by user on 2026-09-10. Incomplete runs
are fully audited, status dimensions are separated, and authorized MCP replay
may be supplied through an explicit execution supplement.

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
LIMITATION = ("File/record consistency only: no Blender execution, no independent proof "
              "of GUI authenticity, authorization identity, or scientific correctness.")


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
           expected_extension: str | None, expected_prepare: str | None,
           execution_supplement: Path | None) -> dict:
    m, spec = read_json(manifest_path), read_json(spec_path)
    if not isinstance(m, dict) or not isinstance(spec, dict):
        raise ValueError("manifest and spec must be objects")
    root = manifest_path.resolve().parent
    integrity_errors: list[str] = []
    technical_gaps: list[str] = []
    review_gaps: list[str] = []

    def require(bucket: list[str], condition: bool, message: str) -> None:
        if not condition:
            bucket.append(message)

    require(integrity_errors,
            m.get("schema_version") == 1 and spec.get("schema_version") == 1,
            "unsupported schema_version")
    require(integrity_errors, m.get("case_id") == spec.get("case_id"),
            "case ID differs from spec")
    valid_status = m.get("status") in STATUSES
    require(integrity_errors, valid_status, "invalid run status")
    require(integrity_errors, m.get("spec_sha256") == sha256(spec_path),
            "spec SHA-256 mismatch")
    complete_run = m.get("status") == "passed"
    if not complete_run:
        require(integrity_errors, bool(m.get("status_reason")),
                "non-passed run requires a reason")
        technical_gaps.append("run is not passed")

    baseline = m.get("baseline")
    if baseline is not None:
        require(integrity_errors, isinstance(baseline, dict), "baseline must be an object")
        baseline = baseline if isinstance(baseline, dict) else {}
        require(integrity_errors,
                bool(HEX40.fullmatch(str(baseline.get("reviewed_commit", "")))),
                "reviewed_commit must be a full commit SHA")
        for key in ("extension_sha256", "prepare_sha256"):
            require(integrity_errors,
                    bool(HEX64.fullmatch(str(baseline.get(key, "")))), f"invalid {key}")
        for value, key in ((expected_extension, "extension_sha256"),
                           (expected_prepare, "prepare_sha256")):
            if value is not None:
                require(integrity_errors, baseline.get(key) == value,
                        f"expected release {key} mismatch")
    else:
        baseline = {}
        if complete_run or expected_extension is not None or expected_prepare is not None:
            technical_gaps.append("missing release baseline")
    if publish:
        require(integrity_errors, not m.get("synthetic", False),
                "synthetic evidence cannot be published")
        require(integrity_errors, bool(expected_extension and expected_prepare),
                "publish check requires both independent expected artifact hashes")

    env = m.get("environment")
    if env is not None:
        require(integrity_errors, isinstance(env, dict), "environment must be an object")
        env = env if isinstance(env, dict) else {}
        for key in ("blender_version", "operating_system", "profile_id", "run_id"):
            value = env.get(key)
            require(integrity_errors,
                    isinstance(value, str) and bool(value.strip()) and
                    value.strip().lower() not in {"tbd", "...", "unknown"},
                    f"missing real environment field: {key}")
    elif complete_run:
        technical_gaps.append("missing environment record")

    items = m.get("artifacts", [])
    require(integrity_errors, isinstance(items, list), "artifacts must be a list")
    items = items if isinstance(items, list) else []
    artifacts, paths, kinds = {}, {}, {}
    for artifact in items:
        if not isinstance(artifact, dict):
            integrity_errors.append("artifact record must be an object")
            continue
        aid = artifact.get("id")
        require(integrity_errors,
                isinstance(aid, str) and bool(aid) and aid not in artifacts,
                "missing or duplicate artifact ID")
        if not isinstance(aid, str) or not aid or aid in artifacts:
            continue
        artifacts[aid] = artifact
        kinds.setdefault(artifact.get("kind"), []).append(aid)
        try:
            path = safe_file(root, artifact.get("path"))
            require(integrity_errors,
                    bool(HEX64.fullmatch(str(artifact.get("sha256", "")))) and
                    sha256(path) == artifact.get("sha256"),
                    f"artifact hash mismatch: {aid}")
            paths[aid] = path
            if artifact.get("kind") in {"gui_raw", "render"}:
                with path.open("rb") as stream:
                    header = stream.read(24)
                png = header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR"
                jpeg = False
                if artifact.get("kind") == "gui_raw" and header[:3] == b"\xff\xd8\xff":
                    with path.open("rb") as stream:
                        stream.seek(-2, 2)
                        jpeg = stream.read(2) == b"\xff\xd9"
                require(integrity_errors,
                        (png and path.suffix.lower() == ".png") or
                        (jpeg and path.suffix.lower() in {".jpg", ".jpeg"}),
                        f"expected native GUI PNG/JPEG or render PNG: {aid}")
                require(integrity_errors,
                        artifact.get("extension_sha256") == baseline.get("extension_sha256"),
                        f"image build differs from baseline: {aid}")
        except (OSError, ValueError, TypeError) as exc:
            integrity_errors.append(f"invalid artifact {aid}: {exc}")
    for kind in spec.get("required_artifact_kinds", []):
        require(technical_gaps, bool(kinds.get(kind)), f"missing artifact kind: {kind}")

    # Event records establish consistency, not proof that a click truly occurred.
    events = {}
    for aid in kinds.get("events", []):
        if aid not in paths:
            continue
        records = read_json(paths[aid])
        require(integrity_errors, isinstance(records, list),
                "events file must be a JSON array")
        for event in records if isinstance(records, list) else []:
            if not isinstance(event, dict):
                integrity_errors.append("event record must be an object")
                continue
            eid = event.get("event_id")
            require(integrity_errors, bool(eid) and eid not in events,
                    "missing/duplicate event ID")
            if eid and eid not in events:
                events[eid] = event

    authorized_replays = {}
    if execution_supplement is not None:
        supplement = read_json(execution_supplement)
        require(integrity_errors, isinstance(supplement, dict),
                "execution supplement must be an object")
        supplement = supplement if isinstance(supplement, dict) else {}
        require(integrity_errors, supplement.get("schema_version") == 1,
                "unsupported execution supplement schema_version")
        require(integrity_errors, supplement.get("case_id") == m.get("case_id"),
                "execution supplement case ID mismatch")
        require(integrity_errors, supplement.get("spec_sha256") == sha256(spec_path),
                "execution supplement spec SHA-256 mismatch")
        authorization = supplement.get("authorization", {})
        require(integrity_errors, isinstance(authorization, dict),
                "execution supplement authorization must be an object")
        if isinstance(authorization, dict):
            require(integrity_errors, authorization.get("approved_by") == "user",
                    "execution supplement requires user authorization")
            for key in ("approved_at", "basis"):
                require(integrity_errors,
                        isinstance(authorization.get(key), str) and
                        bool(authorization[key].strip()),
                        f"execution supplement authorization lacks {key}")
        replay_items = supplement.get("replays", [])
        require(integrity_errors, isinstance(replay_items, list) and bool(replay_items),
                "execution supplement replays must be a nonempty list")
        required_step_ids = {item.get("id") for item in spec.get("required_steps", [])}
        for replay in replay_items if isinstance(replay_items, list) else []:
            before_errors = len(integrity_errors)
            if not isinstance(replay, dict):
                integrity_errors.append("execution replay must be an object")
                continue
            sid = replay.get("step_id")
            require(integrity_errors,
                    isinstance(sid, str) and sid in required_step_ids and
                    sid not in authorized_replays,
                    "execution replay has missing, unknown, or duplicate step_id")
            require(integrity_errors,
                    replay.get("interaction") == "authorized_mcp_replay",
                    f"invalid authorized replay interaction: {sid}")
            require(integrity_errors,
                    replay.get("classification") == "replay_not_direct_gui",
                    f"authorized replay misclassified as direct GUI: {sid}")
            original = replay.get("original_gui", {})
            require(integrity_errors, isinstance(original, dict),
                    f"original GUI chain must be an object: {sid}")
            if isinstance(original, dict):
                for key in ("source_run_id", "event_id"):
                    require(integrity_errors,
                            isinstance(original.get(key), str) and bool(original[key].strip()),
                            f"original GUI chain lacks {key}: {sid}")
                for key in ("source_extension_sha256", "source_manifest_sha256",
                            "events_sha256", "before_artifact_sha256",
                            "after_artifact_sha256"):
                    require(integrity_errors,
                            bool(HEX64.fullmatch(str(original.get(key, "")))),
                            f"original GUI chain has invalid {key}: {sid}")
            difference = replay.get("candidate_difference", {})
            require(integrity_errors, isinstance(difference, dict),
                    f"candidate difference must be an object: {sid}")
            if isinstance(difference, dict):
                require(integrity_errors, difference.get("status") == "passed",
                        f"candidate difference not passed: {sid}")
                require(integrity_errors,
                        difference.get("to_extension_sha256") == baseline.get("extension_sha256") and
                        difference.get("to_prepare_sha256") == baseline.get("prepare_sha256"),
                        f"candidate difference does not match run baseline: {sid}")
                require(integrity_errors,
                        isinstance(difference.get("checked_fields"), list) and
                        bool(difference["checked_fields"]),
                        f"candidate difference lacks checked fields: {sid}")
            receipt = replay.get("operator_receipt", {})
            require(integrity_errors, isinstance(receipt, dict),
                    f"operator receipt must be an object: {sid}")
            if isinstance(receipt, dict):
                aid = receipt.get("artifact_id")
                require(integrity_errors, receipt.get("status") == "passed",
                        f"operator receipt not passed: {sid}")
                require(integrity_errors,
                        aid in paths and receipt.get("sha256") == artifacts.get(aid, {}).get("sha256"),
                        f"operator receipt is not hash-linked to this run: {sid}")
            if len(integrity_errors) == before_errors and isinstance(sid, str):
                authorized_replays[sid] = replay

    step_items = m.get("steps", [])
    require(integrity_errors, isinstance(step_items, list), "steps must be a list")
    steps = {}
    for step in step_items if isinstance(step_items, list) else []:
        if not isinstance(step, dict):
            integrity_errors.append("step record must be an object")
            continue
        sid = step.get("id")
        require(integrity_errors, bool(sid) and sid not in steps,
                "missing/duplicate step ID")
        if sid and sid not in steps:
            steps[sid] = step
    for expected in spec.get("required_steps", []):
        sid = expected["id"]
        step = steps.get(sid)
        if step is None:
            technical_gaps.append(f"step not passed: {sid}")
            continue
        replay = authorized_replays.get(sid)
        replay_passed = (replay is not None and step.get("interaction") == "mcp_replay" and
                         step.get("replay_status") == "passed")
        require(technical_gaps, step.get("status") == "passed" or replay_passed,
                f"step not passed: {sid}")
        if step.get("interaction") == "mcp_replay" and not replay_passed:
            technical_gaps.append(f"authorized replay chain missing: {sid}")
            continue
        if replay_passed:
            continue
        event = events.get(step.get("event_id"))
        require(integrity_errors, event is not None and event.get("step_id") == sid,
                f"event not linked to step: {sid}")
        if expected.get("requires_gui"):
            require(integrity_errors, step.get("interaction") in GUI_TYPES,
                    f"not real GUI interaction: {sid}")
            if event is not None:
                require(integrity_errors, event.get("interaction") == step.get("interaction"),
                        f"event/step interaction mismatch: {sid}")
                require(integrity_errors,
                        bool(event.get("action")) and bool(event.get("timestamp_utc")) and
                        bool(event.get("session_id")), f"incomplete GUI event: {sid}")
            ids = [step.get("before_artifact_id"), step.get("after_artifact_id")]
            require(integrity_errors, ids[0] != ids[1],
                    f"pre/post capture IDs must differ: {sid}")
            for field, aid in zip(("before_artifact_id", "after_artifact_id"), ids):
                require(integrity_errors, artifacts.get(aid, {}).get("kind") == "gui_raw",
                        f"missing raw GUI capture for {sid}: {field}")
                if event is not None:
                    require(integrity_errors, event.get(field) == aid,
                            f"capture/event mismatch for {sid}")

    check_items = m.get("checks", [])
    require(integrity_errors, isinstance(check_items, list), "checks must be a list")
    checks = {}
    for check in check_items if isinstance(check_items, list) else []:
        if not isinstance(check, dict):
            integrity_errors.append("check record must be an object")
            continue
        cid = check.get("id")
        require(integrity_errors, bool(cid) and cid not in checks,
                "missing/duplicate check ID")
        if cid and cid not in checks:
            checks[cid] = check
    for cid in spec.get("required_checks", []):
        check = checks.get(cid)
        if check is None:
            technical_gaps.append(f"check not passed: {cid}")
            continue
        require(technical_gaps, check.get("status") == "passed", f"check not passed: {cid}")
        require(integrity_errors,
                check.get("expected") is not None and check.get("observed") is not None,
                f"check lacks expected/observed values: {cid}")
        refs = check.get("artifact_ids", [])
        require(integrity_errors, bool(refs) and all(ref in paths for ref in refs),
                f"check lacks artifacts: {cid}")

    if spec.get("requires_project_pair"):
        scenes = [paths[aid] for aid in kinds.get("scene_blend", []) if aid in paths]
        sidecars = [paths[aid] for aid in kinds.get("cbq_manifest", []) if aid in paths]
        require(technical_gaps,
                bool(scenes) and any(scene.with_suffix(".cbq") / "manifest.json" in sidecars
                                     for scene in scenes),
                "missing adjacent .blend/.cbq pair")
        for path in sidecars:
            require(integrity_errors, isinstance(read_json(path), dict),
                    "CBQ manifest must be an object")
        # Actual CBQ semantics must additionally pass chemblender-prepare validate.
    if spec.get("requires_cold_reopen"):
        lifecycle_ids = kinds.get("lifecycle", [])
        if not lifecycle_ids:
            technical_gaps.append("one lifecycle report is required")
        elif len(lifecycle_ids) != 1:
            integrity_errors.append("one lifecycle report is required")
        elif lifecycle_ids[0] in paths:
            life = read_json(paths[lifecycle_ids[0]])
            require(integrity_errors, isinstance(life, dict),
                    "lifecycle report must be an object")
            if isinstance(life, dict):
                before = life.get("before_scientific_hashes")
                after = life.get("after_scientific_hashes")
                if before is not None or after is not None:
                    require(integrity_errors,
                            bool(life.get("saved_session_id")) and
                            bool(life.get("reopened_session_id")) and
                            life["saved_session_id"] != life["reopened_session_id"],
                            "cold reopen must record distinct process-session identities")
                    require(integrity_errors,
                            isinstance(before, dict) and bool(before) and before == after,
                            "scientific hashes not preserved after reopen")
                    if isinstance(before, dict):
                        require(integrity_errors,
                                all(HEX64.fullmatch(str(value)) for value in before.values()),
                                "invalid scientific hash")
                else:
                    runs = life.get("original_and_moved_cold_reopen")
                    require(technical_gaps,
                            isinstance(runs, list) and len(runs) >= 2 and
                            all(isinstance(run, dict) and run.get("exit_code") == 0 and
                                run.get("pid") and run.get("path") for run in runs),
                            "cold reopen process receipts are incomplete")
                    require(technical_gaps, life.get("scientific_hashes_unchanged") is True,
                            "scientific hashes not preserved after reopen")
                require(technical_gaps, life.get("status") == "passed",
                        "lifecycle check not passed")
    if spec.get("requires_independent_review"):
        review_ids = kinds.get("review", [])
        if not review_ids:
            review_gaps.append("one independent review record is required")
        elif len(review_ids) != 1:
            integrity_errors.append("one independent review record is required")
        elif review_ids[0] in paths:
            review = read_json(paths[review_ids[0]])
            require(integrity_errors, isinstance(review, dict),
                    "independent review must be an object")
            if isinstance(review, dict):
                require(review_gaps,
                        review.get("status") == "passed" and bool(review.get("reviewer")) and
                        review.get("independent") is True,
                        "independent review is incomplete")

    integrity_status = "invalid" if integrity_errors else "passed"
    technical_status = "incomplete" if technical_gaps else "passed"
    if spec.get("requires_independent_review"):
        independent_review_status = "incomplete" if review_gaps else "passed"
    else:
        independent_review_status = "not_required"
    if integrity_errors:
        acceptance_status = "invalid"
        verdict = "invalid"
    elif technical_gaps or review_gaps:
        acceptance_status = "incomplete"
        verdict = "incomplete"
    else:
        acceptance_status = "passed"
        verdict = "integrity_ok"
    return {
        "verdict": verdict,
        "case_id": m.get("case_id"),
        "errors": integrity_errors + technical_gaps + review_gaps,
        "integrity_status": integrity_status,
        "technical_status": technical_status,
        "independent_review_status": independent_review_status,
        "acceptance_status": acceptance_status,
        "limitation": LIMITATION,
    }


def audit(manifest_path: Path, spec_path: Path, publish: bool = False,
          expected_extension: str | None = None, expected_prepare: str | None = None,
          execution_supplement: Path | None = None) -> dict:
    try:
        return _audit(manifest_path, spec_path, publish, expected_extension, expected_prepare,
                      execution_supplement)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return {
            "verdict": "invalid",
            "errors": [str(exc)],
            "integrity_status": "invalid",
            "technical_status": "not_evaluated",
            "independent_review_status": "not_evaluated",
            "acceptance_status": "invalid",
            "limitation": LIMITATION,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--publish", action="store_true", help="Strict candidate consistency check; does not publish anything")
    parser.add_argument("--expected-extension-sha256")
    parser.add_argument("--expected-prepare-sha256")
    parser.add_argument("--execution-supplement", type=Path)
    args = parser.parse_args()
    result = audit(args.manifest, args.spec, args.publish,
                   args.expected_extension_sha256, args.expected_prepare_sha256,
                   args.execution_supplement)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return {"integrity_ok": 0, "invalid": 1, "incomplete": 2}[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
