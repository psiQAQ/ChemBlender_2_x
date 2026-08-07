"""Fetch provenance-locked representative inputs without project dependencies."""

import argparse
import hashlib
import io
import json
import os
import shutil
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
        digest = _sha256(cached)
        size = cached.stat().st_size
        if digest != source["sha256"] or size != source["bytes"]:
            raise RuntimeError(
                f"source mismatch for {key}: {size} bytes, sha256 {digest}"
            )
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


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--stage", choices=("download",), required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    evidence = fetch_sources(args.cache.resolve(), args.output_root.resolve())
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
