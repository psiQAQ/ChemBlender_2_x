# blender_manifest.toml Field Reference (Extension docs aligned, 4.2+ workflow)

This reference summarizes `blender_manifest.toml` fields based on `docs/extensions-getting_started.md` (official Blender manual excerpt).

## Required fields

| Field | Meaning | Notes |
| --- | --- | --- |
| `schema_version` | Manifest schema version | Use `"1.0.0"` |
| `id` | Unique extension identifier | Lowercase snake-style ID is recommended |
| `version` | Extension version | Must follow semantic versioning |
| `name` | Display name | Full extension name |
| `tagline` | One-line short description | Max 64 chars, no trailing punctuation |
| `maintainer` | Maintainer name | Extension owner/maintainer |
| `type` | Extension type | `"add-on"` or `"theme"` |
| `blender_version_min` | Minimum Blender version | Must be `>= 4.2.0` |
| `license` | SPDX license list | Use `"SPDX:..."` values |

## Optional fields

| Field | Meaning |
| --- | --- |
| `blender_version_max` | Upper excluded Blender version (older versions still supported) |
| `website` | Documentation/support/source URL |
| `copyright` | Copyright lines required by some licenses |
| `tags` | Extension tags |
| `platforms` | Supported platforms (`windows-x64`, `windows-arm64`, `macos-x64`, `macos-arm64`, `linux-x64`) |
| `wheels` | Relative paths to bundled Python wheels |
| `[permissions]` | Required resources and reason strings (`files`, `network`, `clipboard`, `camera`, `microphone`) |

## Optional build table

`[build]` fields are for `extension build` behavior:

| Field | Meaning | Constraint |
| --- | --- | --- |
| `paths` | Explicit include file list | Relative to manifest |
| `paths_exclude_pattern` | Exclude pattern list | Gitignore-compatible patterns; do not declare with `paths` together |

If `[build]` is omitted, Blender uses default excludes.

## Reserved/internal

Do not declare internal values such as:

- `[build.generated]`

## Practical notes

- Do not keep empty placeholders (`""`, `[]`) for optional fields; omit them instead.
- Keep wheel paths inside extension root.
- For network features, verify `bpy.app.online_access` at runtime.
