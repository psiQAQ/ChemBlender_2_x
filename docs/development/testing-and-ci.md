# Testing and CI

ChemBlender release validation uses four layers. Passing an earlier layer does not replace a later one.

## 1. Repository Contracts

Use Blender's bundled Python 3.13; pytest is not required.

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
```

Contracts cover manifest metadata and permissions, ignored dependencies, lifecycle wiring, package-install prohibition, package exclusions, and CI pins.

## 2. Validate and Build

```powershell
$blenderBin = 'C:\Program Files\Blender Foundation\Blender 5.1\blender.exe'
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --python $pythonBin --blender $blenderBin
```

The built ZIP must contain the manifest, license, RDKit wheel, and two `.blend` libraries. It must not contain tests, development scripts, caches, or nested ZIP files.

## 3. Isolated Blender Install

```powershell
$package = (Get-Item 'ChemBlender\chemblender-2.2.0.zip').FullName
$env:BLENDER_USER_RESOURCES = (New-Item -ItemType Directory -Path '.agents\cache\blender-release-clean' -Force).FullName
& $blenderBin --background --factory-startup --python tests/blender_smoke.py -- $package
Remove-Item Env:BLENDER_USER_RESOURCES
```

This proves that an existing user extension or shared `.local` directory did not satisfy a missing dependency. The smoke test covers package contents, RDKit behavior, installed blend libraries, registration, repeated reload, and unregister.

## 4. Real Installation and GitHub Actions

Reinstall the same package into the real `user_default` repository from a fresh Blender process. Do not close an interactive Blender automatically; save work and close it before replacing loaded wheel DLLs.

GitHub Actions repeats the local sequence on `windows-latest`, downloads Blender and RDKit from pinned sources, verifies their checksums, and uploads the tested package. The draft pull request run is authoritative; a local equivalent run alone is not CI proof.

Pillow is outside the 2.2.0 package while no extension code imports PIL or uses Pillow-dependent RDKit behavior. Any such feature must update the dependency decision, manifest, and CI together.
