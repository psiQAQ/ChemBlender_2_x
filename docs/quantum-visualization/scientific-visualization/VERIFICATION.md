# CBQ Viewer 最终本地交付验证

2026-09-09，分支 `feat/cbq-only-viewer`。最终交付由无 wheel Blender Extension、外部 `chemblender-prepare` 分发包、五层科学证据和完整回归组成。结构化记录见 [verification.json](verification.json)，用户操作见[科学量可视化 SOP](README.md)。

## 最终产物

| 产物 | 结果 | 精确身份 |
| --- | --- | --- |
| Blender Extension | Passed | `chemblender-2.4.0.zip`；2,830,321 bytes；109 members；SHA-256 `9ea6adcb84ff8c3e576652d9c140d111d9d509039e5da40d57a5bd404ed06708` |
| Python wheel | Passed | `chemblender_prepare-0.1.0-py3-none-any.whl`；559,417 bytes；SHA-256 `eca1dd6dcafc37a520af541cc7661a163046a5ed3932551a35213eaacc8093c9` |
| Python sdist | Passed | `chemblender_prepare-0.1.0.tar.gz`；897,243 bytes；SHA-256 `82554df211cea58e2394f40f2824283d5a2292e89f59755e719ad1b76ad4c6f6` |
| Artifact budget | Passed | package 2,830,321；unpacked 4,031,844；code 1,522,554；resources 2,509,290；wheels/other 0；全部增长 0 |
| Release artifact contract | Passed | package、SHA-256、wheel inventory、license list、artifact-size 五件齐全；`metadata-mode=package-ci` |

Extension 本地证据位于 `.agents/cache/l8-final-02/`，发行物副本位于 `.blend-analysis/l8-release-artifact-02/`，Python 包位于 `dist/`；这些路径均为本地可再生产物，不随 Git 发布。

## 验证结果

| 检查 | 结果 | 依据与范围 |
| --- | --- | --- |
| `uv build --no-cache` | Passed | wheel/sdist 构建、归档读取和 SHA-256 核对通过 |
| Extension validate/build/staging | Passed | Blender 5.1.1 native validate/build、staging 字节比对、CRC/安全路径/vendored core 审计 |
| 私有安装与冷启动 | Passed | Blender 5.1.1 / Python 3.13.9；安装、register/unregister/reload、CBQ 与纯 Mesh 路径通过 |
| 无科学 wheel | Passed | ZIP wheel inventory 为空；冷启动 `find_spec("rdkit")` 与 `find_spec("gemmi")` 均为 `None`；Bundled NumPy 可用 |
| RDKit 外部等价与性能 | Passed | 芳香/Kekulé、手性、带电、多片段、AddHs、ETKDG、MMFF/UFF、势能、MOL/SDF/SMILES；冷启动额外 0.01761 s |
| 异步控制器与取消 | Passed | modal 0.0000078 s、running 0.01089 s、取消确认 0.33582 s；失败/过期/篡改不提交 |
| 生命周期 | Passed | 处理程序、源文件、输入 CBQ/VDB 移走后，既有 CBQ、View、动画、缓存重建及保存重开可用 |
| 图片、动画与窗口 | Passed | 36 Cycles 静图、128 PNG 帧、4 MP4、11 张真实 Blender 窗口截图；截图清单保留其原安装包身份 |
| 离线 SOP | Passed | `index.html` 已从当前 Markdown 重建；17 anchors、157 local links、0 remote resources；文档专项在 81 项回归中通过 |
| 完整 unittest | Passed | 2526 tests、37 skips、0 failures/errors，147.228 s |
| 共享真实用户安装、远端 CI / 发布 | Not Run | 本轮只使用私有 profile；未经授权不修改共享安装、不 push、不发布 |

## 五层科学证据

五层指模型、适配器/operation、真实文件、UI/渲染、保存重开。完整逐量矩阵在 [SOP 第 15 节](README.md#verification)。其中：

- wavefunction、NCI、QTAIM、phonon 已使用真实后端，并覆盖正式安装态 View 与源移走重开；Fermi 使用真实 SrVO₃ 五文件完成统一 operation。
- MO/密度/ESP、PQR、轨迹与力保留 28 张 Cycles 静图、128 帧动画和 5 个工作台；ELF/LOL 新增 8 张 Cycles 图和 2 个工作台；对应 77 个科学数组已做哈希或完整值生命周期核对。
- vibration/spectra 与 band/DOS 使用固定真实 Gaussian/ORCA/VASP 文件，并保留 reader、模型、原生 View 与 lifecycle contracts。
- ELF/LOL 使用 critic2 1.3.15 从真实 water HF/STO-3G WFX 分别生成 40×40×40 网格，经统一 CLI 发布为无量纲 CBQ；无 wheel 安装扩展完成 Grid Volume、Research/Teaching Cycles、移走原 CUBE/输入 CBQ后的独立冷重开、Rebuild 与 Save As。源/持久数组 SHA-256 分别一致为 `38583b…04a5`、`679b07…766e`。

## 错误恢复

| 情况 | 已验证行为 |
| --- | --- |
| 处理程序未配置或后端缺失 | capability 明确 unavailable；Blender 本地编辑与既有 View 保持可用 |
| 用户取消 | 写 cancel marker；两秒内确认，必要时只终止本任务 PID tree；不发布半成品 |
| 非零退出、伪造 success、hash/路径/UUID 不可信 | fail closed；活动项目、旧实体和旧 View 不变 |
| 输入 revision 已过期 | 拒绝结果，要求按当前 revision 重新计算 |
| CBQ 损坏或旧 schema | 保留原包并报告检查/升级失败；事务导入不留下半项目 |
| 源文件、处理程序或渲染缓存移走 | 权威 CBQ 数组继续可读；本地 View 可重建，外部重计算需重新配置处理程序 |

重放时使用独立 `BLENDER_USER_RESOURCES`。运行环境能力以 `chemblender-prepare capabilities --json` 和 `doctor` 的当次输出为准；根 `.venv` 未配置专用 scientific/fermi/wavefunction 路由时报告 warning 是预期行为，不等于已配置缓存环境失效。
