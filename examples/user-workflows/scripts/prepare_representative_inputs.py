"""Fetch provenance-locked representative inputs without project dependencies."""

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath


USER_AGENT = "ChemBlender-representative-fixtures/1.0 (+https://github.com/psiQAQ/ChemBlender_2_x)"
RMD17_MEMBER = PurePosixPath("rmd17/npz_data/rmd17_aspirin.npz")
RMD17_CONTAINER_BYTES = 1_066_301_513
SOURCES = {
    "ccd_ain": {
        "url": "https://files.rcsb.org/ligands/download/AIN_ideal.sdf",
        "source_id": "wwPDB CCD AIN ideal coordinates",
        "license": "CC0-1.0",
        "license_url": "https://www.rcsb.org/pages/policies",
        "sha256": "ee52997413966ecfb530b783a643b4b88e1d2b2312cb2a8358a39fd31ff0686b",
        "bytes": 1506,
    },
    "ccd_cff": {
        "url": "https://files.rcsb.org/ligands/download/CFF_ideal.sdf",
        "source_id": "wwPDB CCD CFF ideal coordinates",
        "license": "CC0-1.0",
        "license_url": "https://www.rcsb.org/pages/policies",
        "sha256": "7efc60af4a10b6ce723e0dd2a5516e91e3995be879059a1fcc18dab36d17d18c",
        "bytes": 1729,
    },
    "ccd_ta1": {
        "url": "https://files.rcsb.org/ligands/download/TA1_ideal.sdf",
        "source_id": "wwPDB CCD TA1 ideal coordinates",
        "license": "CC0-1.0",
        "license_url": "https://www.rcsb.org/pages/policies",
        "sha256": "2d7c4609811c04d9965f6ed27c7e33753409b29721fe8c61a11d453bab17dfd3",
        "bytes": 7876,
    },
    "cod_4503272": {
        "url": "https://www.crystallography.net/cod/4503272.cif",
        "source_id": "COD 4503272",
        "license": "CC0-1.0",
        "license_url": "https://www.crystallography.net/cod/new.html",
        "sha256": "0ab8afbcc0f931327a5cba664df8317bf557f3b6f06b1fe5b27908676b89c5f5",
        "bytes": 14996,
    },
    "cod_9012293": {
        "url": "https://www.crystallography.net/cod/9012293.cif",
        "source_id": "COD 9012293",
        "license": "CC0-1.0",
        "license_url": "https://www.crystallography.net/cod/new.html",
        "sha256": "0c05811e5981dbbb0b4306c41f75a6a54fc9c6fde7d6bedf628b777396f8e2b7",
        "bytes": 5565,
    },
    "pdb_1d3z": {
        "url": "https://files.rcsb.org/download/1D3Z.pdb",
        "source_id": "PDB 1D3Z",
        "license": "CC0-1.0",
        "license_url": "https://www.rcsb.org/pages/policies",
        "sha256": "21099cb88231455fdfab4095dddfadcc85cc4213e105cf5f9cfff2ca21993378",
        "bytes": 1015821,
    },
    "rmd17_aspirin": {
        "url": "https://ndownloader.figshare.com/files/23950376",
        "source_id": "10.6084/m9.figshare.12672038.v3 member rmd17_aspirin.npz",
        "license": "CC0-1.0",
        "license_url": "https://figshare.com/articles/dataset/Revised_MD17_dataset_rMD17_/12672038",
        "container_md5": "cb1a927628d96f2e966025da4fb63d18",
        "sha256": "6efe3d2454c1a9215efe2bf271c58084ae556afa188a740ae06955bf43456ee8",
        "bytes": 153601803,
    },
    "openbabel_5sun": {
        "url": "https://raw.githubusercontent.com/openbabel/openbabel/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/test/files/5sun_protein.mol2",
        "source_id": "openbabel/openbabel@0e94434fa75c9f61095023e3c12e0d5f2ac035ff:test/files/5sun_protein.mol2",
        "license": "GPL-2.0-only",
        "license_url": "https://raw.githubusercontent.com/openbabel/openbabel/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/COPYING",
        "sha256": "1ac476afd860c326995e28125cc4cf4007b33e022a8c9f397d9e350f3e5a4fbd",
        "bytes": 779286,
    },
    "apbs_pqr": {
        "url": "https://raw.githubusercontent.com/Electrostatics/apbs/4613d0d547c3c71df8815dcb85e9e19abf61822c/examples/protein-rna/model_outNB.pqr",
        "source_id": "Electrostatics/apbs@4613d0d547c3c71df8815dcb85e9e19abf61822c:examples/protein-rna/model_outNB.pqr",
        "license": "BSD-3-Clause",
        "license_url": "https://raw.githubusercontent.com/Electrostatics/apbs/4613d0d547c3c71df8815dcb85e9e19abf61822c/LICENSE.md",
        "sha256": "44f78c804e4f006f74a9f2b439094063e1046735106e2c8436543ba7e7578a68",
        "bytes": 70047,
    },
    "avogadro_cjson": {
        "url": "https://raw.githubusercontent.com/OpenChemistry/avogadrolibs/e32739bed4b9d79db080a32a0026947e15b240d9/avogadro/qtplugins/templatetool/ligands/4-phthalocyanine.cjson",
        "source_id": "OpenChemistry/avogadrolibs@e32739bed4b9d79db080a32a0026947e15b240d9:4-phthalocyanine.cjson",
        "license": "BSD-3-Clause",
        "license_url": "https://raw.githubusercontent.com/OpenChemistry/avogadrolibs/e32739bed4b9d79db080a32a0026947e15b240d9/LICENSE",
        "sha256": "310cb5b4d48a08662d9e956b1a7ac778a05ea9060be6cffcdfaedecfd390097e",
        "bytes": 2708,
    },
    "qcschema_gradient": {
        "url": "https://raw.githubusercontent.com/MolSSI/QCSchema/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/tests/simple/water_gradient_HF_output.json",
        "source_id": "MolSSI/QCSchema@5390e6f11d21847e4e7ca2ad14a97594f957cb2d:tests/simple/water_gradient_HF_output.json",
        "license": "BSD-3-Clause",
        "license_url": "https://raw.githubusercontent.com/MolSSI/QCSchema/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/LICENSE",
        "sha256": "73b28251edde763490937d303cee0b4c2cf4bf55c566d4139c5e33220ffae451",
        "bytes": 1378,
    },
}
CACHE_NAMES = {
    "ccd_ain": "AIN_ideal.sdf",
    "ccd_cff": "CFF_ideal.sdf",
    "ccd_ta1": "TA1_ideal.sdf",
    "cod_4503272": "4503272.cif",
    "cod_9012293": "9012293.cif",
    "pdb_1d3z": "1D3Z.pdb",
    "rmd17_aspirin": "rmd17_aspirin.npz",
    "openbabel_5sun": "5sun_protein.mol2",
    "apbs_pqr": "model_outNB.pqr",
    "avogadro_cjson": "4-phthalocyanine.cjson",
    "qcschema_gradient": "water_gradient_HF_output.json",
}
DIRECT_OUTPUTS = {
    "cod_4503272": "cif/cod-4503272-caffeine-cocrystal.cif",
    "avogadro_cjson": "cjson/avogadro-phthalocyanine.cjson",
    "openbabel_5sun": "mol2/openbabel-5sun-protein.mol2",
    "pdb_1d3z": "pdb/1d3z-ubiquitin-nmr.pdb",
    "apbs_pqr": "pqr/apbs-protein-rna-nb.pqr",
    "qcschema_gradient": "qcschema/molssi-water-gradient-hf.json",
}
DERIVED_OUTPUTS = (
    "cube/h2-lcao-1s-density-64.cube",
    "extxyz/aspirin-rmd17-32.extxyz",
    "mol/ain-aspirin-v2000.mol",
    "mol/ta1-paclitaxel-v3000.mol",
    "poscar/cod-9012293-diamond-2x2x2.CONTCAR",
    "poscar/cod-9012293-diamond.POSCAR",
    "sdf/ccd-3d-showcase.sdf",
    "smiles/ta1-paclitaxel-isomeric.smi",
    "xyz/ta1-paclitaxel-ccd.xyz",
)
KCAL_PER_MOL_PER_EV = 23.060547830619
CUBE_SOURCE_DESCRIPTOR = (
    "chemblender-analytic-h2-lcao-density-v1|R=1.4 bohr|"
    "extent=[-6,6] bohr|grid=64x64x64|phi=exp(-r)/sqrt(pi)|"
    "S=exp(-R)*(1+R+R^2/3)|rho=(phi_A+phi_B)^2/(1+S)|electrons=2"
)


def _request(url, headers=None):
    return urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )


class HTTPRangeReader:
    """Sequentially read a range-only HTTP object with bounded retries."""

    def __init__(self, url, total_bytes, chunk_bytes=64 * 1024 * 1024, retries=3):
        self.url = url
        self.total_bytes = total_bytes
        self.chunk_bytes = chunk_bytes
        self.retries = retries
        self.offset = 0
        self.chunk = io.BytesIO()

    def _fetch(self):
        start = self.offset
        end = min(start + self.chunk_bytes, self.total_bytes) - 1
        expected_range = f"bytes {start}-{end}/{self.total_bytes}"
        expected_bytes = end - start + 1
        for attempt in range(self.retries):
            try:
                request = _request(self.url, {"Range": f"bytes={start}-{end}"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status != 206:
                        raise OSError(f"expected HTTP 206, got {response.status}")
                    if response.headers.get("Content-Range") != expected_range:
                        raise OSError(
                            f"unexpected Content-Range: {response.headers.get('Content-Range')}"
                        )
                    content = response.read()
                if len(content) != expected_bytes:
                    raise OSError(
                        f"truncated range {start}-{end}: {len(content)} of {expected_bytes} bytes"
                    )
                self.offset = end + 1
                self.chunk = io.BytesIO(content)
                return
            except Exception:
                if attempt + 1 == self.retries:
                    raise

    def read(self, size=-1):
        pieces = []
        remaining = size
        while size < 0 or remaining > 0:
            content = self.chunk.read(-1 if size < 0 else remaining)
            if content:
                pieces.append(content)
                if size >= 0:
                    remaining -= len(content)
                    if remaining == 0:
                        break
            if self.offset >= self.total_bytes:
                break
            self._fetch()
        return b"".join(pieces)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_destination(destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    return tempfile.NamedTemporaryFile(
        mode="w+b",
        delete=False,
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )


def download(url, destination):
    destination = Path(destination)
    temporary_path = None
    try:
        with urllib.request.urlopen(_request(url), timeout=120) as response:
            with _atomic_destination(destination) as temporary:
                temporary_path = Path(temporary.name)
                shutil.copyfileobj(response, temporary, length=1024 * 1024)
                temporary.flush()
                os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return _sha256(destination), destination.stat().st_size


def download_rmd17_aspirin(url, destination):
    destination = Path(destination)
    temporary_path = None
    try:
        reader = HTTPRangeReader(url, RMD17_CONTAINER_BYTES)
        with tarfile.open(fileobj=reader, mode="r|bz2") as archive:
            for member in archive:
                if PurePosixPath(member.name) != RMD17_MEMBER:
                    continue
                source = archive.extractfile(member)
                if source is None:
                    raise RuntimeError(f"archive member is not a file: {member.name}")
                with source, _atomic_destination(destination) as temporary:
                    temporary_path = Path(temporary.name)
                    shutil.copyfileobj(source, temporary, length=1024 * 1024)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                temporary_path.replace(destination)
                return _sha256(destination), destination.stat().st_size
        raise RuntimeError(f"archive member not found: {RMD17_MEMBER}")
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _atomic_copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with _atomic_destination(destination) as temporary:
            temporary_path = Path(temporary.name)
            with source.open("rb") as stream:
                shutil.copyfileobj(stream, temporary, length=1024 * 1024)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _write_bytes(destination, content):
    destination = Path(destination)
    temporary_path = None
    try:
        with _atomic_destination(destination) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def _validated_cache(cache, key):
    cached = Path(cache) / CACHE_NAMES[key]
    if not cached.is_file():
        raise FileNotFoundError(f"missing cached source {key}; run --stage download")
    digest = _sha256(cached)
    size = cached.stat().st_size
    source = SOURCES[key]
    if digest != source["sha256"] or size != source["bytes"]:
        raise RuntimeError(
            f"source mismatch for {key}: {size} bytes, sha256 {digest}"
        )
    return cached


def fetch_sources(cache, output_root):
    cache = Path(cache)
    output_root = Path(output_root)
    cache.mkdir(parents=True, exist_ok=True)
    evidence = {}
    for key, source in SOURCES.items():
        cached = cache / CACHE_NAMES[key]
        if not cached.is_file():
            fetch = download_rmd17_aspirin if key == "rmd17_aspirin" else download
            fetch(source["url"], cached)
        cached = _validated_cache(cache, key)
        digest = source["sha256"]
        size = source["bytes"]
        if key in DIRECT_OUTPUTS:
            output = output_root / DIRECT_OUTPUTS[key]
            _atomic_copy(cached, output)
            if _sha256(output) != digest:
                raise RuntimeError(f"copied bytes changed: {output}")
        else:
            output = None
        evidence[key] = {
            "source_id": source["source_id"],
            "source_url": source["url"],
            "license": source["license"],
            "license_url": source["license_url"],
            "sha256": digest,
            "bytes": size,
            "cache": str(cached),
            "output": None if output is None else str(output),
        }
    return evidence


def _load_dependencies():
    repository_root = str(Path(__file__).resolve().parents[3])
    if repository_root not in sys.path:
        sys.path.insert(0, repository_root)
    site = (
        Path(os.environ["APPDATA"])
        / "Blender Foundation"
        / "Blender"
        / "5.1"
        / "extensions"
        / ".local"
        / "lib"
        / "python3.13"
        / "site-packages"
    )
    if not site.is_dir():
        raise RuntimeError(f"Blender 5.1 extension dependency site is missing: {site}")
    site_text = str(site)
    if site_text not in sys.path:
        sys.path.insert(0, site_text)
    import numpy
    from rdkit import Chem

    return numpy, Chem


def _ccd_molecules(cache, Chem):
    molecules = {}
    for key, label in (("ccd_ain", "AIN"), ("ccd_cff", "CFF"), ("ccd_ta1", "TA1")):
        source = _validated_cache(cache, key)
        molecule = Chem.SDMolSupplier(
            str(source),
            removeHs=False,
            sanitize=True,
        )[0]
        if molecule is None or molecule.GetNumConformers() != 1:
            raise RuntimeError(f"cannot load one 3D CCD record from {source}")
        molecule.SetProp("_Name", label)
        molecules[label] = molecule
    return molecules


def _derive_molecules(cache, output_root, Chem):
    molecules = _ccd_molecules(cache, Chem)
    blocks = {
        "mol/ain-aspirin-v2000.mol": Chem.MolToMolBlock(
            molecules["AIN"],
            forceV3000=False,
        ),
        "mol/ta1-paclitaxel-v3000.mol": Chem.MolToMolBlock(
            molecules["TA1"],
            forceV3000=True,
        ),
    }
    for relative, text in blocks.items():
        _write_bytes(output_root / relative, text.replace("\r\n", "\n").encode("utf-8"))

    sdf = b"".join(
        _validated_cache(cache, key).read_bytes()
        for key in ("ccd_ain", "ccd_cff", "ccd_ta1")
    )
    _write_bytes(output_root / "sdf/ccd-3d-showcase.sdf", sdf)

    smiles = (
        f"{Chem.MolToSmiles(molecules['TA1'], canonical=True, isomericSmiles=True)}"
        "\tTA1 paclitaxel\n"
    )
    _write_bytes(
        output_root / "smiles/ta1-paclitaxel-isomeric.smi",
        smiles.encode("ascii"),
    )

    paclitaxel = molecules["TA1"]
    conformer = paclitaxel.GetConformer()
    xyz = [
        str(paclitaxel.GetNumAtoms()),
        (
            "wwPDB CCD TA1 ideal coordinates; source_sha256="
            f"{SOURCES['ccd_ta1']['sha256']}"
        ),
    ]
    for index, atom in enumerate(paclitaxel.GetAtoms()):
        position = conformer.GetAtomPosition(index)
        xyz.append(
            f"{atom.GetSymbol()} {position.x:.8f} {position.y:.8f} {position.z:.8f}"
        )
    _write_bytes(
        output_root / "xyz/ta1-paclitaxel-ccd.xyz",
        ("\n".join(xyz) + "\n").encode("ascii"),
    )


def _derive_rmd17(cache, output_root, numpy, Chem):
    selected = tuple(range(0, 3200, 100))
    with numpy.load(_validated_cache(cache, "rmd17_aspirin"), allow_pickle=False) as data:
        charges = numpy.asarray(data["nuclear_charges"], dtype=int)
        coordinates = numpy.asarray(data["coords"])[list(selected)]
        energies = numpy.asarray(data["energies"])[list(selected)] / KCAL_PER_MOL_PER_EV
        forces = numpy.asarray(data["forces"])[list(selected)] / KCAL_PER_MOL_PER_EV
        source_indices = numpy.asarray(data["old_indices"])[list(selected)]
    symbols = tuple(Chem.GetPeriodicTable().GetElementSymbol(int(value)) for value in charges)
    lines = []
    for frame, subset_index in enumerate(selected):
        lines.append(str(len(symbols)))
        lines.append(
            "Properties=species:S:1:pos:R:3:forces:R:3 "
            f"energy={energies[frame]:.12g} step={subset_index} "
            f"source_index={int(source_indices[frame])} "
            "energy_unit=electron_volt "
            "forces_unit=electron_volt_per_angstrom "
            "step_unit=dimensionless"
        )
        for symbol, position, force in zip(
            symbols,
            coordinates[frame],
            forces[frame],
        ):
            lines.append(
                f"{symbol} "
                + " ".join(f"{float(value):.10f}" for value in position)
                + " "
                + " ".join(f"{float(value):.10f}" for value in force)
            )
    _write_bytes(
        output_root / "extxyz/aspirin-rmd17-32.extxyz",
        ("\n".join(lines) + "\n").encode("ascii"),
    )


def _periodic_structure(numpy, numbers, cell, fractional, revision, label):
    from uuid import NAMESPACE_URL, uuid5

    from cbq_core.model import ArrayData
    from cbq_core.model import PeriodicSiteData
    from cbq_core.model import Structure

    identifier = uuid5(NAMESPACE_URL, f"chemblender:representative:{revision}:{label}")
    count = len(numbers)
    fractional_data = ArrayData(
        numpy.asarray(fractional, dtype=float),
        ("atom", "xyz"),
        "dimensionless",
    )
    cell_data = ArrayData(
        numpy.asarray(cell, dtype=float),
        ("cell_vector", "xyz"),
        "angstrom",
    )
    periodic = PeriodicSiteData(
        fractional_coordinates=fractional_data,
        site_labels=tuple(f"C{index + 1}" for index in range(count)),
        occupancies=ArrayData(numpy.ones(count), ("atom",), "dimensionless"),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * count,
        disorder_groups=(0,) * count,
        declared_space_group_name=None,
        declared_space_group_number=None,
        symmetry_operations=(),
        cif_envelope_id=None,
    )
    return Structure(
        id=identifier,
        revision=revision,
        atomic_numbers=tuple(numbers),
        coordinates=ArrayData(
            fractional_data.values @ cell_data.values,
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=cell_data,
        periodic=periodic,
    )


def _derive_crystal(cache, output_root, numpy):
    from uuid import uuid5

    import gemmi

    from chemblender_prepare.core.exporters import PoscarExportSettings
    from chemblender_prepare.core.exporters import export_poscar
    from chemblender_prepare.core.formats.cif import parse_cif
    from cbq_core.model import ArrayData
    from cbq_core.model import AtomicProperty
    from cbq_core.model import DatasetStatus

    source = _validated_cache(cache, "cod_9012293")
    parsed = parse_cif(source).structures[0]
    block = gemmi.cif.read_file(str(source)).sole_block()
    small = gemmi.make_small_structure_from_block(block)
    group = gemmi.find_spacegroup_by_name(small.spacegroup_hm)
    fractional = sorted(
        {
            tuple(round(float(value) % 1.0, 12) for value in operation.apply_to_xyz([0.0, 0.0, 0.0]))
            for operation in group.operations()
        }
    )
    if len(fractional) != 8 or parsed.atomic_numbers != (6,):
        raise RuntimeError("COD 9012293 did not expand to the expected 8-site diamond cell")
    revision = SOURCES["cod_9012293"]["sha256"]
    conventional = _periodic_structure(
        numpy,
        (6,) * 8,
        parsed.cell.values,
        fractional,
        revision,
        "diamond-conventional",
    )
    export_poscar(
        output_root / "poscar/cod-9012293-diamond.POSCAR",
        conventional,
        PoscarExportSettings(comment="COD 9012293 diamond conventional cell"),
    )

    super_fractional = tuple(
        tuple((numpy.asarray(position) + (x, y, z)) / 2.0)
        for x in range(2)
        for y in range(2)
        for z in range(2)
        for position in fractional
    )
    supercell = _periodic_structure(
        numpy,
        (6,) * 64,
        numpy.asarray(parsed.cell.values) * 2.0,
        super_fractional,
        revision,
        "diamond-2x2x2",
    )
    velocities = AtomicProperty(
        id=uuid5(supercell.id, "zero-ion-velocities"),
        revision=revision,
        semantic_role="atomic_velocity",
        domain="atom",
        data=ArrayData(
            numpy.zeros((64, 3)),
            ("atom", "xyz"),
            "angstrom_per_femtosecond",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=supercell.id,
    )
    export_poscar(
        output_root / "poscar/cod-9012293-diamond-2x2x2.CONTCAR",
        supercell,
        PoscarExportSettings(
            comment="COD 9012293 diamond 2x2x2 supercell with zero velocities",
            velocity_mode="cartesian",
        ),
        velocities=velocities,
    )


def _derive_cube(output_root, numpy):
    count = 64
    lower = -6.0
    upper = 6.0
    separation = 1.4
    step = (upper - lower) / (count - 1)
    axis = numpy.linspace(lower, upper, count)
    x, y, z = numpy.meshgrid(axis, axis, axis, indexing="ij")
    left = numpy.sqrt(x * x + y * y + (z + separation / 2.0) ** 2)
    right = numpy.sqrt(x * x + y * y + (z - separation / 2.0) ** 2)
    phi_left = numpy.exp(-left) / numpy.sqrt(numpy.pi)
    phi_right = numpy.exp(-right) / numpy.sqrt(numpy.pi)
    overlap = numpy.exp(-separation) * (
        1.0 + separation + separation * separation / 3.0
    )
    density = (phi_left + phi_right) ** 2 / (1.0 + overlap)
    lines = [
        "ChemBlender analytic H2 1s LCAO two-electron density",
        "Not HF or DFT; coordinates and density grid are in atomic units",
        f"    2 {lower:.10f} {lower:.10f} {lower:.10f}",
        f"   {count} {step:.10f} 0.0000000000 0.0000000000",
        f"   {count} 0.0000000000 {step:.10f} 0.0000000000",
        f"   {count} 0.0000000000 0.0000000000 {step:.10f}",
        f"    1 0.0000000000 0.0000000000 0.0000000000 {-separation / 2.0:.10f}",
        f"    1 0.0000000000 0.0000000000 0.0000000000 {separation / 2.0:.10f}",
    ]
    values = density.ravel(order="C")
    lines.extend(
        " ".join(f"{float(value):.8e}" for value in values[start : start + 6])
        for start in range(0, len(values), 6)
    )
    _write_bytes(
        output_root / "cube/h2-lcao-1s-density-64.cube",
        ("\n".join(lines) + "\n").encode("ascii"),
    )


def derive(cache, output_root):
    cache = Path(cache)
    output_root = Path(output_root)
    for relative in DERIVED_OUTPUTS:
        (output_root / relative).parent.mkdir(parents=True, exist_ok=True)
    numpy, Chem = _load_dependencies()
    _derive_molecules(cache, output_root, Chem)
    _derive_rmd17(cache, output_root, numpy, Chem)
    _derive_crystal(cache, output_root, numpy)
    _derive_cube(output_root, numpy)
    return {
        relative: {
            "sha256": _sha256(output_root / relative),
            "bytes": (output_root / relative).stat().st_size,
        }
        for relative in DERIVED_OUTPUTS
    }


def verify_derived(cache, output_root):
    output_root = Path(output_root)
    with tempfile.TemporaryDirectory(prefix="chemblender-representative-verify-") as directory:
        fresh_root = Path(directory)
        evidence = derive(cache, fresh_root)
        for relative in DERIVED_OUTPUTS:
            current = output_root / relative
            fresh = fresh_root / relative
            if not current.is_file() or current.read_bytes() != fresh.read_bytes():
                raise RuntimeError(f"derived output drift: {relative}")
    return evidence


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--stage",
        choices=("download", "derive", "verify"),
        required=True,
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.stage == "download":
        evidence = fetch_sources(args.cache.resolve(), args.output_root.resolve())
    elif args.stage == "derive":
        evidence = derive(args.cache.resolve(), args.output_root.resolve())
    else:
        evidence = verify_derived(args.cache.resolve(), args.output_root.resolve())
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
