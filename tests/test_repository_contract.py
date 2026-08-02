import ast
import re
import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
WHEELS = (
    "rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
    "gemmi-0.7.5-cp313-cp313-win_amd64.whl",
)


class RepositoryContractTests(unittest.TestCase):
    def test_extension_layout_and_manifest(self):
        manifest = tomllib.loads(
            (EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["id"], "chemblender")
        self.assertEqual(manifest["version"], "2.4.0-rc.1")
        self.assertEqual(manifest["blender_version_min"], "5.1.0")
        self.assertEqual(manifest["platforms"], ["windows-x64"])
        self.assertEqual(
            manifest["wheels"],
            [f"./wheels/{wheel}" for wheel in WHEELS],
        )
        self.assertLessEqual(len(manifest["permissions"]["files"]), 64)
        self.assertEqual(
            manifest["permissions"]["files"],
            "Read selected files and write requested visualization caches",
        )
        self.assertIn("network", manifest["permissions"])
        self.assertLessEqual(len(manifest["permissions"]["network"]), 64)
        self.assertIn("scripts/", manifest["build"]["paths_exclude_pattern"])
        self.assertTrue((EXTENSION / "__init__.py").exists())
        self.assertTrue((EXTENSION / "scripts" / "build_extension.py").exists())

    def test_generated_and_local_dependencies_are_not_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files", "ChemBlender/wheels/*.whl", ".agents/cache/**"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(tracked, "")

    def test_molecular_fixture_line_endings_are_cross_platform_stable(self):
        attributes = subprocess.run(
            [
                "git",
                "check-attr",
                "text",
                "eol",
                "--",
                "tests/fixtures/mol/water-v2000.mol",
                "tests/fixtures/sdf/records.sdf",
                "tests/fixtures/sdf/crlf.sdf",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

        self.assertIn(
            "tests/fixtures/mol/water-v2000.mol: text: set",
            attributes,
        )
        self.assertIn(
            "tests/fixtures/mol/water-v2000.mol: eol: lf",
            attributes,
        )
        self.assertIn("tests/fixtures/sdf/records.sdf: text: set", attributes)
        self.assertIn("tests/fixtures/sdf/records.sdf: eol: lf", attributes)
        self.assertIn("tests/fixtures/sdf/crlf.sdf: text: unset", attributes)

    def test_runtime_source_has_no_package_install(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in EXTENSION.rglob("*.py")
            if "scripts" not in path.parts
        ).lower()
        self.assertNotIn("pip install", source)
        self.assertNotIn('"-m", "pip"', source)

    def test_extension_uses_one_explicit_registration_entrypoint(self):
        init_source = (EXTENSION / "__init__.py").read_text(encoding="utf-8")
        auto_load_source = (
            EXTENSION / "auto_load.py"
        ).read_text(encoding="utf-8")
        registration_source = (
            EXTENSION / "runtime" / "registration.py"
        ).read_text(encoding="utf-8")
        auto_load_functions = {
            node.name
            for node in ast.parse(auto_load_source).body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertNotIn("bl_info", init_source)
        self.assertIn("register_extension(__package__)", init_source)
        self.assertIn("unregister_extension()", init_source)
        self.assertIn("REGISTER_MODULE_NAMES", registration_source)
        self.assertNotIn("ChemBlender", registration_source)
        self.assertNotIn("bl_ext.user_default", registration_source)
        self.assertNotIn("pkgutil", auto_load_source)
        self.assertFalse(
            {
                "init",
                "register",
                "unregister",
                "clear_submodule_cache",
                "get_all_submodules",
                "iter_submodules",
                "iter_submodule_names",
            }
            & auto_load_functions
        )
        self.assertTrue(
            {
                "get_ordered_classes_to_register",
                "_safe_register_class",
                "_safe_unregister_class",
            }.issubset(auto_load_functions)
        )

    def test_package_workflow_pins_and_verifies_release_inputs(self):
        workflow = (ROOT / ".github" / "workflows" / "extension-package.yml").read_text(
            encoding="utf-8"
        )
        for action in (
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        ):
            self.assertIn(action, workflow)
        self.assertIn("permissions:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("timeout-minutes:", workflow)
        self.assertIn("BLENDER_USER_RESOURCES", workflow)
        self.assertIn("--python-exit-code 1", workflow)
        self.assertIn("if: github.ref_type == 'tag'", workflow)
        self.assertIn('$expectedTag = "v$manifestVersion"', workflow)
        self.assertIn("if ($env:GITHUB_REF_NAME -ne $expectedTag)", workflow)
        self.assertNotIn("TrimStart", workflow)
        self.assertIn("blender-5.1.2.sha256", workflow)
        self.assertIn("f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48", workflow)
        self.assertIn(
            "ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d",
            workflow,
        )

    def test_package_workflow_derives_names_from_release_metadata(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-package.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("chemblender-2.2.0", workflow)
        metadata_step = workflow.split(
            "\n      - name: Read release metadata\n", 1
        )[1].split("\n      - name: Verify changelog entry\n", 1)[0]
        self.assertNotIn("blender_manifest.toml", metadata_step)
        self.assertEqual(workflow.count("release_metadata.py"), 1)
        self.assertIn("id: release_metadata", workflow)
        self.assertIn(
            "release_metadata.py --extension-root ChemBlender --format json",
            workflow,
        )
        self.assertIn("ConvertFrom-Json", workflow)
        self.assertIn("[IO.File]::AppendAllText(", workflow)
        self.assertIn("$env:GITHUB_OUTPUT", workflow)
        self.assertIn("[Text.UTF8Encoding]::new($false)", workflow)
        for name in (
            "version",
            "package_name",
            "checksum_name",
            "artifact_name",
        ):
            self.assertIn(f'"{name}=$($metadata.{name})"', workflow)

        self.assertEqual(
            workflow.count("steps.release_metadata.outputs.version"),
            3,
        )
        self.assertEqual(
            workflow.count("steps.release_metadata.outputs.package_name"),
            2,
        )
        self.assertEqual(
            workflow.count("steps.release_metadata.outputs.checksum_name"),
            2,
        )
        self.assertEqual(
            workflow.count("steps.release_metadata.outputs.artifact_name"),
            1,
        )
        self.assertIn('"$hash  $packageName`n"', workflow)

    def test_package_workflow_runs_tests_with_blender_bundled_python(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-package.yml"
        ).read_text(encoding="utf-8")
        download_step = workflow.split(
            "\n      - name: Download pinned extension wheels\n", 1
        )[1].split("\n      - name: Download Blender 5.1.2\n", 1)[0]
        step = workflow.split(
            "\n      - name: Test, validate, build, and install\n", 1
        )[1].split("\n      - uses:", 1)[0]

        self.assertIn('"RDKIT_WHEEL=$wheelPath`n"', download_step)
        self.assertIn('"GEMMI_WHEEL=$wheelPath`n"', download_step)
        self.assertIn("$env:GITHUB_ENV", download_step)
        self.assertIn(
            "$blenderPython = Join-Path (Split-Path $blender) "
            '"5.1/python/bin/python.exe"',
            step,
        )
        self.assertIn(
            "& $blenderPython -m pip install --disable-pip-version-check "
            "--no-index --no-deps --target $testSite "
            "$env:RDKIT_WHEEL $env:GEMMI_WHEEL",
            step,
        )
        self.assertIn("$env:PYTHONPATH = $testSite", step)
        self.assertIn("Remove-Item Env:PYTHONPATH", step)
        self.assertIn(
            '& $blenderPython -m unittest discover -s tests -p "test_*.py" -v',
            step,
        )
        self.assertIn(
            "build_extension.py --python $blenderPython --blender $blender",
            step,
        )
        self.assertIn(
            'if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }',
            step,
        )
        self.assertIn(
            'if ($LASTEXITCODE -ne 0) { throw "Extension build failed" }',
            step,
        )
        self.assertIn("$env:TEMP = $env:RUNNER_TEMP", step)
        self.assertIn("$env:TMP = $env:RUNNER_TEMP", step)
        test_command = step.index("& $blenderPython -m unittest discover")
        self.assertLess(step.index("$env:TEMP = $env:RUNNER_TEMP"), test_command)
        self.assertLess(step.index("$env:TMP = $env:RUNNER_TEMP"), test_command)
        self.assertLess(step.index("$env:PYTHONPATH = $testSite"), test_command)
        self.assertLess(test_command, step.index("Remove-Item Env:PYTHONPATH"))
        self.assertLess(
            step.index("Remove-Item Env:PYTHONPATH"),
            step.index("& $blenderPython ChemBlender/scripts/build_extension.py"),
        )

    def test_package_workflow_retains_tag_artifacts_for_review(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-package.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "retention-days: ${{ github.ref_type == 'tag' && 30 || 14 }}",
            workflow,
        )
        self.assertEqual(workflow.count("retention-days:"), 1)

    def test_blender_smoke_covers_release_artifact(self):
        smoke = (ROOT / "tests" / "blender_smoke.py").read_text(encoding="utf-8")
        for expected in (
            "ZipFile",
            "Chem_Nodes.blend",
            "Chem_Nodes_En.blend",
            "EmbedMolecule",
            "assert_signed_surface_revision_actions",
            '"inspect_existing"',
            "CHEMBLENDER_OT_diagnostic_page",
            "session_ui._save_pre_handler(None)",
            "--keep-enabled",
        ):
            self.assertIn(expected, smoke)

    def test_blender_smoke_unloads_active_grid_worker_only_at_final_exit(self):
        smoke = (ROOT / "tests" / "blender_smoke.py").read_text(encoding="utf-8")
        tree = ast.parse(smoke)
        unload = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "assert_grid_unload_cancels_active_worker"
        )
        unload_source = ast.get_source_segment(smoke, unload)
        self.assertEqual(unload_source.count("addon_disable("), 1)
        self.assertNotIn("addon_enable(", unload_source)

        dependency_probe = smoke.index("from rdkit.Chem import AllChem")
        keep_enabled_branch = smoke.index("if keep_enabled:", dependency_probe)
        final_unload = smoke.index(
            "assert_grid_unload_cancels_active_worker(module_key)",
            keep_enabled_branch,
        )
        self.assertLess(dependency_probe, keep_enabled_branch)
        self.assertLess(keep_enabled_branch, final_unload)
        self.assertNotIn(
            "addon_disable(",
            smoke[keep_enabled_branch:],
        )

    def test_release_workflow_is_manual_and_deterministic(self):
        workflow = (ROOT / ".github" / "workflows" / "extension-release.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("pull_request:", trigger)
        self.assertNotIn("workflow_run:", trigger)
        self.assertNotRegex(trigger, r"(?m)^\s+push:")
        for expected in (
            "tag:",
            "publish:",
            "type: boolean",
            "default: false",
            "actions: read",
            "contents: read",
            "contents: write",
            "environment: release",
            "if: ${{ inputs.publish }}",
            "gh api --paginate --slurp",
            "actions/workflows/extension-package.yml/runs?event=push&status=success&head_sha=$tag_commit&branch=$RELEASE_TAG&per_page=100",
            "actions/artifacts/$ARTIFACT_ID/zip",
            "gh release create",
            "--draft",
            ".digest",
            "gh release edit",
            "--draft=false --latest",
        ):
            self.assertIn(expected, workflow)
        self.assertEqual(workflow.count("verify_release_artifact.py"), 4)
        self.assertEqual(workflow.count("path: tag-source"), 2)
        self.assertEqual(workflow.count("--extension-root tag-source/ChemBlender"), 5)
        self.assertEqual(workflow.count("--metadata-mode release-assets"), 2)
        self.assertEqual(
            workflow.count("--budget tag-source/.github/artifact-budgets.json"), 4
        )
        self.assertEqual(
            workflow.count('cp -- "dist/$PACKAGE_NAME" "dist/$CHECKSUM_NAME" release-assets/'),
            2,
        )
        self.assertIn("git -C tag-source", workflow)
        self.assertEqual(workflow.count("contents: write"), 1)
        actions = re.findall(r"uses:\s+([^\s]+)", workflow)
        self.assertTrue(actions)
        for action in actions:
            self.assertRegex(action, r"@[0-9a-f]{40}$")

    def test_release_workflow_reverifies_complete_package_artifact_before_publish_assets(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("--select-package-run", workflow)
        self.assertIn("--select-package-artifact", workflow)
        for job in ("verify", "publish"):
            job_text = workflow.split(f"\n  {job}:", 1)[1]
            if job == "verify":
                job_text = job_text.split("\n  publish:", 1)[0]
            step = job_text.split("- name: Download and", 1)[1].split(
                "\n      - name:", 1
            )[0]
            package_ci = step.index("--metadata-mode package-ci")
            copied_assets = step.index(
                'cp -- "dist/$PACKAGE_NAME" "dist/$CHECKSUM_NAME" release-assets/'
            )
            release_assets = step.index("--metadata-mode release-assets")
            self.assertLess(package_ci, copied_assets)
            self.assertLess(copied_assets, release_assets)

    def test_release_workflow_paginates_and_extracts_only_selected_artifact(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("gh run list", workflow)
        self.assertNotIn("--limit 10", workflow)
        self.assertEqual(workflow.count("gh api --paginate --slurp"), 2)
        self.assertIn(
            "actions/workflows/extension-package.yml/runs?event=push&status=success&head_sha=$tag_commit&branch=$RELEASE_TAG&per_page=100",
            workflow,
        )
        self.assertIn(
            "actions/runs/$run_id/artifacts?per_page=100",
            workflow,
        )
        self.assertIn("jq -er '.run_id'", workflow)
        self.assertIn("jq -ce '{artifacts: [.[].artifacts[]]}'", workflow)
        self.assertIn(
            "artifact_id: ${{ steps.release_info.outputs.artifact_id }}",
            workflow,
        )
        self.assertIn("ARTIFACT_ID: ${{ needs.verify.outputs.artifact_id }}", workflow)
        self.assertNotIn("gh run download", workflow)
        self.assertIn("actions/artifacts/$ARTIFACT_ID/zip", workflow)
        for job in ("verify", "publish"):
            job_text = workflow.split(f"\n  {job}:", 1)[1]
            if job == "verify":
                job_text = job_text.split("\n  publish:", 1)[0]
            step = job_text.split("- name: Download and", 1)[1].split(
                "\n      - name:", 1
            )[0]
            self.assertIn('BUNDLE="bundle.zip"', step)
            self.assertIn('unzip -Z1 "$BUNDLE"', step)
            self.assertIn('unzip -q "$BUNDLE" -d dist', step)
            self.assertIn(
                'if [[ "${#bundle_members[@]}" -ne "${#expected_members[@]}" ]]',
                step,
            )
            self.assertIn('for index in "${!expected_sorted[@]}"; do', step)
            self.assertIn("unexpected, duplicate, directory, or unsafe members", step)
            for name in (
                '"$PACKAGE_NAME"',
                '"$CHECKSUM_NAME"',
                '"wheel-inventory.json"',
                '"wheel-license-copy-list.json"',
                '"artifact-size.json"',
            ):
                self.assertIn(name, step)

    def test_release_workflow_requires_default_branch_dispatch_ref(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")

        verify_job = workflow.split("\n  verify:", 1)[1].split("\n  publish:", 1)[0]
        steps = verify_job.split("\n    steps:\n", 1)[1]
        first_step = re.search(r"(?m)^      - (.+)$", steps)
        self.assertIsNotNone(first_step)
        self.assertEqual(
            first_step.group(1),
            "name: Require default-branch workflow ref",
        )
        self.assertIn("- name: Require default-branch workflow ref", workflow)
        self.assertIn("WORKFLOW_REF: ${{ github.ref }}", workflow)
        self.assertIn(
            "DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}",
            workflow,
        )
        self.assertIn('expected="refs/heads/$DEFAULT_BRANCH"', workflow)
        self.assertIn('if [[ "$WORKFLOW_REF" != "$expected" ]]', workflow)

    def test_release_documentation_dispatches_release_workflow_from_main(self):
        documentation = (
            ROOT / "docs" / "development" / "branch-and-release.md"
        ).read_text(encoding="utf-8")
        lines = documentation.splitlines()
        dispatches = []
        for index, line in enumerate(lines):
            if not line.startswith("gh workflow run extension-release.yml"):
                continue
            command = line
            while command.rstrip().endswith("`"):
                index += 1
                command = f"{command} {lines[index].strip()}"
            dispatches.append(command)

        self.assertEqual(len(dispatches), 2)
        for command in dispatches:
            self.assertEqual(
                re.findall(r"(?:^|\s)--ref\s+(\S+)", command),
                ["main"],
            )

    def test_release_workflow_derives_identity_from_tagged_metadata(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")

        self.assertEqual(workflow.count("release_metadata.py"), 3)
        self.assertIn(
            "python3 ChemBlender/scripts/release_metadata.py",
            workflow,
        )
        self.assertNotIn(
            "python3 tag-source/ChemBlender/scripts/release_metadata.py",
            workflow,
        )
        self.assertIn(
            "--extension-root tag-source/ChemBlender --format json --include-channel",
            workflow,
        )
        self.assertNotIn("import tomllib", workflow)
        self.assertNotRegex(workflow, r"=~ \^v\\?\[0-9")
        self.assertNotIn('artifact_name="chemblender-', workflow)
        self.assertNotIn('package_name="chemblender-', workflow)
        self.assertNotIn('checksum_name="chemblender-', workflow)
        self.assertNotIn("build_extension.py", workflow)
        for name in (
            "version",
            "artifact_name",
            "package_name",
            "checksum_name",
            "channel",
            "is_prerelease",
        ):
            self.assertIn(
                f"""{name}="$(jq -r '.{name}' <<< "$metadata_json")\"""",
                workflow,
            )
            self.assertIn(f'echo "{name}=${name}"', workflow)
            self.assertIn(
                f"{name}: ${{{{ steps.release_info.outputs.{name} }}}}",
                workflow,
            )
        self.assertIn('expected_tag="v$version"', workflow)
        self.assertIn('if [[ "$RELEASE_TAG" != "$expected_tag" ]]', workflow)
        self.assertIn(
            "actions/workflows/extension-package.yml/runs?event=push&status=success&head_sha=$tag_commit&branch=$RELEASE_TAG&per_page=100",
            workflow,
        )
        self.assertIn(
            '--select-package-run --tag "$RELEASE_TAG" --tag-commit "$tag_commit"',
            workflow,
        )
        self.assertIn(
            '--select-package-artifact --artifact-name "$artifact_name"',
            workflow,
        )
        self.assertNotIn("select(.name == $name and .expired == false)", workflow)
        self.assertNotIn("if [[ -f tag-source/CHANGELOG.md ]]", workflow)
        self.assertEqual(workflow.count("--changelog tag-source/CHANGELOG.md"), 2)
        self.assertEqual(workflow.count("cmp release-notes.md tag-release-notes.md"), 2)

    def test_release_workflow_binds_publish_to_verified_tag_commit(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")
        publish = workflow.split("\n  publish:", 1)[1]

        self.assertIn(
            "tag_commit: ${{ steps.release_info.outputs.tag_commit }}",
            workflow,
        )
        self.assertIn('echo "tag_commit=$tag_commit"', workflow)
        self.assertIn(
            "ref: ${{ needs.verify.outputs.tag_commit }}",
            publish,
        )
        self.assertNotIn("ref: ${{ inputs.tag }}", publish)
        self.assertIn(
            "VERIFIED_TAG_COMMIT: ${{ needs.verify.outputs.tag_commit }}",
            publish,
        )

        create_step = publish.split("- name: Create verified GitHub Release", 1)[1]
        required_in_order = (
            'git -C tag-source fetch --force origin "refs/tags/$RELEASE_TAG:refs/tags/$RELEASE_TAG"',
            'git -C tag-source cat-file -t "refs/tags/$RELEASE_TAG"',
            'current_tag_commit="$(git -C tag-source rev-list -n 1 "refs/tags/$RELEASE_TAG")"',
            'if [[ "$current_tag_commit" != "$VERIFIED_TAG_COMMIT" ]]',
            'gh release create "$RELEASE_TAG"',
        )
        positions = [create_step.index(text) for text in required_in_order]
        self.assertEqual(positions, sorted(positions))

    def test_release_workflow_keeps_prereleases_out_of_latest(self):
        workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "IS_PRERELEASE: ${{ needs.verify.outputs.is_prerelease }}",
            workflow,
        )
        self.assertIn("release_flags+=(--prerelease)", workflow)
        self.assertIn('"${release_flags[@]}"', workflow)
        publish_branch = re.search(
            r'if \[\[ "\$IS_PRERELEASE" == "true" \]\]; then'
            r"(?P<prerelease>.*?gh release edit.*?)"
            r"else(?P<final>.*?gh release edit.*?)"
            r"\n\s*fi",
            workflow,
            re.DOTALL,
        )
        self.assertIsNotNone(publish_branch)
        prerelease = publish_branch.group("prerelease")
        final = publish_branch.group("final")
        self.assertIn("--draft=false --prerelease --verify-tag", prerelease)
        self.assertNotIn("--latest", prerelease)
        self.assertIn("--draft=false --latest --verify-tag", final)
        self.assertNotIn("--prerelease", final)
        self.assertGreaterEqual(workflow.count("isPrerelease"), 3)
        self.assertIn('!= "$RELEASE_TAG"', prerelease)
        self.assertIn('== "$RELEASE_TAG"', final)

    def test_release_documentation_covers_prerelease_review_window(self):
        documentation = (
            ROOT / "docs" / "development" / "branch-and-release.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "vMAJOR.MINOR.PATCH-alpha.N",
            documentation,
        )
        self.assertIn("vMAJOR.MINOR.PATCH-beta.N", documentation)
        self.assertIn("vMAJOR.MINOR.PATCH-rc.N", documentation)
        self.assertIn("30 days", documentation)
        self.assertIn("14 days", documentation)
        self.assertIn("never marked latest", documentation)
        self.assertIn("manual", documentation.lower())

    def test_changelog_drives_release_notes(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        manifest = tomllib.loads(
            (EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8")
        )
        self.assertIn(f"## [{manifest['version']}] - ", changelog)

        package_workflow = (
            ROOT / ".github" / "workflows" / "extension-package.yml"
        ).read_text(encoding="utf-8")
        release_workflow = (
            ROOT / ".github" / "workflows" / "extension-release.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("extract_release_notes.py", package_workflow)
        self.assertGreaterEqual(release_workflow.count("extract_release_notes.py"), 2)
        self.assertIn("--notes-file release-notes.md", release_workflow)
        self.assertNotIn("--generate-notes", release_workflow)

if __name__ == "__main__":
    unittest.main()
