"""Format-level fixtures authored from pinned critic2 flx_printpath, not real runs."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy as np

from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from chemblender_prepare.core.critic2_adapter import parse_critic2_cpreport
from chemblender_prepare.core.critic2_paths import parse_critic2_paths
from tests.test_critic2_topology import FIXTURE, structure


BOHR_TO_ANGSTROM = .529177210903


def flux_text(samples, *, start, end, unit="bohr", matrix=None, start_fractional=None,
              end_fractional=None, gap=0., start_cell=3, end_cell=1):
    """Use the exact 1.3.15 TEXT header/13-column layout with synthetic numbers."""
    def vector(values):
        return " ".join(f"{value:.12E}" for value in values)

    text = (f"# Gradient from BCP (upwards)\n# number of points: {len(samples)}\n"
            "# ---- origin of the path ----\n"
            f"# name: B1 (bond) ncp: 3 ncpcel: {start_cell}\n"
            "# rho: .25 grad: 0. lap: -.1\n"
            f"# starting position (cryst.): {vector(start if start_fractional is None else start_fractional)}\n"
            f"# starting position ({unit}): {vector(start)}\n"
            f"# starting path direction ({unit}): -1.0 0.0 0.0\n"
            "# ---- end of the path ----\n"
            f"# name: N1 (nucleus) ncp: 1 ncpcel: {end_cell}\n"
            f"# distance between nucleus and end of path (bohr): {gap:.6f}\n"
            "# rho: 10. grad: 0. lap: -30.\n"
            f"# end position (cryst.): {vector(end if end_fractional is None else end_fractional)}\n"
            f"# end position ({unit}): {vector(end)}\n#\n")
    if matrix is not None:
        homogeneous = np.eye(4)
        homogeneous[:3, :3] = matrix
        for name, values in (("Crys2Car", homogeneous), ("Car2Crys", np.linalg.inv(homogeneous))):
            text += f"# {name} :\n" + "\n".join("# " + vector(row) for row in values) + "\n\n"
    text += "# x y z rho rhox rhoy rhoz rhoxx rhoxy rhoxz rhoyy rhoyz rhozz\n"
    for sample in samples:
        text += vector((*sample, .25, 0., 0., 0., -.3, 0., 0., -.2, 0., .4)) + "\n"
    return text + "# End gradient path\n\n"


class Critic2PathTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.cp_path = self.directory / "cpreport.json"
        self.path = self.directory / "flux.txt"
        self.document = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.document["units"] = "bohr"
        self.document["structure"] = {"is_molecule": True, "molecule_centering_vector": [.2, -.3, .4]}
        self.structure = structure(uuid4())
        self.write_cp()

    def write_cp(self, unit="bohr"):
        self.cp_path.write_text(json.dumps(self.document), encoding="utf-8")
        self.cp_batch = parse_critic2_cpreport(self.cp_path, structure_id=self.structure.id, coordinate_unit=unit)
        self.graph = self.cp_batch.datasets[0]

    def parse(self, text, **kwargs):
        self.path.write_text(text, encoding="utf-8")
        return parse_critic2_paths(self.path, graph=self.graph, cpreport_path=self.cp_path, **kwargs)

    def molecular_text(self):
        offset = np.array(self.document["structure"]["molecule_centering_vector"])
        samples = np.array(((1., 0., 0.), (.5, .3, .2), (.01, 0., 0.))) + offset
        return flux_text(samples, start=samples[0], end=offset, gap=.01), samples

    def test_molecular_origin_unit_conversion_and_order_keep_unsnapped_samples(self):
        text, samples = self.molecular_text()
        self.write_cp(unit="angstrom")
        batch = self.parse(text)
        derived = batch.datasets[0]
        self.assertEqual(self.graph.paths, ())
        self.assertNotEqual(derived.id, self.graph.id)
        self.assertEqual(derived.critical_point_ids, self.graph.critical_point_ids)
        np.testing.assert_allclose(derived.paths[0].samples.values, samples * BOHR_TO_ANGSTROM)
        np.testing.assert_allclose(self.graph.data.values[0], [.2 * BOHR_TO_ANGSTROM, -.3 * BOHR_TO_ANGSTROM, .4 * BOHR_TO_ANGSTROM])
        self.assertAlmostEqual(self.graph.connections[0].distance, BOHR_TO_ANGSTROM)
        self.assertAlmostEqual(self.graph.connections[0].path_length, 1.05 * BOHR_TO_ANGSTROM)
        self.assertGreater(np.linalg.norm(derived.paths[0].samples.values[-1] - self.graph.data.values[0]), 0.)
        self.assertEqual(batch.provenance[0].parent_ids, (self.graph.id,))
        self.assertEqual(derived.revision, self.parse(text).datasets[0].revision)

    def test_text_angstrom_header_is_not_misread_as_bohr(self):
        offset = np.array(self.document["structure"]["molecule_centering_vector"])
        samples = (np.array(((1., 0., 0.), (.5, .3, 0.), (0., 0., 0.))) + offset) * BOHR_TO_ANGSTROM
        batch = self.parse(flux_text(samples, start=samples[0], end=offset * BOHR_TO_ANGSTROM, unit="ang_"))
        np.testing.assert_allclose(batch.datasets[0].paths[0].samples.values, samples / BOHR_TO_ANGSTROM)

    def periodic(self):
        matrix = np.array(((2., .3, .1), (.2, 3., .4), (0., .1, 4.)))
        self.document["structure"] = {"is_molecule": False, "molecule_centering_vector": [0., 0., 0.],
                                       "crys_to_cart_matrix": matrix.ravel(order="F").tolist()}
        fractions = ((0., 0., 0.), (.8, 0., 0.), (.5, 0., 0.))
        for row, fractional in zip(self.document["critical_points"]["cell_cps"], fractions):
            row["fractional_coordinates"] = list(fractional)
            row["cartesian_coordinates"] = (matrix @ fractional).tolist()
        self.write_cp(unit="angstrom")
        samples = np.array(((.5, 0., 0.), (.75, .03, 0.), (1., 0., 0.)))
        text = flux_text(samples, start=(matrix @ samples[0]) * BOHR_TO_ANGSTROM,
            end=np.zeros(3), unit="ang_", matrix=matrix,
            start_fractional=samples[0], end_fractional=np.zeros(3))
        return text, samples, matrix

    def test_skew_periodic_coordinates_use_bohr_matrix_and_keep_unwrapped_image(self):
        text, samples, matrix = self.periodic()
        batch = self.parse(text)
        path = batch.datasets[0].paths[0]
        np.testing.assert_allclose(path.samples.values, samples @ matrix.T * BOHR_TO_ANGSTROM)
        metadata = dict(batch.provenance[0].parameters)["paths"][0]
        self.assertEqual(metadata["path_id"], str(path.id))
        self.assertEqual(metadata["start_id"], str(self.graph.critical_point_ids[2]))
        self.assertEqual(metadata["end_id"], str(self.graph.critical_point_ids[0]))
        self.assertEqual(metadata["start_lattice_vector"], (0, 0, 0))
        self.assertEqual(metadata["end_lattice_vector"], (1, 0, 0))

    def test_truncated_malformed_unknown_cp_and_far_endpoint_are_rejected(self):
        text, _ = self.molecular_text()
        variants = [text.replace("# End gradient path", "# truncated"),
                    text.replace("number of points: 3", "number of points: 4"),
                    text.replace("ncpcel: 1", "ncpcel: 0"),
                    text.replace("ncpcel: 1", "ncpcel: 99"),
                    text.replace("ncp: 1 ncpcel: 1", "ncp: 2 ncpcel: 1"),
                    text.replace("2.100000000000E-01", "NaN")]
        for variant in variants:
            with self.subTest(variant=variant[-80:]), self.assertRaises(ValueError):
                self.parse(variant)
        far = np.array(((1.2, -.3, .4), (.7, 0., .4), (.5, -.3, .4)))
        with self.assertRaisesRegex(ValueError, "sample endpoint"):
            self.parse(flux_text(far, start=far[0], end=(.2, -.3, .4), gap=.3))

    def test_matching_graph_cannot_be_replaced_by_a_nearby_unrelated_cp(self):
        text, _ = self.molecular_text()
        self.graph = replace(self.graph, critical_point_ids=tuple(uuid4() for _ in range(3)), connections=())
        with self.assertRaisesRegex(ValueError, "identities"):
            self.parse(text)

    def test_periodic_matrix_mismatch_fails(self):
        text, *_ = self.periodic()
        text = text.replace("2.000000000000E+00", "2.100000000000E+00")
        with self.assertRaisesRegex(ValueError, "matrices"):
            self.parse(text)

    def test_multiple_paths_and_fortran_d_exponents_preserve_order(self):
        text, samples = self.molecular_text()
        batch = self.parse(text + text.replace("E-01", "D-01"))
        self.assertEqual(len(batch.datasets[0].paths), 2)
        self.assertNotEqual(batch.datasets[0].paths[0].id, batch.datasets[0].paths[1].id)
        for path in batch.datasets[0].paths:
            np.testing.assert_allclose(path.samples.values, samples)

    def test_cbq_roundtrip_preserves_paths_and_per_path_image_provenance(self):
        text, *_ = self.periodic()
        batch = self.parse(text)
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(structures=(self.structure,), datasets=self.cp_batch.datasets,
                                   provenance=self.cp_batch.provenance))
        project.commit(batch)
        sidecar = self.directory / "topology.cbq"
        save_project(sidecar, project)
        restored = open_project(sidecar)
        try:
            graph = restored.datasets[batch.datasets[0].id]
            np.testing.assert_array_equal(graph.paths[0].samples.values, batch.datasets[0].paths[0].samples.values)
            record = restored.provenance[batch.provenance[0].id]
            metadata = dict(record.parameters)["paths"][0]
            self.assertEqual(metadata["path_id"], str(graph.paths[0].id))
            self.assertEqual(list(metadata["end_lattice_vector"]), [1, 0, 0])
        finally:
            close_project(restored)


if __name__ == "__main__":
    unittest.main()
