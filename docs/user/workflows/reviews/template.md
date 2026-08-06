# ChemBlender <version> 人工插件使用体验检阅

从本文件复制到 `reviews/<version>.md` 后再填写。未实际执行的字段保持 `Incomplete`，不得预填 Passed。

## Environment

- Date/time and timezone:
- Reviewer:
- Windows version:
- Blender version:
- Blender executable:
- Bundled Python:
- Runtime system:
- Extension repository:
- Enabled key (`bl_ext.user_default.chemblender`):
- Test profile / `BLENDER_USER_RESOURCES`:
- Active file and initial dirty state:
- Display scale, language and viewport size:

## Source and package

- Version:
- Branch:
- Git commit:
- Package filename:
- Package SHA-256:
- Manifest version:
- RDKit version/origin:
- Gemmi version/origin:
- Sample manifest SHA-256:
- Runner report path and SHA-256:

## Required case summary

Result values: `Passed` / `Failed` / `Blocked` / `Incomplete`.

| Case | Required | Workflow | UI result | Agent/MCP result | Duration | Evidence | Findings | Fix commit | Rerun result |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ENV | Yes | Environment / install | Incomplete | Incomplete |  |  |  |  |  |
| IMP | Yes | Import / Preview / cancel | Incomplete | Incomplete |  |  |  |  |  |
| DATA | Yes | Process / revision validity | Incomplete | Incomplete |  |  |  |  |  |
| VIEW | Yes | Structure / Grid / playback | Incomplete | Incomplete |  |  |  |  |  |
| EXP | Yes | Export / loss / re-import | Incomplete | Incomplete |  |  |  |  |  |
| LIFE | Yes | Save / cold reopen / recovery | Incomplete | Incomplete |  |  |  |  |  |
| MIG | Yes | Legacy preview / migration / reopen | Incomplete | Incomplete |  |  |  |  |  |
| AGENT | Yes | Public Operator / MCP / crash recovery | Incomplete | Incomplete |  |  |  |  |  |
| OUTSIDE | Yes, scope only | Generic Blender cases stay outside product scope | Incomplete | Incomplete |  |  |  |  |  |

## Case evidence

为每个 case 复制一份本节。人工 UI 与 Agent/MCP 要分开记录；runner 只能作为附件。

### <CASE>: <title>

- Preconditions:
- Input/source:
- UI steps:
- UI result:
- Agent/MCP prompt and steps:
- Agent/MCP result:
- Expected visible state:
- Actual visible state:
- Duration:
- Evidence:
- Findings:
- Severity: Blocker / Major / Minor / Suggestion / None
- Scientific/data risk:
- Workaround:
- Fix commit:
- Rerun result:
- Final case result: Passed / Failed / Blocked / Incomplete

## Saved and exported files

只记录有独立教学或复核价值的代表性文件。临时导出可在 case 证据中引用，不必提交。

| Path | Role | File size | File SHA-256 | Reopen state | External references | Notes |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  | Incomplete |  |  |

对 `.blend`/`.cbq` 配对补充：

- Project UUID / link state:
- Sidecar manifest hash:
- Cold reopen Blender version/executable:
- Key entities and View bindings after reopen:
- Missing/rebuilt cache evidence:
- Largest single file and size:
- Any file above 50 MiB and reason:
- Confirm no file exceeds 100 MiB:

## Final review

- Required cases Passed:
- Required cases Failed:
- Required cases Blocked:
- Required cases Incomplete:
- Open findings:
- Deferred external cases requiring approval:
- Final result: Passed / Failed / Blocked
- Reviewer sign-off and time:

`Incomplete`、`Failed` 或 `Blocked` 的 required case 阻止 tag/Release。自动 runner 全绿也不能覆盖人工失败。

门禁规则见 [README.md](README.md)，完整操作见[工作流中心](../README.md)。
