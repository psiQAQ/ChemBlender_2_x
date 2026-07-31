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
$ErrorActionPreference = 'Stop'

$metadataJson = & $pythonBin ChemBlender/scripts/release_metadata.py `
  --extension-root ChemBlender --format json --include-channel
if ($LASTEXITCODE -ne 0) { throw 'Release metadata probe failed' }
$metadata = $metadataJson | ConvertFrom-Json
$version = $metadata.version
$metadata
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
if ($LASTEXITCODE -ne 0) { throw 'Generated documentation check failed' }

$wheelDir = Join-Path (Get-Location) 'ChemBlender/wheels'
$rdkitWheel = Join-Path $wheelDir 'rdkit-2026.3.3-cp313-cp313-win_amd64.whl'
$gemmiWheel = Join-Path $wheelDir 'gemmi-0.7.5-cp313-cp313-win_amd64.whl'
foreach ($wheel in @($rdkitWheel, $gemmiWheel)) {
  if (-not (Test-Path -LiteralPath $wheel -PathType Leaf)) {
    throw "Missing reviewed offline wheel: $wheel"
  }
}
$qualificationRoot = Join-Path `
  ([IO.Path]::GetTempPath()) `
  ("cb23-qualification-" + [guid]::NewGuid().ToString('N'))
$dependencySite = Join-Path $qualificationRoot 'site-packages'
New-Item -ItemType Directory -Path $dependencySite | Out-Null

& $pythonBin ChemBlender/scripts/dependency_inventory.py `
  --inventory ChemBlender/dependencies.toml `
  --wheel-dir $wheelDir `
  --manifest ChemBlender/blender_manifest.toml `
  --output (Join-Path $qualificationRoot 'wheel-inventory.json') `
  --license-copy-list (Join-Path $qualificationRoot 'wheel-license-copy-list.json')
if ($LASTEXITCODE -ne 0) { throw 'Pinned wheel inventory validation failed' }

& $pythonBin -m pip install --disable-pip-version-check `
  --no-index --no-deps --target $dependencySite $rdkitWheel $gemmiWheel
if ($LASTEXITCODE -ne 0) { throw 'Offline dependency bootstrap failed' }

$previousPythonPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = $dependencySite
  & $pythonBin -c "from importlib.metadata import version; import gemmi; from rdkit import rdBase; assert version('gemmi') == '0.7.5'; assert gemmi.__version__ == '0.7.5'; assert version('rdkit') == '2026.3.3'; assert rdBase.rdkitVersion == '2026.03.3'"
  if ($LASTEXITCODE -ne 0) { throw 'Exact Gemmi/RDKit probe failed' }
  & $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
  if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
  & $pythonBin -m compileall -q ChemBlender worker tests
  if ($LASTEXITCODE -ne 0) { throw 'compileall failed' }
} finally {
  if ($null -eq $previousPythonPath) {
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  } else {
    $env:PYTHONPATH = $previousPythonPath
  }
}
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'git diff --check failed' }
& $pythonBin ChemBlender/scripts/validate_extension.py `
  --source-path ChemBlender --blender $blenderBin
if ($LASTEXITCODE -ne 0) { throw 'Extension validation failed' }
& $pythonBin ChemBlender/scripts/build_extension.py `
  --python $pythonBin --blender $blenderBin
if ($LASTEXITCODE -ne 0) { throw 'Extension build failed' }
```

该前置只读取已审核、已下载并通过 `dependencies.toml` hash/size/license contract 的
pinned wheels；`--no-index --no-deps` 保证 pip 不得联网下载或解析其他依赖，目标是
一次性的隔离目录，不是 Blender global site-packages。不得将包安装到 Blender
global site-packages。开发者也可显式复用已安装 Extension 的共享
`extensions/.local/lib/python3.13/site-packages` 作为 `$dependencySite`，但仍须先运行
相同的 exact Gemmi/RDKit probe；这不能替代 package gate 对原始 wheels 的 inventory
验证。裸 Blender Python 未完成上述前置时，不得把 full suite 失败或 skip 解释为
产品结果。

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
