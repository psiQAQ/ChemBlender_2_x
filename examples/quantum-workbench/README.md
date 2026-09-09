# 水分子量子可视化示例

> 冻结的 2.4 波函数资格样例。2.5 通过单一 `chemblender-prepare.exe` 和 Worker Protocol v1 联动，当前步骤见[中文 prepare 指南](../../docs/prepare/zh-CN/index.md)。

使用固定 IOData FCHK 输入，在独立 worker 中计算 HOMO 5、LUMO 6、电子密度和静电势；Blender 保存轨道等值面、密度表面上的静电势、色标、切片、剖面与结构视图。

可直接打开随附的 [water-workbench.blend](output/water-workbench.blend)，并保持同名 `.cbq` 目录相邻。

输入为 [water_sto3g_hf_g03.fchk](https://github.com/theochem/iodata/blob/adab5813713ba64641565eb2a8c11803a4e9bba6/iodata/test/data/water_sto3g_hf_g03.fchk)，SHA-256 为 `aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816`。文件第二行声明 `SP RHF STO-3G`；水分子为中性单重态，10 个电子。文件名中的 `g03` 只是上游命名提示，输入没有声明精确程序版本。上游源码许可证见 [IOData LICENSE.txt](../../submodules/iodata/LICENSE.txt)，输入原样保留在固定子模块中。

规则网格为 `45 × 45 × 45`，间距 `0.28 bohr`，起点 `(-6.13, -5.87, -6.07) bohr`，避开核位置。密度采用输入中的 total SCF AO density matrix；静电势采用该矩阵和输入明确记录的有效核电荷。此网格用于显示，未进行积分收敛研究。HOMO/LUMO 编号从 1 开始，MO 相位颜色的正负不代表电荷。

从仓库根目录完整复跑到新目录；需要现有 Blender 5.1 和已批准建立的项目科学环境，不会安装软件包：

```powershell
$blender = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
$script = 'tests/blender_quantum_workbench_lifecycle.py'
$env:BLENDER_USER_RESOURCES = "$PWD/.agents/cache/quantum-example-profile"
$exampleOutput = "$PWD/.agents/cache/quantum-example-replay"
& $blender --background --factory-startup --python-exit-code 1 --python $script -- --phase build --output $exampleOutput
& $blender --background --factory-startup --python-exit-code 1 --python $script -- --phase reopen --output $exampleOutput
& $blender --background --factory-startup --python-exit-code 1 --python $script -- --phase save-as --output $exampleOutput
& $blender --background --factory-startup --python-exit-code 1 --python $script -- --phase recover --output $exampleOutput
& $blender --background --factory-startup --python-exit-code 1 --python $script -- --phase export --output $exampleOutput
```

`--worker-python`、`--existing-libraries` 和 `--output` 可显式指定环境和输出位置。构建阶段拒绝覆盖已有 `.blend`；已构建示例可用 `--phase render` 重新渲染，或用 `--phase refresh` 从已有科学数组重建本示例的展示与材质。

随附生成物位于 [output](output/)；上述复跑命令写入 `$exampleOutput`：

| 文件 | 内容 |
| --- | --- |
| `water-workbench.blend` 与同名 `.cbq` | 主场景和权威科学数据，应保持相邻 |
| `overview.png` | 统一灯光与相机的示例总览 |
| `provenance.json` | 输入来源、方法、软件版本、网格、视图参数和数组哈希 |
| `plane.csv`、`profile.csv` | 根据科学坐标重算的采样值；含单位和有效标记 |
| `save-as/water-workbench-copy.*` | 独立 Save As 副本 |
| `verification-*.json` | 每个生命周期阶段的实际验证结果 |
| `orbitals/` | 使用固定相机批量导出的 HOMO/LUMO 图片及导出元数据 |
| `pyscf-comparison.json` | 独立 PySCF 计算与保存网格的逐点数值对照 |

重开和 Save As 会核对科学 `.npy` 的 SHA-256 与视图参数。恢复阶段只删除副本内的 `cache/render`，再通过另一 Blender 进程重建；同时核对密度专用 `Grid to Mesh` 节点仍为 property surface v2。切片与剖面 CSV 的检查会移动显示对象，确认科学结果字节不变。主场景、科学数组、图片及来源记录随示例保存；派生缓存、Save As 验证副本和运行检查记录不纳入 Git。

独立 [PySCF 数值对照](output/pyscf-comparison.json) 使用本机已有 PySCF 2.13.1 重新进行 RHF/STO-3G 计算，在 12 个固定网格点比较 HOMO、LUMO、密度与 ESP，最大绝对差分别为 `4.38e-9`、`4.82e-9`、`1.59e-9`、`9.60e-9`。轨道仅允许整体相位对齐；容差预设为 `atol=1e-6, rtol=1e-5`。这是逐点检查，不代表积分域与网格已收敛。

在已有 PySCF 的 Python 环境中运行 `python -B tests/compare_water_pyscf.py` 可复核；脚本只读取科学项目，结果写入 `.agents/cache/water-pyscf-comparison.json`，不安装依赖。
