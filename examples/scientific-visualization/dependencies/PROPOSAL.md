# 科学示例的独立环境提案

状态：仅完成解析与来源核验，尚未安装。这里的环境位于项目缓存，全部在 Blender Extension ZIP 之外；不修改 `gbasis-py312`、Blender 自带 Python 或用户扩展目录。

| 环境 | 固定主要版本 | 用途与影响 |
| --- | --- | --- |
| `.agents/cache/scientific-py312` | CPython 3.12.13；cclib 1.8.1；NumPy 2.2.6；SciPy 1.16.3；pymatgen-core 2026.7.16；phonopy 4.4.0；ASE 3.29.0；spglib 2.7.0 | 分子输出、IR/Raman/UV-Vis/ECD、周期结构、Band/DOS/PDOS 和声子。共 47 个固定包，包括 h5py、phonors、symfc、lxml、matplotlib 等上游必需依赖。 |
| `.agents/cache/fermi-py312` | CPython 3.12.13；PyProcar 6.5.0；NumPy 1.26.4；SciPy 1.16.3；ASE 3.29.0；spglib 2.7.0；PyVista 0.49.0；VTK 9.7.0 | Fermi 原始 VASP 数据解析和曲面提取。PyProcar 要求 NumPy < 2，因此独立环境；共 106 个固定包，包含上游强制的 PyVista Jupyter 依赖，体积较大。不得开启服务或读取上游 pickle 缓存。 |
| 已有 WSL `Ubuntu-24.04` 中的 critic2 CLI | 源码 `4b5dec9131c3a035af1b421d68a227c47fd641db`；两份 Fortran deb 均为 `13.3.0-6ubuntu2~24.04.1` | 从真实 WFX 生成 ELF/LOL/RDG/sign-lambda2-rho Cube、CPREPORT JSON 及 FLUXPRINT 有序路径。仅把 deb 解包至项目缓存，复用系统 GCC；不执行系统安装、不写 `/usr`。 |

`scientific-py312.txt` 与 `fermi-py312.txt` 已通过 `uv 0.11.19 pip compile --only-binary :all:` 针对 Windows CPython 3.12 解析；每个包锁定版本与上游 SHA-256。解析只读包索引元数据，不是实际安装或科学正确性验证。解析器对部分历史包版本的错误 Requires-Python 写法做了规范化并发出警告；未修改上游包。

Python 复用现有 `.agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe`，版本 3.12.13，不再下载解释器。两个 `.in` 文件记录直接依赖；两个 `.txt` 文件记录完整传递依赖。版本依据为已有源码 gitlink、项目依赖参考和官方 [cclib](https://pypi.org/project/cclib/1.8.1/)、[pymatgen-core](https://pypi.org/project/pymatgen-core/2026.7.16/)、[phonopy](https://pypi.org/project/phonopy/4.4.0/)、[PyProcar](https://pypi.org/project/pyprocar/6.5.0/) 元数据。

批准后分别执行以下步骤；不得省略 `--require-hashes` 或复用现有 GBasis 环境作为目标：

```powershell
uv venv --python .agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe .agents/cache/scientific-py312
uv pip sync --python .agents/cache/scientific-py312/Scripts/python.exe --require-hashes --only-binary :all: --index-url https://pypi.org/simple --cache-dir .agents/cache/uv-scientific examples/scientific-visualization/dependencies/scientific-py312.txt

uv venv --python .agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe .agents/cache/fermi-py312
uv pip sync --python .agents/cache/fermi-py312/Scripts/python.exe --require-hashes --only-binary :all: --index-url https://pypi.org/simple --cache-dir .agents/cache/uv-scientific examples/scientific-visualization/dependencies/fermi-py312.txt
```

WSL 已实测存在 CMake 3.28.3、Make 4.3、GCC 13.3.0、BLAS/LAPACK 3.12.0 和 libgfortran5 14.2.0；未找到 critic2 或 gfortran。`apt-get --simulate install gfortran-13=13.3.0-6ubuntu2~24.04.1` 得到 0 upgrade / 3 new / 0 remove：仅 gfortran-13、gfortran-13-x86-64-linux-gnu 和 libgfortran-13-dev。系统 GCC/base/dev 已与候选精确同版，运行依赖已经满足。

因此改用更窄的缓存方案：只取下列两包，共 12,336,750 bytes，省去 13,914-byte 的 gfortran-13 别名包。Ubuntu apt 索引给出的固定来源前缀为 `https://mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/main/g/gcc-13/`；许可为 GCC 的 GPL-3.0-or-later 及适用的 GCC Runtime Library Exception，保留 deb 内版权声明。仍需用户批准下载/解包和编译；以下是待验证方案，不代表编译已通过。

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| `gfortran-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb` | 11408640 | `82382cb8506616ef7df5b9927694bfaacf97bdfb317b1f995453cc17c96aa071` |
| `libgfortran-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb` | 928110 | `ce0fdf0d9e7eadb33947ca7cdd0fc3477b570603cb721b108c96ebdfbb7cd80a` |

批准后先按表中 URL 下载至 `.agents/cache/critic2-toolchain/packages/` 并逐个核验 bytes/hash；仅在全部匹配后运行如下 WSL 命令。`dpkg-deb -x` 仅解包，不运行维护脚本或修改 dpkg 数据库。

```bash
cd /mnt/d/workspace/ChemBlender_2_x
toolchain="$PWD/.agents/cache/critic2-toolchain"
dpkg-deb -x "$toolchain/packages/gfortran-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb" "$toolchain"
dpkg-deb -x "$toolchain/packages/libgfortran-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb" "$toolchain"
compiler="$toolchain/usr/bin/x86_64-linux-gnu-gfortran-13"
fortran_flags="-B$toolchain/usr/libexec/gcc/x86_64-linux-gnu/13/ -L$toolchain/usr/lib/gcc/x86_64-linux-gnu/13/ -static-libgfortran"
# First compile and run a small Fortran program in this cache.
# Proceed only after compiler, linker, and runtime have all passed.
cmake -S submodules/critic2 -B .agents/cache/critic2-build \
  -DCMAKE_BUILD_TYPE=Release -DENABLE_GUI=OFF -DUSE_EXTERNAL_LAPACK=OFF \
  -DCMAKE_Fortran_COMPILER="$compiler" -DCMAKE_Fortran_FLAGS="$fortran_flags"
cmake --build .agents/cache/critic2-build --parallel 4
```

`-B` 定位缓存中的 Fortran 前端；`-L` 与 `-static-libgfortran` 使用缓存开发包内静态库，避免解包后的开发库相对软链接缺少目标。系统已有 `collect2`、C 前端和 `libquadmath.a` 供链接复用。若这一路线的真实编译失败，先报告原因，不退回系统安装。critic2 关闭 GUI、使用内置 LAPACK，避免新增 GUI/BLAS 依赖；实际性能和输出需构建后验证。

critic2 计算路线计划复用现有 `worker/external_program.py` 外部进程边界；Windows Worker 到 WSL 的明确调用和路径适配仍待实现，不能把手工 WSL 运行当作面板计算闭环已完成。现有 `core/critic2_adapter.py` 与 `core/critic2_paths.py` 已支持 CPREPORT JSON 和 FLUXPRINT TEXT 的有序路径样点，保留明确单位、周期晶格变换与端点平移，不把 CP 连接关系当作真实路径。`QTAIM / critic2 Import` 面板已可选择 CPREPORT、可选 FLUXPRINT，并绑定现有 Structure；后台解析核对结构身份和文件哈希，完整批次一次发布，取消或源文件变化时不发布。

上述路径解析与原生 Blender 导入事务已通过针对测试；本轮固定 WFX 经真实 critic2 生成输出的对照仍为 Not Run。ELF / LOL / RDG / sign-lambda2-rho 网格将采用同一 WFX 和同一网格定义，记录 critic2 版本、源码 hash、输入 hash、完整命令和参数，不做收敛性宣称。

验证状态：本提案的依赖解析 Passed；两个新 Python 环境和 critic2 工具链尚未安装，安装、import smoke、真实 cclib / 周期 / Fermi reader 与 worker、critic2 实际计算及其数值和 Blender 闭环均为 Not Run，等待授权。现有 GBasis 分子数值、PQR / extXYZ 和显示适配器的已完成验证不依赖这次安装，也不能替代这些待运行检查。
