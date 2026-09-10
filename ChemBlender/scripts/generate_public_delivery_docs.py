#!/usr/bin/env python3
"""Generate the public interface inventory and self-contained bilingual HTML."""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


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
            "capabilities-and-projects", "troubleshooting", "release-status", "first-aspirin", "ethanol-conformers",
        )
    ), *(
        f"docs/prepare/en/{name}.md" for name in (
            "index", "cli-and-gui", "protocol-and-reader-api", "advanced-routes",
        )
    )),
    "zh-CN": ("README.zh-CN.md", *(
        f"docs/user/zh-CN/{name}.md" for name in (
            "index", "installation", "blender-workflow",
            "capabilities-and-projects", "troubleshooting", "release-status", "first-aspirin", "ethanol-conformers",
        )
    ), *(
        f"docs/prepare/zh-CN/{name}.md" for name in (
            "index", "cli-and-gui", "protocol-and-reader-api", "advanced-routes",
        )
    )),
}


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


def _slug(value):
    return re.sub(r"[^\w\s-]", "", value.lower()).replace(" ", "-")


def _inline(value, resolve=lambda target, image: (target, None)):
    fragments = []

    def keep(markup):
        fragments.append(markup)
        return f"\x00{len(fragments)-1}\x00"

    def link(match, image=False):
        target, download = resolve(match[2], image)
        label = html.escape(match[1])
        target = html.escape(target, quote=True)
        if image:
            return keep(f'<img alt="{label}" src="{target}">')
        attribute = f' download="{html.escape(download, quote=True)}"' if download else ''
        return keep(f'<a href="{target}"{attribute}>{label}</a>')

    value = re.sub(r"`([^`]+)`", lambda m: keep('<code>' + html.escape(m[1]) + '</code>'), value)
    value = re.sub(r"!\[([^]]*)\]\(([^)]+)\)", lambda m: link(m, True), value)
    value = re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, value)
    value = re.sub(r"\*\*([^*]+)\*\*", lambda m: keep('<strong>' + html.escape(m[1]) + '</strong>'), value)
    value = html.escape(value)
    for index in reversed(range(len(fragments))):
        value = value.replace(f'\x00{index}\x00', fragments[index])
    return value


def _markdown(value, resolve=lambda target, image: (target, None), prefix=""):
    output = []
    paragraph = []
    listing = None
    code = []
    fence = False
    table = []
    headings = {}

    def flush():
        nonlocal paragraph, listing, table
        if paragraph:
            output.append("<p>" + _inline(" ".join(paragraph), resolve) + "</p>")
            paragraph = []
        if listing:
            output.append(f"</{listing}>")
            listing = None
        if table:
            rows = [[cell.strip() for cell in row.strip().strip('|').split('|')] for row in table]
            header = len(rows) > 1 and all(re.fullmatch(r':?-+:?', cell) for cell in rows[1])
            output.append('<table>')
            if header:
                output.append('<thead><tr>' + ''.join('<th scope="col">' + _inline(cell, resolve) + '</th>' for cell in rows[0]) + '</tr></thead>')
                rows = rows[2:]
            output.append('<tbody>')
            for row in rows:
                output.append('<tr>' + ''.join('<td>' + _inline(cell, resolve) + '</td>' for cell in row) + '</tr>')
            output.append('</tbody></table>')
            table = []

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
        if line.startswith('|'):
            if not table:
                flush()
            table.append(line)
            continue
        if table:
            flush()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush()
            level = min(len(heading.group(1)) + 1, 6)
            slug = _slug(heading.group(2))
            count = headings.get(slug, 0)
            headings[slug] = count + 1
            anchor = prefix + slug + (f'-{count}' if count else '')
            output.append(f'<h{level} id="{html.escape(anchor, quote=True)}">{_inline(heading.group(2), resolve)}</h{level}>')
            continue
        item = re.match(r"^\s*(-|\d+\.)\s+(.+)$", line)
        if item:
            if paragraph:
                flush()
            kind = "ul" if item.group(1) == "-" else "ol"
            if listing != kind:
                flush()
                start = f' start="{int(item.group(1)[:-1])}"' if kind == 'ol' else ''
                output.append(f"<{kind}{start}>")
                listing = kind
            output.append("<li>" + _inline(item.group(2), resolve) + "</li>")
            continue
        if not line.strip():
            flush()
        else:
            paragraph.append(line.strip())
    flush()
    return "\n".join(output)


def _offline_html(language, sources, image_hashes=None):
    title = "ChemBlender 2.5 Offline Guide" if language == "en" else "ChemBlender 2.5 离线指南"
    navigation = []
    sections = []
    image_hashes = {} if image_hashes is None else image_hashes
    locations = {(ROOT / source).resolve(): (lang, f'document-{index}')
                 for lang, paths in SOURCES.items() for index, source in enumerate(paths)}
    for index, relative in enumerate(sources):
        source = (ROOT / relative).read_text(encoding="utf-8")
        section_id = f"document-{index}"

        def resolve(target, image=False):
            parts = urlsplit(html.unescape(target))
            if parts.scheme:
                if parts.scheme not in {'https', 'http', 'mailto'}:
                    raise ValueError(f'Unsupported link scheme: {relative}: {target}')
                if image:
                    raise ValueError(f'Remote image in offline guide: {relative}: {target}')
                return target, None
            path = ((ROOT / relative).parent / unquote(parts.path)).resolve() if parts.path else (ROOT / relative).resolve()
            path.relative_to(ROOT)
            if not path.is_file():
                raise ValueError(f'Missing local resource: {relative}: {target}')
            if not image and path in locations:
                lang, document = locations[path]
                fragment = document + ('-' + unquote(parts.fragment) if parts.fragment else '')
                return ('' if lang == language else f'../{lang}/index.html') + '#' + fragment, None
            payload = path.read_bytes()
            mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.md': 'text/plain;charset=utf-8', '.json': 'application/json'}.get(path.suffix.lower(), 'application/octet-stream')
            if image:
                image_hashes[path.relative_to(ROOT).as_posix()] = hashlib.sha256(payload).hexdigest()
            # Ancillary source documents are explicit downloads, embedded in this HTML.
            return f'data:{mime};base64,' + base64.b64encode(payload).decode('ascii'), None if image else path.name

        navigation.append(f'<a href="#{section_id}">{html.escape(relative)}</a>')
        sections.append(
            f'<article id="{section_id}"><div class=path>{html.escape(relative)}</div>'
            + _markdown(source, resolve, section_id + '-') + "</article>"
        )
    return ("<!doctype html><html lang=\"" + language + "\"><meta charset=utf-8>"
            "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
            f"<title>{title}</title><style>"
            ":root{color-scheme:light dark}body{font:16px/1.6 system-ui;margin:0}"
            "header,main{max-width:1080px;margin:auto;padding:24px}header{background:#17324d;color:white}"
            "nav{display:flex;gap:8px;flex-wrap:wrap}nav a{color:#bde3ff}"
            "article{padding:24px 0;border-bottom:1px solid #8885}.path{font:13px monospace;opacity:.7}"
            "code,pre{font-family:ui-monospace,monospace}pre{padding:12px;overflow:auto;background:#8882}"
            "table{border-collapse:collapse;width:100%;display:block;overflow:auto}th,td{border:1px solid #8886;padding:8px;text-align:left}"
            "img{max-width:100%;height:auto}a{overflow-wrap:anywhere}h2,h3,h4{scroll-margin-top:16px}"
            "</style><body><header><h1>" + title + "</h1><p>Self-contained / 无远程资源</p><nav>"
            + "".join(navigation) + "</nav></header><main>" + "".join(sections)
            + "</main></body></html>\n").encode("utf-8")


class _Resources(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.ids, self.links, self.images = set(), [], []
        self.feed(content.decode('utf-8'))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        if tag == 'a':
            self.links.append(attrs.get('href', ''))
        if tag == 'img':
            self.images.append(attrs.get('src', ''))


def _resource_stats(relative, content, documents):
    parsed = _Resources(content)
    missing = []
    for url in parsed.links + parsed.images:
        parts = urlsplit(url)
        if parts.scheme in {'https', 'http', 'mailto', 'data'}:
            continue
        target = (ROOT / relative).parent / unquote(parts.path) if parts.path else ROOT / relative
        key = target.resolve().relative_to(ROOT).as_posix()
        payload = documents.get(key)
        if payload is None or parts.fragment and unquote(parts.fragment) not in _Resources(payload).ids:
            missing.append(url)
    return {'link_count': len(parsed.links), 'image_count': len(parsed.images),
            'remote_resources': sum(urlsplit(url).scheme in {'http', 'https'} for url in parsed.images),
            'external_link_count': sum(urlsplit(url).scheme in {'http', 'https'} for url in parsed.links),
            'missing_resources': len(missing), 'missing_targets': missing}


def render_documents():
    documents = {"docs/prepare/public-surface.json": _json_bytes(public_surface())}
    images = {}
    for language, sources in SOURCES.items():
        images[language] = {}
        documents[f'docs/offline/{language}/index.html'] = _offline_html(language, sources, images[language])
    for language, sources in SOURCES.items():
        relative = f'docs/offline/{language}/index.html'
        html_bytes = documents[relative]
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
            "image_sha256": images[language],
            **_resource_stats(relative, html_bytes, documents),
        }
        if manifest['missing_resources'] or manifest['remote_resources']:
            raise ValueError(f'Offline resource audit failed: {language}: {manifest["missing_targets"]}')
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
