#!/usr/bin/env python3
"""Generate the public interface inventory and self-contained bilingual HTML."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cbq_core.worker_protocol import PROTOCOL_VERSION, WORKER_VERSION
from chemblender_prepare.cli import build_parser
from chemblender_prepare.core.reader_catalog import reader_capability_document
from chemblender_prepare.gui import COMMANDS
from chemblender_prepare.reader_api import READER_API_VERSION
from chemblender_prepare.worker.runner import default_registry


SOURCES = {
    "en": ("README.md", *(
        f"docs/user/en/{name}.md" for name in (
            "index", "installation", "blender-workflow",
            "capabilities-and-projects", "troubleshooting", "release-status",
        )
    ), *(
        f"docs/prepare/en/{name}.md" for name in (
            "index", "cli-and-gui", "protocol-and-reader-api", "advanced-routes",
        )
    )),
    "zh-CN": ("README.zh-CN.md", *(
        f"docs/user/zh-CN/{name}.md" for name in (
            "index", "installation", "blender-workflow",
            "capabilities-and-projects", "troubleshooting", "release-status",
        )
    ), *(
        f"docs/prepare/zh-CN/{name}.md" for name in (
            "index", "cli-and-gui", "protocol-and-reader-api", "advanced-routes",
        )
    )),
}
SCREENSHOTS = ("docs/user/assets/2.5.0/blender-viewer.png",)


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def public_surface():
    parser = build_parser()
    subparsers = next(action for action in parser._actions
                      if action.__class__.__name__ == "_SubParsersAction")
    export_parser = subparsers.choices["export"]
    formats = next(action.choices for action in export_parser._actions
                   if action.dest == "format")
    readers = reader_capability_document()["readers"]
    return {
        "schema_name": "chemblender_public_surface",
        "schema_version": 1,
        "prepare_version": WORKER_VERSION,
        "worker_protocol_version": PROTOCOL_VERSION,
        "reader_api_version": READER_API_VERSION,
        "cli_commands": sorted(subparsers.choices),
        "gui_commands": list(COMMANDS),
        "operations": [
            {"operation_id": operation_id, "operation_version": version}
            for operation_id, version in sorted(default_registry()._operations)
        ],
        "readers": [
            {"reader_id": item["reader_id"],
             "reader_version": item["reader_version"]}
            for item in readers
        ],
        "export_formats": list(formats),
        "python_sdk": False,
    }


def _inline(value):
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    return re.sub(r"\[([^]]+)\]\(([^)]+)\)", r"\1 <small>(\2)</small>", value)


def _markdown(value):
    output = []
    paragraph = []
    listing = None
    code = []
    fence = False

    def flush():
        nonlocal paragraph, listing
        if paragraph:
            output.append("<p>" + _inline(" ".join(paragraph)) + "</p>")
            paragraph = []
        if listing:
            output.append(f"</{listing}>")
            listing = None

    for line in value.splitlines():
        if line.startswith("```"):
            if fence:
                output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = []
                fence = False
            else:
                flush()
                fence = True
            continue
        if fence:
            code.append(line)
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush()
            level = min(len(heading.group(1)) + 1, 6)
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        item = re.match(r"^\s*(-|\d+\.)\s+(.+)$", line)
        if item:
            paragraph = []
            kind = "ul" if item.group(1) == "-" else "ol"
            if listing != kind:
                flush()
                output.append(f"<{kind}>")
                listing = kind
            output.append("<li>" + _inline(item.group(2)) + "</li>")
            continue
        if not line.strip():
            flush()
        elif line.startswith("|"):
            flush()
            output.append("<pre class=table>" + html.escape(line) + "</pre>")
        else:
            paragraph.append(line.strip())
    flush()
    return "\n".join(output)


def _offline_html(language, sources):
    title = "ChemBlender 2.5 Offline Guide" if language == "en" else "ChemBlender 2.5 离线指南"
    navigation = []
    sections = []
    for index, relative in enumerate(sources):
        source = (ROOT / relative).read_text(encoding="utf-8")
        section_id = f"document-{index}"
        navigation.append(f'<a href="#{section_id}">{html.escape(relative)}</a>')
        sections.append(
            f'<article id="{section_id}"><div class=path>{html.escape(relative)}</div>'
            + _markdown(source) + "</article>"
        )
    figures = []
    for relative in SCREENSHOTS:
        encoded = base64.b64encode((ROOT / relative).read_bytes()).decode("ascii")
        figures.append('<figure><img alt="ChemBlender 2.5.0 Viewer" '
                       f'src="data:image/png;base64,{encoded}">'
                       f'<figcaption>{html.escape(relative)}</figcaption></figure>')
    return ("<!doctype html><html lang=\"" + language + "\"><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>"
            ":root{color-scheme:light dark}body{font:16px/1.6 system-ui;margin:0}"
            "header,main{max-width:1080px;margin:auto;padding:24px}header{background:#17324d;color:white}"
            "nav{display:flex;gap:8px;flex-wrap:wrap}nav a{color:#bde3ff}"
            "article{padding:24px 0;border-bottom:1px solid #8885}.path{font:13px monospace;opacity:.7}"
            "code,pre{font-family:ui-monospace,monospace}pre{padding:12px;overflow:auto;background:#8882}"
            "pre.table{margin:0;padding:2px 8px}small{opacity:.7}img{max-width:100%;height:auto}"
            "</style><body><header><h1>" + title + "</h1><p>Self-contained / 无远程资源</p><nav>"
            + "".join(navigation) + "</nav></header><main>" + "".join(figures) + "".join(sections)
            + "</main></body></html>\n").encode("utf-8")


def render_documents():
    documents = {"docs/prepare/public-surface.json": _json_bytes(public_surface())}
    for language, sources in SOURCES.items():
        html_bytes = _offline_html(language, sources)
        manifest = {
            "schema_name": "chemblender_offline_sop",
            "schema_version": 1,
            "language": language,
            "html": "index.html",
            "html_sha256": hashlib.sha256(html_bytes).hexdigest(),
            "source_sha256": {
                relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                for relative in sources
            },
            "image_sha256": {
                relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
                for relative in SCREENSHOTS
            },
            "link_count": html_bytes.count(b"href="),
            "image_count": len(SCREENSHOTS),
            "remote_resources": 0,
            "missing_resources": 0,
        }
        documents[f"docs/offline/{language}/index.html"] = html_bytes
        documents[f"docs/offline/{language}/manifest.json"] = _json_bytes(manifest)
    return documents


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    documents = render_documents()
    stale = [relative for relative, content in documents.items()
             if not (ROOT / relative).is_file() or (ROOT / relative).read_bytes() != content]
    if args.check:
        if stale:
            print("ERROR: stale public delivery docs: " + ", ".join(stale))
            return 1
    else:
        for relative, content in documents.items():
            path = ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    print("OK: public delivery docs are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
