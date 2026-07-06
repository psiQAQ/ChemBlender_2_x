import bpy
import sys
import subprocess
import importlib
import os

def safe_check_rdkit(min_version="2023.09.01"):
    try:
        spec = importlib.util.find_spec("rdkit")
        if spec is None:
            return False

        rdkit = importlib.import_module("rdkit")
        from rdkit import rdBase

        version = rdBase.rdkitVersion
        v_inst = version.split(".")
        v_min = min_version.split(".")

        for i in range(min(len(v_inst), len(v_min))):
            vi = v_inst[i].replace("dev", "").replace("-release", "")
            vm = v_min[i]
            if not vi.isdigit() or not vm.isdigit():
                continue
            if int(vi) > int(vm):
                return True
            if int(vi) < int(vm):
                return False
        return True

    except Exception:
        return False


# -----------------------------------------------------------------------------
PYPI_MIRROR = {
    'Default': '',
    'BFSU (Beijing)': 'https://mirrors.bfsu.edu.cn/pypi/web/simple',
    'TUNA (Beijing)': 'https://pypi.tuna.tsinghua.edu.cn/simple',
}

def install_rdkit(mirror_url):
    python_exe = os.path.realpath(sys.executable)
    try:
        subprocess.run([python_exe, "-m", "pip", "uninstall", "rdkit", "-y"], check=False)
        subprocess.run([python_exe, "-m", "pip", "cache", "purge"], check=False)
        subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip"], check=False)

        install_cmd = [python_exe, "-m", "pip", "install", "rdkit"]
        if mirror_url:
            install_cmd += ["-i", mirror_url]
        result = subprocess.run(install_cmd, check=False)
        return result.returncode == 0
    except Exception:
        return False

# -----------------------------------------------------------------------------
class CHEMBLENDER_OT_install_rdkit(bpy.types.Operator):
    bl_label = "Install RDKit"
    bl_idname = "chem.install_rdkit"

    def execute(self, context):
        mirror_name = context.scene.pypi_mirror
        mirror_url = PYPI_MIRROR[mirror_name]

        self.report({'INFO'}, f"Installing RDKit from {mirror_name}...")
        success = install_rdkit(mirror_url)

        if success:
            self.report({'INFO'}, "RDKit installed successfully! Restart Blender to use.")
        else:
            self.report({'ERROR'}, "Installation failed. Please check Internet.")

        # 刷新面板
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

        return {'FINISHED'}
