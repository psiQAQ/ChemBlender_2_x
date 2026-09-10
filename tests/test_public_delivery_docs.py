import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender/scripts/generate_public_delivery_docs.py"


class PublicDeliveryDocsTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location("public_delivery_docs", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_generated_public_surface_and_offline_guides_are_fresh(self):
        documents = self.module().render_documents()
        for relative, content in documents.items():
            self.assertEqual((ROOT / relative).read_bytes(), content, relative)
        surface = json.loads(documents["docs/prepare/public-surface.json"])
        self.assertEqual(len(surface["cli_commands"]), 10)
        self.assertEqual(len(surface["gui_commands"]), 9)
        self.assertEqual(len(surface["operations"]), 21)
        self.assertEqual(len(surface["readers"]), 22)
        self.assertEqual(len(surface["export_formats"]), 13)
        self.assertEqual(surface["reader_api_version"], "1.0-rc1")
        self.assertFalse(surface["python_sdk"])

    def test_offline_guides_have_no_remote_or_missing_resources(self):
        documents = self.module().render_documents()
        for language in ("en", "zh-CN"):
            manifest = json.loads(documents[f"docs/offline/{language}/manifest.json"])
            self.assertEqual(manifest["remote_resources"], 0)
            self.assertEqual(manifest["missing_resources"], 0)
            self.assertGreater(manifest["link_count"], 5)
            self.assertEqual(manifest["image_count"], 27)
            self.assertEqual(
                set(manifest["image_sha256"]),
                {"docs/user/assets/2.5.0/blender-viewer.png", *(
                    'docs/user/assets/2.5-tutorials/' + name for name in (
                        'aspirin-cycles.png', 'aspirin-prepare-convert.jpg',
                        'aspirin-view.jpg', 'aspirin-render-result.jpg',
                        'ethanol-cycles.png', 'ethanol-prepare-convert.jpg',
                        'ethanol-generated.jpg', 'ethanol-energy.jpg', 'ethanol-apply.jpg',
                        'crystal-cocrystal.png', 'crystal-diamond.png', 'crystal-cell-view.jpg',
                        'grid-prepare-inspect.jpg', 'grid-prepare-convert.jpg', 'grid-signed-volume.png', 'grid-sampling.png', 'grid-difference-refined.png', 'grid-primary-surface.jpg', 'grid-signed-surface.jpg',
                        'trajectory-frame15.png', 'trajectory-apply-frame.jpg', 'trajectory-smooth.jpg', 'trajectory-prepare-inspect.jpg', 'trajectory-prepare-convert.jpg', 'trajectory-frame0.jpg', 'trajectory-frame31.jpg'))},
            )

    def test_body_links_images_tables_and_paragraphs_survive_rendering(self):
        module = self.module()
        source = ('# First step\n\nKeep this paragraph.\n- Click **Preview**.\n\n'
                  '[Open section](#first-step)\n\n'
                  '[![Actual screenshot](image.png)](image.png)\n\n'
                  '| Name | Value |\n| --- | --- |\n| Atoms | 21 |\n')
        rendered = module._markdown(source)
        self.assertIn('<p>Keep this paragraph.</p>', rendered)
        self.assertIn('<a href="#first-step">Open section</a>', rendered)
        self.assertIn('<a href="image.png"><img alt="Actual screenshot" src="image.png"></a>', rendered)
        self.assertIn('<thead><tr><th scope="col">Name</th>', rendered)
        self.assertIn('<td>21</td>', rendered)
        self.assertLess(rendered.index('Click'), rendered.index('<img'))
        self.assertIn('<h2 id="first-step">', rendered)
        self.assertEqual(module._inline('`[literal](file)`'), '<code>[literal](file)</code>')
        self.assertIn('<ol start="3">', module._markdown('1. Before\n\n![Step](image.png)\n\n3. After'))

    def test_resource_audit_detects_missing_targets_and_remote_images(self):
        module = self.module()
        relative = 'docs/offline/en/index.html'
        content = b'<h2 id="exists">Title</h2><a href="#exists">OK</a><a href="#absent">Bad</a><a href="missing.html">Bad</a><img src="https://example.test/image.png">'
        stats = module._resource_stats(relative, content, {relative: content})
        self.assertEqual(stats['missing_resources'], 2)
        self.assertEqual(stats['remote_resources'], 1)
        self.assertEqual(stats['link_count'], 3)
        self.assertEqual(stats['image_count'], 1)

    def test_real_body_links_resolve_to_sections_and_ancillary_downloads(self):
        documents = self.module().render_documents()
        content = documents['docs/offline/en/index.html'].decode('utf-8')
        self.assertIn('href="#document-2"', content)
        self.assertIn('href="../zh-CN/index.html#document-1"', content)
        self.assertIn('download="public-surface.json"', content)
        self.assertEqual(content.count('<img '), 27)
        self.assertIn('download="ethanol.smi"', content)
        self.assertIn('download="ethanol-science-check.json"', content)
        self.assertGreater(content.index('<img '), content.index('<article id="document-3">'))


if __name__ == "__main__":
    unittest.main()
