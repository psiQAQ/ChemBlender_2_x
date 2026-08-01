# ChemBlender 2.3.0 RC 可用性验收脚本

本脚本是 **hybrid scripted product/integration acceptance**，不是独立人类可用性
研究。所有场景都从 packaged Extension 开始；真实 `bpy.ops` 用户路径与安装包内
core/`ExportJob` 集成断言按下表明确区分。每个 Blender 进程必须创建唯一、短路径
的 **fresh profile**（`BLENDER_USER_RESOURCES`、`TEMP` 和 `TMP`）；若目录已存在
则 **refuse reuse**。不得把源码复制到 legacy add-on 目录。

## 环境与输入

- Windows x64，Blender 5.1.2 或更高的 5.1 版本。
- 当前 checkout 构建出的 `ChemBlender/chemblender-2.3.0-alpha.1.zip`。
- 固定输入：
  `tests/fixtures/xyz/water.xyz`、
  `tests/fixtures/sdf/records.sdf`、
  `tests/fixtures/cube/sheared.cube`、
  `tests/fixtures/cif/partial-disorder.cif` 和
  `tests/fixtures/pdb/altloc.pdb`。
- legacy 场景：
  `chemblender-2.1-molecule.blend`
  (`36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`)、
  `chemblender-2.2-crystal.blend`
  (`f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a`) 和
  `chemblender-2.2-edited-scaffold.blend`
  (`a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740`)。

开始前记录 Blender/Python 版本、CPU、内存、checkout SHA、ZIP SHA-256 和 wall
clock。每项任务从触发操作开始计时，到下表验收条件全部成立时停止。

## 记录字段

每项都必须记录：

- `Completion`：Passed、Failed 或 Not Run。
- `Elapsed time`：wall-clock 秒数；共享自动化场景须明确标记。
- `Errors`：错误文本或 `None`；warning 与 error 分开记录。
- `Help required`：None、内置提示、文档或人工协助。
- `Scientific misunderstanding`：误解的物理/化学语义及纠正方式，或 `None`。

## 用户任务

| ID | 操作 | 验收条件 |
| --- | --- | --- |
| U01 | 从 ZIP 安装并启用 Extension | `bl_ext.user_default.chemblender` 启用；RDKit 与 Gemmi 可导入；没有 legacy add-on copy |
| U02 | Quick Import 导入 XYZ | 预览显示 Structure；确认后创建绑定正确 revision 的 Structure View |
| U03 | 导入 SDF 并确认 conformers 分组 | review 后生成 `ConformerSet`；Project Browser 可见；SDF export 可重新解析为两条记录 |
| U04 | 导入 Cube、查看 diagnostics 并 resolve Cube semantic | 原 Grid 保持 Ambiguous；派生 Grid 为 Complete `scalar_field`；signed surface 绑定派生 revision |
| U05 | 导入 CIF | fractional/cell/occupancy 保持；Structure View 可保存、reopen 和 CIF export；该 fixture 不宣称 ADP round-trip |
| U06 | 导入 PDB | hierarchy、altloc、occupancy 与默认可见性保持；保存、reopen 后仍一致 |
| U07 | 浏览并导出 diagnostics | 合成 canonical report 经真实 operators 分页/导出；UI preview 有界且 JSON/Markdown 完整 |
| U08 | save/reopen 项目 | `.blend` 与 `.cbq` 建立一致 link；clean save 不改 manifest；reopen 恢复实体和 View bindings |
| U09 | 处理 revision 提示 | Keep Current、Update Selected Views 和 Comparison View 只作用于目标 logical View |
| U10 | 执行 scientific edit | 原 Structure 不变；生成带 `USER_EDITED` topology/provenance 的派生 Structure |
| U11 | export 并语义重导入 | XYZ/extXYZ/SDF/CIF 目标可重读；需确认的 loss preview 不被绕过 |
| U12 | migrate hash-locked legacy scene | 显式 preview/confirm；原对象进入 backup；新 Project/View 保存并 reopen；三份 fixture 均通过 |

## 验收层级

| 任务 | 执行层级 |
| --- | --- |
| U01 | fresh profile 中用 Blender Extensions operator 安装并启用 exact ZIP |
| U02 | XYZ 经真实 Quick Import/confirm operators，验证 revision 与 Structure View binding |
| U03 | SDF staging 是 Quick Import operator；preview/group/commit 直调安装包 UI services；export 是 Blender operator，随后由安装包 core reader 复验 |
| U04 | Cube 经真实 Quick Import/confirm、semantic-resolution 和 surface operators；源 Grid 与派生 Grid 的状态断言来自真实 fixture |
| U05 | 安装包 `parse_cif`/project、真实 Blender View/save/reopen，加直接 `ExportJob`/reparse；不把 direct core 调用描述为 UI 点击 |
| U06 | PDB fixture 经真实 Quick Import/confirm operators，验证 hierarchy、altloc、occupancy、save/reopen |
| U07 | 合成 diagnostic document 经真实 copy/page/export operators；它不是某个 Cube 文件自产的 report |
| U08 | 构造安装包 Project/View 后执行真实 Blender save/reopen；验证 `.cbq` link 与 clean/link-only save manifest |
| U09 | 对进程内构造的 replacement revision/Grid 调用真实 Keep/Update/Comparison operators；不宣称来源于第二次文件导入 |
| U10 | 直接 preview helper 识别 mesh edit，再用真实 `apply_scientific_edits` operator 生成派生 Structure/topology |
| U11 | SDF 使用真实 export operator；XYZ/extXYZ/CIF 还包含安装包 core/`ExportJob` 的 semantic re-import |
| U12 | 每份 hash-locked `.blend` 在独立 fresh profile 中安装 exact ZIP，调用真实 preview/migrate operators 并 save/reopen |

## 自动化复验

下面的命令保留 validate/build、U01–U11 product run 和每份 U12 fixture 的原始
stdout/stderr。每一步都检查 native exit code；product/legacy 还必须匹配自己的
`PASS:` marker。`tests/blender_usability_legacy.py` 不导入 checkout package，而是
安装 exact ZIP 后只通过 `bl_ext.user_default.chemblender` 和真实 operators 工作。

```powershell
$ErrorActionPreference = "Stop"
$blender = "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
$evidence = ".superpowers\sdd\2026-07-23-chemblender-2.3.0-wave-4-performance-ux"
New-Item -ItemType Directory -Force -Path $evidence | Out-Null

function Quote-Native([string]$value) {
    return '"' + $value.Replace('"', '\"') + '"'
}

function New-FreshProfile([string]$label) {
    $token = [guid]::NewGuid().ToString("N").Substring(0, 8)
    $profile = "D:\cbu-$label-$token"
    if (Test-Path -LiteralPath $profile) {
        throw "refuse reuse: fresh profile already exists: $profile"
    }
    $user = New-Item -ItemType Directory -Path (Join-Path $profile "user")
    $tmp = New-Item -ItemType Directory -Path (Join-Path $profile "tmp")
    if (
        -not (Test-Path -LiteralPath $user.FullName -PathType Container) -or
        -not (Test-Path -LiteralPath $tmp.FullName -PathType Container)
    ) {
        throw "fresh profile creation failed: $profile"
    }
    return [pscustomobject]@{
        Root = $profile
        User = $user.FullName
        Temp = $tmp.FullName
    }
}

function Invoke-CapturedBlender(
    [string]$label,
    [string[]]$arguments,
    [string]$passMarker
) {
    $profile = New-FreshProfile $label
    $env:BLENDER_USER_RESOURCES = $profile.User
    $env:TEMP = $profile.Temp
    $env:TMP = $profile.Temp
    $stdout = Join-Path $evidence "task6-final-$label-stdout.log"
    $stderr = Join-Path $evidence "task6-final-$label-stderr.log"
    $watch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $blender -ArgumentList $arguments `
        -Wait -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $watch.Stop()
    if ($process.ExitCode -ne 0) {
        throw "$label failed with exit $($process.ExitCode); inspect $stdout / $stderr"
    }
    if (-not (Select-String -LiteralPath $stdout -SimpleMatch `
        -Pattern $passMarker -Quiet)) {
        throw "$label missing PASS marker '$passMarker'; inspect $stdout"
    }
    Write-Host "PASS: $label exit=0 elapsed=$($watch.Elapsed.TotalSeconds)s profile=$($profile.Root)"
    return [pscustomobject]@{
        Label = $label
        Profile = $profile.Root
        ExitCode = $process.ExitCode
        ElapsedSeconds = $watch.Elapsed.TotalSeconds
        Stdout = $stdout
        Stderr = $stderr
    }
}

$validateLog = Join-Path $evidence "task6-final-validate.log"
& $blender --command extension validate ChemBlender 2>&1 |
    Tee-Object -FilePath $validateLog
$validateExit = $LASTEXITCODE
if ($validateExit -ne 0) { throw "extension validate failed: $validateExit" }
Write-Host "PASS: extension validate"

$buildLog = Join-Path $evidence "task6-final-build.log"
& $blender --command extension build `
    --source-dir ChemBlender --output-dir ChemBlender 2>&1 |
    Tee-Object -FilePath $buildLog
$buildExit = $LASTEXITCODE
if ($buildExit -ne 0) { throw "extension build failed: $buildExit" }
Write-Host "PASS: extension build"

$package = (Resolve-Path "ChemBlender\chemblender-2.3.0-alpha.1.zip").Path
$packageHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $package).Hash.ToLowerInvariant()
$expectedPackageHash = "0db367c18fd849897bb5ca0189c50c573bda40ea5db35c565a99f882115356ec"
if ($packageHash -ne $expectedPackageHash) {
    throw "package hash mismatch: $packageHash"
}

$product = Invoke-CapturedBlender "product" @(
    "--background",
    "--factory-startup",
    "--python-exit-code", "1",
    "--python", (Quote-Native ((Resolve-Path "tests\blender_smoke.py").Path)),
    "--", (Quote-Native $package)
) "PASS: ChemBlender extension lifecycle"

$fixtures = @(
    [pscustomobject]@{
        Label = "legacy-21"
        Path = "tests\fixtures\legacy-blend\chemblender-2.1-molecule.blend"
        Hash = "36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4"
    },
    [pscustomobject]@{
        Label = "legacy-22-crystal"
        Path = "tests\fixtures\legacy-blend\chemblender-2.2-crystal.blend"
        Hash = "f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a"
    },
    [pscustomobject]@{
        Label = "legacy-22-edited"
        Path = "tests\fixtures\legacy-blend\chemblender-2.2-edited-scaffold.blend"
        Hash = "a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740"
    }
)
$legacyResults = foreach ($fixture in $fixtures) {
    $fixturePath = (Resolve-Path $fixture.Path).Path
    $actualHash = (
        Get-FileHash -Algorithm SHA256 -LiteralPath $fixturePath
    ).Hash.ToLowerInvariant()
    if ($actualHash -ne $fixture.Hash) {
        throw "fixture hash mismatch: $fixturePath $actualHash"
    }
    Invoke-CapturedBlender $fixture.Label @(
        "--background",
        "--python-exit-code", "1",
        (Quote-Native $fixturePath),
        "--python", (Quote-Native ((Resolve-Path "tests\blender_usability_legacy.py").Path)),
        "--", (Quote-Native $package), $packageHash, $fixture.Hash
    ) "PASS: packaged legacy migration and reopen"
}
```

通过条件是 validate/build exit `0`，product/legacy 的 `$process.ExitCode` 为 `0`，
对应 `PASS:` marker 存在，且所有明确分层的任务断言成立；仅有 ZIP、manifest 可解析
或源码环境里的 migration test 不算 packaged Extension 验收通过。

## 问题分级

- `Blocker`：数据丢失/损坏、错误科学映射、无法恢复或保存、崩溃，或核心任务失败。
- `Major`：主路径仍可完成，但需要未说明的人工绕行，或产生会误导决策的 UI/诊断。
- `Minor`：不改变科学结果、持久化和核心任务完成度的可发现性、文案或非阻断 warning。

RC scope freeze 后只修 `Blocker`。每个修复必须先有复现测试，再有 focused commit；
`Major`/`Minor` 记录到结果和后续计划，不在本任务扩展产品范围。
