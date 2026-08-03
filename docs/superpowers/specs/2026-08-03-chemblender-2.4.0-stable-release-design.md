# ChemBlender 2.4.0 Stable Release Design

## 目标

在不增加功能、不修改科学模型或依赖边界的前提下，将已验证并公开的
`2.4.0-rc.1` 晋级为 Stable `2.4.0`，并保留从 RC、稳定版提交到公开 Release
的精确证据链。

## 已确认基线

- `origin/main`: `e15e46535b7af9ebae5768fa3db5c82bee43901e`。
- Annotated RC tag: `v2.4.0-rc.1`，tag object
  `472775cd4e0652ee5c0c6e9507aee8a29230acba`，peeled commit 与
  `origin/main` 相同。
- Exact-tag `extension-package`: run `30770885098`, `success`；其中
  Blender 5.1.2 validate/build/install/lifecycle Passed。
- Verification-only `extension-release`: run `30771253311`, `success`，
  `publish` job skipped。
- Published prerelease `extension-release`: run `30772029322`, `success`。
- Public RC Release:
  `https://github.com/psiQAQ/ChemBlender_2_x/releases/tag/v2.4.0-rc.1`。
- RC ZIP SHA-256:
  `cae3b9d6bc8928c866cfec079ff1b4dab816d3e4803275f679706141c92e08f4`。
- RC checksum SHA-256:
  `99edee2c2f34049e9b36735056b1a4a1fb56673a1152789bf6d1360bf5f65192`。
- Public Release body 与 tagged `CHANGELOG.md` 提取结果完全一致，公开两项
  asset 已使用 `release-assets` verifier 复验。

## Feedback Review 决策

Feedback review 以可归因的报告和已验证运行证据为准，不引入计划外的最低
下载数或等待时长。截至本设计审查：

- GitHub Issues 与 Discussions 均未启用；
- 没有开放 PR；
- 没有收到数据损坏、科学映射错误、崩溃、项目丢失/恢复失败或核心工作流
  失败报告；
- RC 已具备 exact-tag package、installed-runtime、公开资产与 Release body
  证据；
- RC 已知限制保持不变，不属于 Stable blocker。

因此可以开始独立 Stable preparation。后续若出现可复现 blocker，必须停止
晋级，并在独立修复提交中按 systematic debugging 与 TDD 处理。

## Stable 变更范围

允许修改：

- `ChemBlender/blender_manifest.toml`：仅将版本改为 `2.4.0`；
- `CHANGELOG.md`：新增 dated Stable `2.4.0` entry，更新 compare/release links，
  保留 published RC entry 不变；
- Stable production-state/readiness tests；
- RC feedback review、Stable readiness、Execution Cursor、spec 与 implementation
  plan。

禁止修改：

- runtime source、scientific model、Reader API、sidecar/project schema；
- RDKit `2026.3.3`、Gemmi `0.7.5` 或其他 dependency；
- GitHub Actions workflow、artifact budget 或 package contents；
- `v2.4.0-rc.1` tag、RC Release body 或 RC assets；
- 新格式、新 UI、新迁移或兼容层。

## Metadata 与 Release Notes

Stable metadata 必须由现有 `release_metadata.py` 单一来源得到：

- version: `2.4.0`；
- package: `chemblender-2.4.0.zip`；
- checksum: `chemblender-2.4.0.sha256`；
- artifact: `chemblender-2.4.0-windows-x64`；
- channel: `stable`；
- prerelease: `false`。

Stable CHANGELOG entry 只描述 RC 到 Stable 的晋级、最终验证和保持不变的
已知限制，不复制或改写已发布 RC entry。`CHANGELOG.md` 继续作为唯一 Release
body source。

## Tests 与证据记录

先新增 Stable production-state contract 并观察其因 `2.4.0` metadata/readiness
尚不存在而 RED。Minimal GREEN 只更新 metadata、CHANGELOG、feedback/readiness
记录及受影响的精确版本断言。

RC readiness contract 转为验证 published RC 历史快照，不再把 RC metadata 当作
当前 production state。Stable contract 验证：

- exact version/package/checksum/artifact names；
- Stable CHANGELOG entry 与 links；
- RC entry 仍存在且内容未被 Stable preparation 改写；
- feedback review 引用精确 RC tag/run/asset evidence；
- Stable readiness 记录本轮真实本地资格结果；
- production manifest byte/hash change 仅来自版本文本与既有换行规范。

## Local Qualification

从 clean committed Stable tree 运行：

1. Stable/release focused tests；
2. full `unittest` suite 与 `compileall`；
3. generated documentation contracts 与 `git diff --check`；
4. pinned dependency inventory；
5. Blender 5.1.2 native extension validate/build；
6. ZIP inventory、CRC、安全路径、size/license budget；
7. isolated install、real `user_default` lifecycle 与 product smoke；
8. `package-ci` 和 `release-assets` verifier；
9. stable manifest probe。

所有结果必须记录 Passed/Failed/Not Run；任何必需项 Failed 都停止晋级。

## Git、CI 与 Publication

使用独立 `release/2.4.0` branch 和普通提交。流程固定为：

1. push branch，创建 Ready PR 到 `main`；
2. 等待 exact PR-head `extension-package` 与 `optional-qc-core`；
3. 使用普通 merge commit；
4. 等待 exact merge-SHA 两个 workflow；
5. 创建 annotated tag `v2.4.0`，不得移动或重写；
6. 等待 exact-tag `extension-package` 与 installed-runtime evidence；
7. 运行 `extension-release` `publish=false`；
8. 运行 `extension-release` `publish=true`；
9. 下载公开 assets，复验 inventory、checksum、ZIP 与 Release body；
10. 以 post-release evidence checkpoint 记录最终 run、tag、Release 和 ancestry。

任何 run 的 `headSha`、branch/tag 或 event 不匹配时不得借用旧证据。

## Failure 与 Recovery

- 测试或 runtime 失败：停止，保留失败证据，先定位 root cause；
- PR/CI 失败：不 merge、不 tag、不 publish；新 commit 使旧 CI 证据失效；
- tag 或 asset 身份不一致：停止，不删除或移动已公开 tag；
- publication 失败：不得手工上传未经 verifier 复验的替代 asset；
- Git recovery 使用 `cherry-pick --abort` 或 `git revert`，禁止 `reset --hard`、
  rebase、force-push 和 squash merge。

## 完成标准

Stable `2.4.0` 只有在普通 merge、exact merge/tag CI、annotated tag、公开
non-prerelease Release、两项公开 asset 独立复验和 post-release evidence
checkpoint 全部完成后才算交付。完成后现场审计 `.agents/active/`、
`.agents/queued/` 与 roadmap；没有已批准的未完成计划时再关闭持续目标。
