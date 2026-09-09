"""Shared scientific model contract after removing the mixed parser facade."""

import subprocess
import sys
import unittest
from pathlib import Path

from cbq_core import model
from cbq_core.model_registry import MODEL_ENUMS, MODEL_TYPES


class CorePublicApiTests(unittest.TestCase):
    def test_registered_models_and_enums_match_shared_model(self):
        for name, model_type in {**MODEL_TYPES, **MODEL_ENUMS}.items():
            with self.subTest(name=name):
                self.assertIs(getattr(model, name), model_type)

    def test_entire_shared_package_imports_without_scientific_backends(self):
        code = """
import importlib
import pkgutil
import sys
import cbq_core
for entry in pkgutil.walk_packages(cbq_core.__path__, cbq_core.__name__ + '.'):
    importlib.import_module(entry.name)
forbidden = {'bpy', 'rdkit', 'gemmi', 'scipy', 'iodata', 'gbasis', 'cclib',
             'chemblender_prepare', 'pymatgen', 'phonopy', 'pyprocar'}
assert not forbidden.intersection(sys.modules), forbidden.intersection(sys.modules)
"""
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_api_document_contract(self):
        document = (
            Path(__file__).resolve().parents[1]
            / "docs/quantum-visualization/2.3.0/public-core-api.md"
        )
        self.assertTrue(document.is_file(), f"missing API document: {document}")
        content = document.read_bytes()
        self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
        text = content.decode("utf-8")
        for heading in (
            "## 稳定模型门面",
            "## 存储 API",
            "## Session API",
            "## Reader 契约",
            "## Recipe 契约",
            "## 内部 Adapter 兼容面",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
