from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tests" / "check_committed_format_range.py"
ZERO_SHA = "0" * 40


class CommittedFormatRangeTests(unittest.TestCase):
    def _git(self, cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *args),
            cwd=cwd,
            check=check,
            capture_output=True,
            encoding="utf-8",
        )

    def _repository(self, root: Path, name: str) -> Path:
        repository = root / name
        repository.mkdir()
        self._git(repository, "init", "--initial-branch=main")
        self._git(repository, "config", "user.email", "ci@example.invalid")
        self._git(repository, "config", "user.name", "CI Contract")
        return repository

    def _commit(self, repository: Path, filename: str, contents: str, message: str) -> str:
        (repository / filename).write_text(contents, encoding="utf-8", newline="\n")
        self._git(repository, "add", filename)
        self._git(repository, "commit", "-m", message)
        return self._git(repository, "rev-parse", "HEAD").stdout.strip()

    def _run_checker(
        self,
        repository: Path,
        *,
        event: str,
        pull_request_base: str = "",
        push_before: str = "",
        default_branch: str = "main",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (
                sys.executable,
                str(CHECKER),
                "--event-name",
                event,
                "--pull-request-base",
                pull_request_base,
                "--push-before",
                push_before,
                "--default-branch",
                default_branch,
            ),
            cwd=repository,
            check=False,
            capture_output=True,
            encoding="utf-8",
        )

    def test_known_event_base_checks_earlier_committed_whitespace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = self._repository(Path(temp_dir), "repository")
            base = self._commit(repository, "base.txt", "base\n", "base")
            self._commit(repository, "bad.txt", "bad  \n", "bad")
            self._commit(repository, "later.txt", "later\n", "later")

            result = self._run_checker(
                repository,
                event="push",
                push_before=base,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trailing whitespace", result.stdout)

    def test_unreachable_event_base_is_fetched_from_bare_origin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._repository(root, "source")
            base = self._commit(source, "base.txt", "base\n", "base")
            self._commit(source, "bad.txt", "bad  \n", "bad")
            origin = root / "origin.git"
            self._git(root, "clone", "--bare", str(source), str(origin))
            clone = root / "clone"
            self._git(root, "clone", "--depth=1", origin.as_uri(), str(clone))

            self.assertNotEqual(
                self._git(clone, "cat-file", "-e", f"{base}^{{commit}}", check=False).returncode,
                0,
            )
            result = self._run_checker(clone, event="push", push_before=base)
            fetched = self._git(clone, "cat-file", "-e", f"{base}^{{commit}}", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trailing whitespace", result.stdout)
        self.assertEqual(fetched.returncode, 0, fetched.stderr)

    def test_nonexistent_event_base_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = self._repository(Path(temp_dir), "repository")
            self._commit(repository, "base.txt", "base\n", "base")
            self._commit(repository, "head.txt", "clean\n", "head")

            result = self._run_checker(
                repository,
                event="pull_request",
                pull_request_base="f" * 40,
            )

        self.assertNotEqual(result.returncode, 0)

    def test_zero_push_before_checks_all_new_branch_commits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = self._repository(root, "repository")
            self._commit(repository, "base.txt", "base\n", "base")
            origin = root / "origin.git"
            self._git(root, "clone", "--bare", str(repository), str(origin))
            self._git(repository, "remote", "add", "origin", str(origin))
            self._git(repository, "fetch", "origin", "main:refs/remotes/origin/main")
            self._git(repository, "switch", "-c", "topic")
            self._commit(repository, "bad.txt", "bad  \n", "bad")
            self._commit(repository, "later.txt", "later\n", "later")

            result = self._run_checker(
                repository,
                event="push",
                push_before=ZERO_SHA,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("trailing whitespace", result.stdout)

    def test_clean_range_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = self._repository(Path(temp_dir), "repository")
            base = self._commit(repository, "base.txt", "base\n", "base")
            self._commit(repository, "head.txt", "clean\n", "head")

            result = self._run_checker(
                repository,
                event="pull_request",
                pull_request_base=base,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
