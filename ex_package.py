import importlib


def safe_check_rdkit(min_version="2023.09.01"):
    try:
        spec = importlib.util.find_spec("rdkit")
        if spec is None:
            return False

        importlib.import_module("rdkit")
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