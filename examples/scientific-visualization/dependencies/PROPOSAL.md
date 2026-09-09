# 科学示例的独立环境提案

状态：2026-09-08 已获用户批准并完成缓存安装。scientific 环境的精确锁、主要模块导入和 `uv pip check` 已通过；Fermi 经下述兼容修复后，精确锁、导入、依赖检查及真实 SrVO3 输入 smoke 已通过；critic2 编译器 probe、构建和运行时资源检查已通过。这里的环境位于项目缓存，全部在 Blender Extension ZIP 之外；不修改 `gbasis-py312`、Blender 自带 Python 或用户扩展目录。

| 环境 | 固定主要版本 | 用途与影响 |
| --- | --- | --- |
| `.agents/cache/scientific-py312` | CPython 3.12.13；cclib 1.8.1；NumPy 2.2.6；SciPy 1.16.3；pymatgen-core 2026.7.16；phonopy 4.4.0；ASE 3.29.0；spglib 2.7.0 | 分子输出、IR/Raman/UV-Vis/ECD、周期结构、Band/DOS/PDOS 和声子。共 47 个固定包，包括 h5py、phonors、symfc、lxml、matplotlib 等上游必需依赖。 |
| `.agents/cache/fermi-py312` | CPython 3.12.13；PyProcar 6.5.0；NumPy 1.26.4；SciPy 1.16.3；ASE 3.29.0；spglib 2.7.0；PyVista 0.46.5；VTK 9.5.2 | Fermi 原始 VASP 数据解析和曲面提取。PyProcar 要求 NumPy < 2，因此独立环境；兼容修复后共 144 个固定包，包含上游强制的 PyVista Jupyter 依赖，体积较大。不得开启服务或读取上游 pickle 缓存。 |
| 已有 WSL `Ubuntu-24.04` 中的 critic2 CLI | 源码 `4b5dec9131c3a035af1b421d68a227c47fd641db`；两份 Fortran deb 均为 `13.3.0-6ubuntu2~24.04.1` | 从真实 WFX 生成 ELF/LOL/RDG/sign-lambda2-rho Cube、CPREPORT JSON 及 FLUXPRINT 有序路径。仅把 deb 解包至项目缓存，复用系统 GCC；不执行系统安装、不写 `/usr`。 |

`scientific-py312.txt` 与 `fermi-py312.txt` 已通过 `uv 0.11.19 pip compile --only-binary :all:` 针对 Windows CPython 3.12 解析；每个包锁定版本与上游 SHA-256。解析只读包索引元数据，不是实际安装或科学正确性验证。解析器对部分历史包版本的错误 Requires-Python 写法做了规范化并发出警告；未修改上游包。

Python 复用现有 `.agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe`，版本 3.12.13，不再下载解释器。两个 `.in` 文件记录直接依赖；两个 `.txt` 文件记录完整传递依赖。版本依据为已有源码 gitlink、项目依赖参考和官方 [cclib](https://pypi.org/project/cclib/1.8.1/)、[pymatgen-core](https://pypi.org/project/pymatgen-core/2026.7.16/)、[phonopy](https://pypi.org/project/phonopy/4.4.0/)、[PyProcar](https://pypi.org/project/pyprocar/6.5.0/) 元数据。

复现安装时分别执行以下步骤；目标环境已存在时跳过 `uv venv`，仅在对应缓存环境内同步锁文件；不得省略 `--require-hashes` 或复用现有 GBasis 环境作为目标：

```powershell
uv venv --python .agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe .agents/cache/scientific-py312
uv pip sync --python .agents/cache/scientific-py312/Scripts/python.exe --require-hashes --only-binary :all: --index-url https://pypi.org/simple --cache-dir .agents/cache/uv-scientific examples/scientific-visualization/dependencies/scientific-py312.txt

uv venv --python .agents/cache/pythons/cpython-3.12-windows-x86_64-none/python.exe .agents/cache/fermi-py312
uv pip sync --python .agents/cache/fermi-py312/Scripts/python.exe --require-hashes --only-binary :all: --index-url https://pypi.org/simple --cache-dir .agents/cache/uv-scientific examples/scientific-visualization/dependencies/fermi-py312.txt
```

WSL 已实测存在 CMake 3.28.3、Make 4.3、GCC 13.3.0、BLAS/LAPACK 3.12.0 和 libgfortran5 14.2.0；未找到 critic2 或 gfortran。`apt-get --simulate install gfortran-13=13.3.0-6ubuntu2~24.04.1` 得到 0 upgrade / 3 new / 0 remove：仅 gfortran-13、gfortran-13-x86-64-linux-gnu 和 libgfortran-13-dev。系统 GCC/base/dev 已与候选精确同版，运行依赖已经满足。

因此改用更窄的缓存方案：只取下列两包，共 12,336,750 bytes，省去 13,914-byte 的 gfortran-13 别名包。Ubuntu apt 索引给出的固定来源前缀为 `https://mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/main/g/gcc-13/`；许可为 GCC 的 GPL-3.0-or-later 及适用的 GCC Runtime Library Exception，保留 deb 内版权声明。下载、解包和编译已于 2026-09-08 获批准并通过；系统目录和包数据库未改变。

| 文件 | bytes | SHA-256 |
| --- | ---: | --- |
| `gfortran-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb` | 11408640 | `82382cb8506616ef7df5b9927694bfaacf97bdfb317b1f995453cc17c96aa071` |
| `libgfortran-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb` | 928110 | `ce0fdf0d9e7eadb33947ca7cdd0fc3477b570603cb721b108c96ebdfbb7cd80a` |

先按表中 URL 下载至 `.agents/cache/critic2-toolchain/packages/` 并逐个核验 bytes/hash；仅在全部匹配后运行如下 WSL 命令。`dpkg-deb -x` 仅解包，不运行维护脚本或修改 dpkg 数据库。

```bash
cd /mnt/d/workspace/ChemBlender_2_x
toolchain="$PWD/.agents/cache/critic2-toolchain"
dpkg-deb -x "$toolchain/packages/gfortran-13-x86-64-linux-gnu_13.3.0-6ubuntu2~24.04.1_amd64.deb" "$toolchain"
dpkg-deb -x "$toolchain/packages/libgfortran-13-dev_13.3.0-6ubuntu2~24.04.1_amd64.deb" "$toolchain"
compiler="$toolchain/usr/bin/x86_64-linux-gnu-gfortran-13"
fortran_flags="-B$toolchain/usr/libexec/gcc/x86_64-linux-gnu/13/ -B/usr/libexec/gcc/x86_64-linux-gnu/13/ -B/usr/lib/gcc/x86_64-linux-gnu/13/ -L$toolchain/usr/lib/gcc/x86_64-linux-gnu/13/ -static-libgfortran"
# First compile and run a small Fortran program in this cache.
# Proceed only after compiler, linker, and runtime have all passed.
cmake -S submodules/critic2 -B .agents/cache/critic2-build \
  -DCMAKE_BUILD_TYPE=Release -DENABLE_GUI=OFF -DUSE_EXTERNAL_LAPACK=OFF \
  -DCMAKE_Fortran_COMPILER="$compiler" -DCMAKE_Fortran_FLAGS="$fortran_flags"
cmake --build .agents/cache/critic2-build --parallel 4
```

`-B` 定位缓存中的 Fortran 前端；`-L` 与 `-static-libgfortran` 使用缓存开发包内静态库，避免解包后的开发库相对软链接缺少目标。实际 probe 发现缓存驱动找不到 `liblto_plugin.so`；两个额外的系统 `-B` 路径使它只读复用同版 GCC 的链接插件、`collect2`、C 前端、启动对象和 `libquadmath.a`。若这一路线的真实编译失败，先报告原因，不退回系统安装。critic2 关闭 GUI、使用内置 LAPACK，避免新增 GUI/BLAS 依赖；实际性能和输出需构建后验证。

critic2 计算路线计划复用现有 `worker/external_program.py` 外部进程边界；Windows Worker 到 WSL 的明确调用和路径适配仍待实现，不能把手工 WSL 运行当作面板计算闭环已完成。现有 `core/critic2_adapter.py` 与 `core/critic2_paths.py` 已支持 CPREPORT JSON 和 FLUXPRINT TEXT 的有序路径样点，保留明确单位、周期晶格变换与端点平移，不把 CP 连接关系当作真实路径。`QTAIM / critic2 Import` 面板已可选择 CPREPORT、可选 FLUXPRINT，并绑定现有 Structure；后台解析核对结构身份和文件哈希，完整批次一次发布，取消或源文件变化时不发布。

上述路径解析与原生 Blender 导入事务已通过针对测试；本轮固定 WFX 经真实 critic2 生成输出的对照仍为 Not Run。ELF / LOL / RDG / sign-lambda2-rho 网格将采用同一 WFX 和同一网格定义，记录 critic2 版本、源码 hash、输入 hash、完整命令和参数，不做收敛性宣称。

验证状态：两个缓存环境的安装、精确版本清单、import smoke 与 `uv pip check` Passed。真实 SrVO3 Fermi reader 测试 Passed（21³ k 点、20 条能带、E_F = 5.699 eV，结构及倒易晶格校验通过，实际生成曲面）；critic2 1.3.15 的缓存 probe、CMake 构建、帮助入口与动态库解析 Passed。真实 cclib / 周期 worker、critic2 科学输出及全部 Blender 闭环仍需后续验收。现有 GBasis 分子数值、PQR / extXYZ 和显示适配器的已完成验证不依赖这次安装，也不能替代这些待运行检查。

## 2026-09-08 Fermi 运行兼容修复

原 106 包锁的安装及 `uv pip check` 均成功，但 `import pyprocar` 因 `pyvista.core.utilities.NORMALS` 缺失而失败。[PyVista 0.46.5 的源码](https://raw.githubusercontent.com/pyvista/pyvista/v0.46.5/pyvista/core/utilities/__init__.py)仍导出该接口；0.47 起移除。兼容锁固定 PyVista 0.46.5 与其声明支持的 VTK 9.5.2，其他仍需要的既有包版本不变。两个新 pin 均写入 `.in`，完整版本与 SHA-256 由 uv 重新解析；没有修改第三方安装源码。

PyProcar 强制的 `pyvista[jupyter]` 在这个版本带入 Jupyter Server 的声明依赖，净增加 38 包（新增 47、移除 9），形成 144 包锁。它们仅安装在外部缓存环境；验收没有启动 Jupyter、Trame 或其他服务。

| 测量 | 原锁 | 兼容锁 | 差值 |
| --- | ---: | ---: | ---: |
| 匹配 Windows CPython 3.12 的 wheel 下载总字节 | 228,505,555 | 216,476,687 | -12,028,868 |
| Fermi 环境逻辑文件字节（各自导入检查后，含已有 pyc） | 833,132,568 | 770,693,253 | -62,439,315 |

wheel 大小来自 PyPI 对应固定哈希的文件元数据。逻辑文件字节是实测文件长度之和，不代表 NTFS 分配空间；uv cache 和 hardlink 复用另计。scientific 环境同口径为 411,441,000 字节。

新增依赖：`argon2-cffi==25.1.0`, `argon2-cffi-bindings==26.1.0`, `arrow==1.4.0`, `bleach==6.4.0`, `cffi==2.1.1`, `defusedxml==0.7.1`, `fastjsonschema==2.22.2`, `fqdn==1.5.1`, `isoduration==20.11.0`, `jinja2==3.1.6`, `jsonpointer==3.1.1`, `jsonschema==4.26.0`, `jsonschema-specifications==2025.9.1`, `jupyter-client==8.10.0`, `jupyter-core==5.9.1`, `jupyter-events==0.12.1`, `jupyter-server==2.21.0`, `jupyter-server-proxy==4.5.0`, `jupyter-server-terminals==0.5.4`, `jupyterlab-pygments==0.3.0`, `lark==1.3.1`, `markupsafe==3.0.3`, `mistune==3.3.4`, `nbclient==0.11.0`, `nbconvert==7.17.1`, `nbformat==5.11.1`, `nest-asyncio==1.6.0`, `pandocfilters==1.5.1`, `prometheus-client==0.26.0`, `pycparser==3.0`, `python-json-logger==4.2.0`, `pywinpty==3.0.5`, `pyzmq==27.2.0`, `referencing==0.37.0`, `rfc3339-validator==0.1.4`, `rfc3986-validator==0.1.1`, `rfc3987-syntax==1.1.0`, `rpds-py==2026.6.3`, `send2trash==2.1.0`, `simpervisor==1.0.0`, `terminado==0.18.1`, `tinycss2==1.5.1`, `tornado==6.5.8`, `uri-template==1.3.0`, `webcolors==25.10.0`, `webencodings==0.6.1`, `websocket-client==1.9.2`.

移除依赖：`cyclopts`, `docstring-parser`, `markdown-it-py`, `mdurl`, `nest-asyncio2`, `pyvista-validation`, `rich`, `rich-rst`, `trame-pyvista`.

原始锁、安装日志、完整版本清单、字节审计和真实输入测试日志保存在忽略目录 `.blend-analysis/2026-09-08-cbq-architecture-consolidation/dependency-install/`。正式 `fermi-py312.txt` 是当前通过运行检查的 144 包锁；旧锁可从 Git 历史和该目录的 `fermi-py312-original.txt` 复核。

critic2 可执行文件为 `.agents/cache/critic2-build/src/critic2`，大小 10,688,624 字节，SHA-256 `4f4fdb6b915c994cd3673778a175bbb1d8ce2ebff89b3a42c6d31d4f051f9f4e`。在 WSL 中将 `CRITIC_HOME` 指向 `/mnt/d/workspace/ChemBlender_2_x/submodules/critic2`（程序自行追加 `dat`），或用 `-r` 指定资源目录。构建未执行系统安装。
