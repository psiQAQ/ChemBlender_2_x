# 2.3 开发与 Release 门

本文面向 2.3.x 维护者，说明从功能分支到可发布证据的最短受控路径。完整 GitHub
步骤以 [Branch and Release Workflow](branch-and-release.md) 为准；本页不授予任何
远端操作。

## 本地开发 checkpoint

每个逻辑任务先在 feature/release branch 完成 RED、实现、focused tests、独立审查
和 clean checkpoint。不要在未通过的 task 上修改版本、CHANGELOG、tag 或 artifact
budget。Reader/依赖文档必须保持可再生：

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
$blenderBin = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'

$metadata = (
  & $pythonBin ChemBlender/scripts/release_metadata.py `
    --extension-root ChemBlender --format json --include-channel
) | ConvertFrom-Json
$version = $metadata.version
$metadata
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
& $pythonBin ChemBlender/scripts/validate_extension.py `
  --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py `
  --python $pythonBin --blender $blenderBin
```

`release_metadata.py` 是 version、package、checksum 和 artifact 名称的单一来源；
不要再拼接 `chemblender-{version}`。构建后还必须完成 ZIP path/type/CRC/inventory、
isolated install、real lifecycle 和产品 smoke；ZIP 存在不等于通过。

## Artifact evidence

`dependency_inventory.py` 从 `dependencies.toml` 与 exact wheels 生成
`wheel-inventory.json` 和 `wheel-license-copy-list.json`。
`artifact_size_report.py` 对 `.github/artifact-budgets.json` 生成
`artifact-size.json`。将这三个文件与 metadata 指定的 ZIP/checksum 放在同一临时
artifact directory 后，使用：

```powershell
& $pythonBin ChemBlender/scripts/verify_release_artifact.py `
  --artifact-dir release-artifact `
  --extension-root ChemBlender `
  --tag "v$version" `
  --metadata-mode package-ci `
  --budget .github/artifact-budgets.json
```

`artifact_size_report.py` 失败时不能静默增加预算。先审计 code/resources/wheels/other
差异和 intentional growth，再以新的 exact package evidence 单独评审基线变更。
公开 assets 只允许 ZIP/checksum；五文件 bundle 是 CI 内部 provenance。

## 远端集成证据

本地通过后，远端门仍是独立状态：

1. 只有获得 explicit authorization 才能 push 或创建 PR。
2. PR required checks 必须对应被审查的 exact HEAD；旧 run、其他 branch run 和
   本地产物都不能替代。
3. 普通 merge commit 也需要用户授权。合并后复验 `origin/main` ancestry 和 main
   exact commit 的 CI。
4. `Remote CI: Not Run` 是未运行，不是 Passed；记录原因并停止在远端门前。

不得自动 force-push、rebase、删除分支、dispatch workflow、创建 tag 或 Release。

## Prerelease / final

version 与对应 dated `CHANGELOG.md` entry 必须在同一个 pre-tag commit。先用
`release_metadata.py` 和 Blender native validate 检查 version，再取得 main exact
HEAD 的全部门禁。创建、push annotated exact tag 需要新的 explicit authorization；
不要使用 `git push --follow-tags`。

tag push 的 `extension-package` run 必须满足：

- `headSha` 等于 annotated tag 指向的 exact tag commit；
- branch/tag 名与 metadata version 一致；
- 唯一成功 exact tag run 产生唯一未过期 metadata-named 五文件 artifact；
- package、wheel/license、size、install/lifecycle 全部通过。

在用户另行授权后，`extension-release.yml` 的 `publish=false` dispatch 只读验证
exact tag artifact，不重建。核对 run/artifact IDs、SHA-256、Release notes 和
prerelease/latest policy 后再次暂停。只有新的发布授权才可用 `publish=true`；
workflow 会重新验证同一 artifact 后创建 Release。

RC 后只修 blocker 或文档事实，不加入新范围。Published tag/asset 不移动、不替换；
用户可能已下载时发布新的 patch/prerelease。
