# Legacy `.blend` fixtures

These immutable fixtures are pre-migration evidence for the explicit legacy
scene migration gate. They were saved by Blender 5.1.2 from the released
ChemBlender tags below and were never opened or resaved by ChemBlender 2.3.

## Provenance

| File | ChemBlender source | Blender | Bytes | SHA-256 |
| --- | --- | --- | ---: | --- |
| `chemblender-2.1-molecule.blend` | `v2.1.1` / `2b72abf9e0e1f987014c8a95193bed06cc8dd988` | 5.1.2 | 153914 | `36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4` |
| `chemblender-2.2-crystal.blend` | `v2.2.0` / `cdc723649a28fe30cfa2ba956318444fc3783ec1` | 5.1.2 | 201029 | `f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a` |
| `chemblender-2.2-edited-scaffold.blend` | `v2.2.0` / `cdc723649a28fe30cfa2ba956318444fc3783ec1` | 5.1.2 | 154011 | `a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740` |

The source trees were exported directly from the local annotated tags. The
legacy readers used the release-pinned
`rdkit-2026.3.3-cp313-cp313-win_amd64.whl` with SHA-256
`f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48`.
The wheel was extracted into a short temporary path; no dependency was
installed or changed.

## Reproducible generation

1. Export `v2.1.1` with a `ChemBlender/` prefix and export the
   `ChemBlender/` tree from `v2.2.0`. Verify that the exported package files
   resolve to the commits in the provenance table.
2. Run Blender 5.1.2 with `--background --factory-startup`. Give every run
   unique short `BLENDER_USER_RESOURCES`, `TEMP`, and `TMP` directories. Put
   only the corresponding exported package and the verified RDKit wheel
   extraction on `sys.path`, import it as `ChemBlender`, assert its version,
   and call its released `register()`.
3. Remove the factory-startup objects and orphan data. Build each scaffold
   through the released `bpy.ops.chem.scaffold_build()` operator, apply the
   recorded release-era edits below, and save with
   `bpy.ops.wm.save_as_mainfile(compress=True)`.
4. In a new background process and a new isolated profile, reopen one fixture,
   register the same released package, and inspect the recorded objects,
   topology, attributes, custom properties, and CIF PropertyGroups. Do not
   save during inspection.

### 2.1 molecule input and display edits

The input is a hand-authored V2000 formaldehyde molecule:

| Atom | Element | Cartesian coordinate |
| --- | --- | --- |
| 1 | C | `(0.0000, 0.0000, 0.0000)` |
| 2 | O | `(1.2100, 0.0000, 0.0000)` |
| 3 | H | `(-0.6000, 0.9400, 0.0000)` |
| 4 | H | `(-0.6000, -0.9400, 0.0000)` |

Its bonds are `1-2` order 2, `1-3` order 1, and `1-4` order 1. After import,
the released `mesh.add_attr()` stores `atom_scale_f =
[1.25, 1.10, 0.80, 0.80]` and `bond_scale_f = [0.65, 0.85, 0.85]`.
The final collection/object are `Legacy 2.1 Molecule` and
`legacy_formaldehyde`; the Geometry Nodes modifier is
`GN_legacy_formaldehyde` using `NodeTree_legacy_formaldehyde`.

### 2.2 CIF-derived crystal

The hand-authored P1 CIF has cell `(5, 6, 7)` Å, angles
`(90, 100, 110)` degrees, symmetry operation `x,y,z`, and these asymmetric
atoms:

| Atom | Fractional coordinate | Occupancy | ADP | U11, U22, U33, U12, U13, U23 |
| --- | --- | ---: | --- | --- |
| Cu1 | `(0, 0, 0)` | 0.75 | Uani | `0.011, 0.013, 0.017, 0.003, 0.002, 0.001` |
| O1 | `(0.5, 0.5, 0.5)` | 1.00 | Uiso 0.020 | `0, 0, 0, 0, 0, 0` |

The 2.2 CIF reader generates `unit_partial_uij` and
`cell_edges_partial_uij`. Its zero-boundary behavior retains eight periodic
images of Cu1 plus O1. The released parser reads the Uij loop but does not
consume `_atom_site_occupancy`; therefore the generator transparently clears
the initial atom list and calls the released 2.2 `read.init_cif_data()` with
the same CIF values. That released function writes both `cif_original` and
`cif_current`. No 2.3 code participates.

The collection is `Legacy 2.2 Crystal`. Expected recovery includes cell
parameters, P1 / SG 1 / symmetry operations, both CIF PropertyGroups,
occupancy and Uij, the thermal-ellipsoid attributes `u_scale`, `u_v1`,
`u_v2`, and `u_v3`, and the unit-cell object properties.

### 2.2 edited scaffold

The base input is a hand-authored V2000 ethanol scaffold with coordinates:

| Atom | Element | Cartesian coordinate |
| --- | --- | --- |
| 1 | C | `(-0.7500, 0.0000, 0.0000)` |
| 2 | C | `(0.7500, 0.0000, 0.0000)` |
| 3 | O | `(1.4300, 1.1700, 0.0000)` |
| 4 | H | `(-1.1200, -0.5200, 0.8900)` |
| 5 | H | `(-1.1200, -0.5200, -0.8900)` |
| 6 | H | `(-1.1200, 1.0300, 0.0000)` |
| 7 | H | `(1.1200, -0.5200, 0.8900)` |
| 8 | H | `(1.1200, -0.5200, -0.8900)` |
| 9 | H | `(2.3800, 1.0000, 0.0000)` |

The eight single bonds are `1-2`, `2-3`, `1-4`, `1-5`, `1-6`, `2-7`,
`2-8`, and `3-9`. Release 2.2 `mesh.add_attr()` then changes atom 1 to
atomic number 7, moves it to `(-1.0, 0.15, 0)`, sets its scale to 1.4 and
colour to `(0.10, 0.70, 0.65, 1.0)`, and changes bond 1 to order 2, scale
0.6, and dashed. The collection/object are
`Legacy 2.2 Edited Scaffold` and `legacy_edited_ethanol`.

## Redistribution review

The chemical inputs above were authored solely for these tests. The local
node groups and materials come from the tagged ChemBlender GPL-3.0-or-later
source already distributed by this repository. Independent reopen inspection
found no linked libraries and no external file images in any fixture.
Therefore the three fixtures contain no third-party dataset or non-
redistributable external asset.

## Machine-readable companion metadata

`tests.test_legacy_fixture_inventory` decodes this JSON and compares it with
hard-coded reviewed hashes, actual byte sizes, and the expected recovery
surface.

<!-- fixture-metadata-begin -->
```json
{
  "schema_version": 1,
  "redistributable": true,
  "fixtures": [
    {
      "file": "chemblender-2.1-molecule.blend",
      "sha256": "36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4",
      "bytes": 153914,
      "chemblender_version": "2.1.1",
      "chemblender_commit": "2b72abf9e0e1f987014c8a95193bed06cc8dd988",
      "blender_version": "5.1.2",
      "collections": [
        "Legacy 2.1 Molecule"
      ],
      "objects": [
        "legacy_formaldehyde"
      ],
      "expected_recoverable_fields": [
        "object[\"Type\"]",
        "object[\"Elements\"]",
        "mesh.vertices",
        "mesh.edges",
        "mesh.attributes.atomic_num",
        "mesh.attributes.bond_order",
        "mesh.attributes.atom_scale_f",
        "mesh.attributes.bond_scale_f",
        "geometry_nodes"
      ]
    },
    {
      "file": "chemblender-2.2-crystal.blend",
      "sha256": "f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a",
      "bytes": 201029,
      "chemblender_version": "2.2.0",
      "chemblender_commit": "cdc723649a28fe30cfa2ba956318444fc3783ec1",
      "blender_version": "5.1.2",
      "collections": [
        "Legacy 2.2 Crystal"
      ],
      "objects": [
        "cell_edges_partial_uij",
        "unit_partial_uij"
      ],
      "expected_recoverable_fields": [
        "object[\"Type\"]",
        "object[\"cell lengths\"]",
        "object[\"cell angles\"]",
        "object[\"space group\"]",
        "object[\"SG No.\"]",
        "object[\"symops\"]",
        "object.cif_original.atom_count",
        "object.cif_original.atoms[].label",
        "object.cif_original.atoms[].element",
        "object.cif_original.atoms[].x",
        "object.cif_original.atoms[].y",
        "object.cif_original.atoms[].z",
        "object.cif_original.atoms[].occupancy",
        "object.cif_original.atoms[].u_iso_equiv",
        "object.cif_original.atoms[].adp_type",
        "object.cif_original.atoms[].u11",
        "object.cif_original.atoms[].u22",
        "object.cif_original.atoms[].u33",
        "object.cif_original.atoms[].u12",
        "object.cif_original.atoms[].u13",
        "object.cif_original.atoms[].u23",
        "object.cif_current.atom_count",
        "object.cif_current.atoms[].label",
        "object.cif_current.atoms[].element",
        "object.cif_current.atoms[].x",
        "object.cif_current.atoms[].y",
        "object.cif_current.atoms[].z",
        "object.cif_current.atoms[].occupancy",
        "object.cif_current.atoms[].u_iso_equiv",
        "object.cif_current.atoms[].adp_type",
        "object.cif_current.atoms[].u11",
        "object.cif_current.atoms[].u22",
        "object.cif_current.atoms[].u33",
        "object.cif_current.atoms[].u12",
        "object.cif_current.atoms[].u13",
        "object.cif_current.atoms[].u23",
        "mesh.vertices",
        "mesh.vertices[].co",
        "mesh.attributes.atomic_num",
        "mesh.attributes.u_scale",
        "mesh.attributes.u_v1",
        "mesh.attributes.u_v2",
        "mesh.attributes.u_v3",
        "cell_edges.custom_properties"
      ],
      "expected_values": {
        "cif_original": {
          "atom_count": 2,
          "atoms": [
            {
              "label": "Cu1",
              "element": "Cu",
              "x": 0.0,
              "y": 0.0,
              "z": 0.0,
              "occupancy": 0.75,
              "u_iso_equiv": 0.012000000104308128,
              "adp_type": "Uani",
              "u11": 0.010999999940395355,
              "u22": 0.013000000268220901,
              "u33": 0.017000000923871994,
              "u12": 0.003000000026077032,
              "u13": 0.0020000000949949026,
              "u23": 0.0010000000474974513
            },
            {
              "label": "O1",
              "element": "O",
              "x": 0.5,
              "y": 0.5,
              "z": 0.5,
              "occupancy": 1.0,
              "u_iso_equiv": 0.019999999552965164,
              "adp_type": "Uiso",
              "u11": 0.0,
              "u22": 0.0,
              "u33": 0.0,
              "u12": 0.0,
              "u13": 0.0,
              "u23": 0.0
            }
          ]
        },
        "cif_current": {
          "atom_count": 2,
          "atoms": [
            {
              "label": "Cu1",
              "element": "Cu",
              "x": 0.0,
              "y": 0.0,
              "z": 0.0,
              "occupancy": 0.75,
              "u_iso_equiv": 0.012000000104308128,
              "adp_type": "Uani",
              "u11": 0.010999999940395355,
              "u22": 0.013000000268220901,
              "u33": 0.017000000923871994,
              "u12": 0.003000000026077032,
              "u13": 0.0020000000949949026,
              "u23": 0.0010000000474974513
            },
            {
              "label": "O1",
              "element": "O",
              "x": 0.5,
              "y": 0.5,
              "z": 0.5,
              "occupancy": 1.0,
              "u_iso_equiv": 0.019999999552965164,
              "adp_type": "Uiso",
              "u11": 0.0,
              "u22": 0.0,
              "u33": 0.0,
              "u12": 0.0,
              "u13": 0.0,
              "u23": 0.0
            }
          ]
        },
        "mesh_vertices": [
          [
            0.0,
            0.0,
            0.0
          ],
          [
            -1.215537190437317,
            -0.4424193799495697,
            6.8794426918029785
          ],
          [
            -2.0521209239959717,
            5.638155937194824,
            0.0
          ],
          [
            -3.267657995223999,
            5.195736408233643,
            6.8794426918029785
          ],
          [
            5.0,
            0.0,
            0.0
          ],
          [
            3.7844626903533936,
            -0.4424193799495697,
            6.8794426918029785
          ],
          [
            2.9478790760040283,
            5.638155937194824,
            0.0
          ],
          [
            1.7323418855667114,
            5.195736408233643,
            6.8794426918029785
          ],
          [
            0.8661709427833557,
            2.5978682041168213,
            3.4397213459014893
          ]
        ]
      }
    },
    {
      "file": "chemblender-2.2-edited-scaffold.blend",
      "sha256": "a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740",
      "bytes": 154011,
      "chemblender_version": "2.2.0",
      "chemblender_commit": "cdc723649a28fe30cfa2ba956318444fc3783ec1",
      "blender_version": "5.1.2",
      "collections": [
        "Legacy 2.2 Edited Scaffold"
      ],
      "objects": [
        "legacy_edited_ethanol"
      ],
      "expected_recoverable_fields": [
        "object[\"Type\"]",
        "object[\"Elements\"]",
        "mesh.vertices",
        "mesh.edges",
        "mesh.attributes.atomic_num",
        "mesh.attributes.bond_order",
        "mesh.attributes.atom_scale_f",
        "mesh.attributes.bond_scale_f",
        "mesh.attributes.colour",
        "mesh.attributes.dashed",
        "geometry_nodes"
      ]
    }
  ]
}
```
<!-- fixture-metadata-end -->
