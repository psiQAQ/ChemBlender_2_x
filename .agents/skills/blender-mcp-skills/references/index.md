# Blender MCP Plugin Development References

This directory contains modular reference docs for Blender add-on and extension development workflows used by this skill.

## Recommended reading order

1. [Template Guide](./template-guide.md)
2. [Manifest Fields](./manifest-fields.md)
3. [Dependency Policy](./dependency-policy.md)
4. [System Adaptation](./system-adaptation.md)
5. [Extension Workflow](./extension-workflow.md)
6. [Lifecycle](./lifecycle.md)
7. [Pitfalls and Fixes](./pitfalls-and-fixes.md)
8. [Migration Notes](./migration-notes.md)

## When to use which doc

- If you need to create a new add-on scaffold: start with **Template Guide**.
- If you need to edit or review `blender_manifest.toml`: check **Manifest Fields**.
- If you need third-party Python packages: check **Dependency Policy**.
- If you are about to run Blender commands or edit add-on files: read **System Adaptation** first.
- If you need iterative reload flow: use **Extension Workflow**.
- If registration/unregistration behaves unexpectedly: check **Lifecycle** and **Pitfalls and Fixes**.
- If you are converting old `bl_info` style add-ons to extension mode: check **Migration Notes**.

## Setup guide reference (raw)

Use this when `blender-mcp` command or agent-side MCP registration is missing.

Note:
- This guide is maintained by this repository (not official Blender documentation).
- It is used to install official Blender MCP components.

- Local setup (EN): `https://raw.githubusercontent.com/psiQAQ/blender_mcp-setup-guide/main/docs/blender_mcp-setup_en.md`

## Built-in template

Default local template path:

- `templates/extension_addon/`

The skill should ask users whether they want to reuse this template when they request:

- create plugin scaffolding
- create template
- create new add-on
- create extension add-on
