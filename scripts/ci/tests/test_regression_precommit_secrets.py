"""Exercise the secret guard against real Git indexes and commit ranges, without network access."""

import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / "scripts/ci/precommit_secrets.py"


class SecretGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, capture_output=True, timeout=10
        )

    def stage(self, content, name="sample.txt"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git("add", "--", name)
        return path

    def record_head(self):
        # Build a baseline tree directly; no commit or hook bypass is needed.
        tree = self.git("write-tree").stdout.strip().decode()
        who = ["-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
        commit = self.git(*who, "commit-tree", tree, "-m", "test baseline").stdout.strip()
        self.git("update-ref", "HEAD", commit.decode())

    def invoke(self, *args):
        return subprocess.run(args, cwd=self.repo, capture_output=True, text=True, timeout=10)

    def scan(self, message=None):
        args = ["python3", str(GUARD)]
        if message is not None:
            path = self.repo / "message"
            path.write_text(message)
            args.append(str(path))
        return self.invoke(*args)

    def assert_blocked(self, result, content):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Secret guard:", result.stderr)
        self.assertNotIn(content.strip(), result.stdout + result.stderr)

    def test_clean_index_and_message_pass(self):
        self.stage('title = "Public example"\n')
        self.assertEqual(self.scan().returncode, 0)
        self.assertEqual(self.scan("fix: improve input validation\n").returncode, 0)

    def test_empty_index_passes(self):
        self.assertEqual(self.scan().returncode, 0)

    def test_obvious_fake_tokens_block_in_index_and_message(self):
        tokens = [
            "AKIA" + "A" * 16,
            "ghp_" + "A" * 36,
            "github_pat_" + "A" * 82,
            "xoxb-" + "1234567890-" * 2 + "A" * 24,
            "-----BEGIN " + "RSA PRIVATE KEY-----",
            "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----",
            'api_key = "' + "FAKE" * 10 + '"',
            'client_secret: "' + "FAKE" * 6 + '"',
            'DB_PASSWORD: "' + "FAKE" * 6 + '"',
            "password: " + "Fake" * 2 + "123!",
            "API_KEY=" + "FAKE" * 4 + "/+=",
        ]
        for token in tokens:
            with self.subTest(kind=token[:4]):
                self.stage(token + "\n")
                self.assert_blocked(self.scan(), token)
                self.assert_blocked(self.scan("fix: example\n\n" + token), token)

    def test_safe_references_and_placeholders_pass(self):
        lines = [
            'api_key = "' + v + '"' for v in ["REPLACE_FROM_VAULT", "${API_KEY:-}", "<YOUR_KEY>"]
        ]
        lines += [
            'api_key = os.getenv("API_KEY")',
            "const apiKey = process.env.API_KEY;",
            "password = settings.db_password",
            "  password: formData.password,",
            "self.client_secret = self.client_secret  # attribute",
            "accessToken: dpopAccessToken!,",
            "login(username=username, password=password, api_key=API_KEY)",
            "client_secret: SecretStr",
        ]
        for line in lines:
            with self.subTest(line=line):
                self.stage(line + "\n")
                self.assertEqual(self.scan().returncode, 0)
                self.assertEqual(self.scan("fix: example\n\n" + line).returncode, 0)

    def test_worktree_cannot_hide_staged_secret(self):
        token = "ghp_" + "A" * 36
        path = self.stage(token)
        path.write_text("clean worktree\n")
        self.assert_blocked(self.scan(), token)

    def test_unstaged_secret_is_not_committed(self):
        path = self.stage("clean index\n")
        path.write_text("ghp_" + "A" * 36)
        self.assertEqual(self.scan().returncode, 0)

    def test_only_added_lines_are_scanned(self):
        self.stage("ghp_" + "A" * 36 + "\n")
        self.record_head()
        self.stage("clean replacement\n")
        self.assertEqual(self.scan().returncode, 0)

    def test_new_sensitive_paths_block_even_with_clean_content(self):
        names = [".env", ".env.local", ".env.development", "key.pem", "key.key", "vars.tfvars"]
        names += ["credentials.json", ".aws/credentials", ".git-credentials", "ci.credentials"]
        for name in names:
            with self.subTest(name=name):
                self.stage("clean\n", name)
                result = self.scan()
                self.assertEqual(result.returncode, 1)
                self.assertIn("sensitive filename", result.stderr)
                self.git("read-tree", "--empty")

    def test_rename_to_sensitive_path_blocks(self):
        self.stage("clean\n", "notes.txt")
        self.record_head()
        self.git("mv", "notes.txt", ".env")
        result = self.scan()
        self.assertEqual(result.returncode, 1)
        self.assertIn("sensitive filename", result.stderr)

    def test_templates_and_credential_sources_can_be_added_and_modified(self):
        self.stage("tracked\n", "portal/.env.development")  # tracked env file, edits only
        self.record_head()
        names = ["portal/.env.development", "deploy/.env.example", ".env.sample"]
        names += ["src/credentials.rs", "docs/credentials.md", "ui/CredentialsViewer.tsx"]
        for content in ["clean\n", "clean edit\n"]:
            for name in names:
                self.stage(content, name)
            self.assertEqual(self.scan().returncode, 0, content)
            self.record_head()
        token = "ghp_" + "A" * 36
        self.stage(token + "\n", names[1])
        self.assert_blocked(self.scan(), token)

    def test_test_and_example_paths_are_not_exempt(self):
        token = "ghp_" + "A" * 36
        self.stage(token, "tests/fixture.example")
        self.assert_blocked(self.scan(), token)

    def test_added_line_starting_with_plus_is_scanned(self):
        token = "ghp_" + "A" * 36
        self.stage("++" + token)
        self.assert_blocked(self.scan(), token)

    def test_missing_message_fails_closed(self):
        result = self.invoke("python3", str(GUARD), str(self.repo / "missing"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Secret guard:", result.stderr)

    def test_real_hooks_refuse_secrets_before_running_other_tools(self):
        guard = self.repo / "scripts/ci/precommit_secrets.py"
        guard.parent.mkdir(parents=True)
        shutil.copyfile(GUARD, guard)
        token = "ghp_" + "A" * 36
        self.stage(token)
        message = self.repo / "message"
        message.write_text("fix: example\n\n" + token)
        for hook in ["pre-commit", "commit-msg"]:
            with self.subTest(hook=hook):
                result = self.invoke("/bin/sh", str(ROOT / ".husky" / hook), str(message))
                self.assert_blocked(result, token)

    def test_existing_hooks_invoke_guard_before_other_checks(self):
        for name in ["pre-commit", "commit-msg"]:
            lines = (ROOT / ".husky" / name).read_text().splitlines()
            self.assertIn("scripts/ci/precommit_secrets.py", lines[0])
            self.assertIn("|| exit", lines[0])


class SecretGuardRangeTests(unittest.TestCase):
    """Drive --range through the command line against throwaway repositories.

    Failure messages are fixed strings: fixture values, paths and captured output are never
    rendered. Fixture values are assembled at run time and commit messages go through stdin.
    """

    longMessage = False
    TIMEOUT = 30
    TOKEN = "ghp_" + "A" * 36
    KEY_HEADER = "-----BEGIN " + "RSA PRIVATE KEY-----"
    CREDENTIAL = 'api_key = "' + "FAKE" * 8 + '"'
    BARE_CREDENTIAL = "password: " + "Fake" * 2 + "123!"
    FOUND = ". Remove sensitive data from the range.\n"
    CLOSED = ". Range scan failed closed.\n"
    LEGACY = ". Remove sensitive data before committing.\n"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        # Fixture repositories ignore the caller's Git environment and configuration.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        for role in ("AUTHOR", "COMMITTER"):
            self.env[f"GIT_{role}_NAME"] = "Test"
            self.env[f"GIT_{role}_EMAIL"] = "test@example.invalid"
        self.git("init", "-q", "-b", "main")
        self.base = self.commit("seed.txt", "baseline\n")

    def require(self, condition, message):
        if not condition:
            self.fail(message)

    def run_quiet(self, *command, stdin="", cwd=None):
        try:
            return subprocess.run(
                command,
                cwd=cwd or self.repo,
                env=self.env,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            raise self.failureException("fixture command timed out") from None

    def git(self, *args, stdin="", cwd=None):
        result = self.run_quiet("git", *args, stdin=stdin, cwd=cwd)
        self.require(result.returncode == 0, "git fixture command failed")
        return result.stdout.strip()

    def stage(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode())
        self.git("add", "-f", "--", name)

    def commit(self, name=None, content="", message="chore: update fixture"):
        """Commit the index, plus one file when a name is given, and return the commit id."""
        if name is not None:
            self.stage(name, content)
        self.git("commit", "-q", "--allow-empty", "-F", "-", stdin=message)
        return self.git("rev-parse", "HEAD")

    def scan(self, *args, cwd=None):
        return self.run_quiet("python3", str(GUARD), *args, cwd=cwd)

    def scan_range(self, base, head, *flags, cwd=None):
        return self.scan("--range", base, head, *flags, cwd=cwd)

    def load_guard(self):
        """Import the guard in this process, for checks that no git setting can reach."""
        spec = importlib.util.spec_from_file_location("precommit_secrets_under_test", GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def assert_passes(self, result):
        self.require(result.returncode == 0, "expected the scan to pass")
        self.require(result.stdout + result.stderr == "", "expected no scan output")

    def assert_diagnostics(self, result, details, suffix, hidden=()):
        output = result.stdout + result.stderr
        self.require(not any(value in output for value in hidden), "diagnostics echoed scan input")
        self.require(result.returncode == 1, "expected exit status 1")
        self.require(
            all(detail in result.stderr for detail in details), "expected label is missing"
        )
        expected = "".join(f"Secret guard: {detail}{suffix}" for detail in details)
        self.require(output == expected, "unexpected diagnostics")

    def assert_findings(self, result, findings, hidden=()):
        self.assert_diagnostics(result, findings, self.FOUND, hidden)

    def assert_closed(self, result, detail):
        self.assert_diagnostics(result, [detail], self.CLOSED)

    def assert_legacy(self, result, detail):
        self.assert_diagnostics(result, [detail], self.LEGACY)

    def test_capability_marker_is_declared(self):
        lines = GUARD.read_text(encoding="utf-8").splitlines()
        self.require("RANGE_MODE_SUPPORTED = True" in lines, "range capability marker is missing")

    def test_clean_range_passes(self):
        tracked = self.commit("portal/.env.development", "PORT=3000\n")
        self.commit("portal/.env.development", "PORT=3000\nHOST=localhost\n")
        self.commit("deploy/.env.example", "API_KEY=REPLACE_FROM_VAULT\n")
        head = self.commit("app.py", 'api_key = os.getenv("API_KEY")\n', "feat: read settings")
        self.assert_passes(self.scan_range(tracked, head))
        self.assert_passes(self.scan_range(tracked, "main"))

    def test_sensitive_filenames_are_reported_without_the_path(self):
        names = [".env", "certs/service.pem", "infra/prod.tfvars", ".aws/credentials"]
        expected = ["sensitive filename added or renamed at diff path #1"]
        for index, name in enumerate(names):
            with self.subTest(case=index):
                self.git("checkout", "-q", self.base)
                head = self.commit(name, "clean\n")
                result = self.scan_range(self.base, head)
                self.assert_findings(result, expected, [name, Path(name).name])
        with self.subTest(case=len(names)):
            self.git("checkout", "-q", self.base)
            self.git("mv", "seed.txt", "deploy.key")
            head = self.commit()
            self.assert_findings(self.scan_range(self.base, head), expected, ["deploy.key"])

    def test_added_lines_are_reported_by_rule_without_the_value(self):
        cases = [
            ("access token", self.TOKEN),
            ("private key", self.KEY_HEADER),
            ("literal credential", self.CREDENTIAL),
            ("literal credential", self.BARE_CREDENTIAL),
        ]
        for index, (label, value) in enumerate(cases):
            with self.subTest(case=index):
                self.git("checkout", "-q", self.base)
                head = self.commit("src/settings.txt", "first\n" + value + "\n")
                expected = [f"{label} detected in diff file #1 at line 2"]
                result = self.scan_range(self.base, head)
                self.assert_findings(result, expected, [value, "settings"])

    def test_only_lines_added_in_the_range_are_reported(self):
        base = self.commit("legacy.txt", "keep\n" + self.TOKEN + "\n")
        kept = self.commit("legacy.txt", "keep\n" + self.TOKEN + "\nmore\n")
        self.assert_passes(self.scan_range(base, kept))
        removed = self.commit("legacy.txt", "keep\nmore\n")
        self.assert_passes(self.scan_range(base, removed))

    def test_commit_messages_are_scanned(self):
        older = self.commit("a.txt", "one\n", "feat: subject\n\n" + self.TOKEN)
        head = self.commit("b.txt", "two\n", "chore: follow-up")
        expected = [f"access token detected in commit #2 ({older[:12]}) message at line 3"]
        self.assert_findings(self.scan_range(self.base, head), expected, [self.TOKEN])
        # A commit reachable from BASE is outside the range.
        self.assert_passes(self.scan_range(older, head))

    def test_message_only_commit_is_scanned(self):
        clean = self.commit(message="chore: record a decision")
        self.assert_passes(self.scan_range(self.base, clean))
        head = self.commit(message="chore: record a decision\n\n" + self.KEY_HEADER)
        expected = [f"private key detected in commit #1 ({head[:12]}) message at line 3"]
        self.assert_findings(self.scan_range(clean, head), expected, [self.KEY_HEADER])

    def test_merge_commit_message_is_scanned(self):
        self.git("checkout", "-q", "-b", "side")
        self.commit("side.txt", "side\n")
        self.git("checkout", "-q", "main")
        self.commit("main.txt", "main\n")
        self.git("merge", "-q", "--no-ff", "--no-commit", "side")
        head = self.commit(message="merge: side\n\n" + self.CREDENTIAL)
        parents = self.git("rev-list", "--parents", "-n", "1", head).split()[1:]
        self.require(len(parents) == 2, "fixture is not a merge commit")
        expected = [f"literal credential detected in commit #1 ({head[:12]}) message at line 3"]
        self.assert_findings(self.scan_range(self.base, head), expected, [self.CREDENTIAL])

    def test_worktree_file_named_like_a_commit_does_not_disturb_the_message_scan(self):
        flagged = self.commit(message="chore: note\n\n" + self.TOKEN)
        head = self.commit(flagged, "clean\n")
        expected = [f"access token detected in commit #2 ({flagged[:12]}) message at line 3"]
        self.assert_findings(self.scan_range(self.base, head), expected, [self.TOKEN])

    def test_empty_range_fails_unless_allowed(self):
        head = self.commit("a.txt", "one\n")
        for index, (base, tip) in enumerate([(head, head), (head, self.base)]):
            with self.subTest(case=index):
                self.assert_closed(self.scan_range(base, tip), "empty commit range")
                self.assert_passes(self.scan_range(base, tip, "--allow-empty"))

    def test_invalid_revisions_and_options_fail_closed(self):
        head = self.commit("a.txt", "one\n")
        invalid, unresolved = "invalid git revision", "unable to resolve git revision"
        usage = "expected --range BASE HEAD [--allow-empty] [--direct]"
        cases = [
            (["", head], invalid),
            ([self.base, ""], invalid),
            (["--cached", head], invalid),
            ([self.base, "-1"], invalid),
            ([self.base + ".." + head, head], invalid),
            ([self.base, "main..main"], invalid),
            ([self.base, "ma\tin"], invalid),
            ([self.base, "main\n"], invalid),
            ([self.base, "no-such-branch"], unresolved),
            (["0" * 40, head], unresolved),
            ([self.base + "^{tree}", head], unresolved),
            ([self.base, head, "--unknown"], usage),
            ([self.base, head, head], usage),
            ([self.base, head, "--direct", "--direct"], usage),
            ([self.base, head, "--allow-empty", "--direct", "--allow-empty"], usage),
        ]
        for index, (args, detail) in enumerate(cases):
            with self.subTest(case=index):
                self.assert_closed(self.scan("--range", *args), detail)
        with self.subTest(case=len(cases)), tempfile.TemporaryDirectory() as outside:
            result = self.scan("--range", self.base, head, cwd=outside)
            self.assert_closed(result, unresolved)

    def test_divergent_branch_is_compared_with_the_merge_base(self):
        # Both sides share these at the branch point; BASE removes them afterwards.
        self.commit("legacy.txt", self.TOKEN + "\n")
        branch_point = self.commit("deploy/.env.local", "PORT=3000\n")
        self.git("rm", "-q", "--", "legacy.txt", "deploy/.env.local")
        advanced = self.commit(message="chore: clean up\n\n" + self.KEY_HEADER)
        self.git("checkout", "-q", "-b", "topic", branch_point)
        head = self.commit("feature.txt", "clean\n")
        # What differs only because BASE moved on is not attributed to HEAD, and the
        # commits reachable from BASE are outside BASE..HEAD.
        self.assert_passes(self.scan_range(advanced, head))
        # Compared with BASE itself, the same range does report those differences.
        expected = [
            "sensitive filename added or renamed at diff path #1",
            "access token detected in diff file #3 at line 1",
        ]
        result = self.scan_range(advanced, head, "--direct")
        self.assert_findings(result, expected, [self.TOKEN, ".env.local", "legacy"])
        head = self.commit("feature.txt", "clean\n" + self.CREDENTIAL + "\n")
        expected = ["literal credential detected in diff file #1 at line 2"]
        self.assert_findings(self.scan_range(advanced, head), expected, [self.CREDENTIAL])

    def test_unrelated_histories_need_direct_mode(self):
        self.git("checkout", "-q", "--orphan", "unrelated")
        self.git("rm", "-rf", "-q", ".")
        head = self.commit("other.txt", "clean\n")
        self.assert_closed(self.scan_range(self.base, head), "unable to resolve merge base")
        self.assert_passes(self.scan_range(self.base, head, "--direct"))

    def test_direct_mode_detects_a_rewind_that_restores_a_sensitive_path(self):
        restored = self.commit("deploy/.env", "PORT=3000\n" + self.TOKEN + "\n")
        self.git("rm", "-q", "--", "deploy/.env")
        removed = self.commit()
        # Moving the branch from `removed` back to `restored` adds no commit, and the merge
        # base is `restored` itself: only the direct comparison sees the path come back.
        self.assert_closed(self.scan_range(removed, restored, "--direct"), "empty commit range")
        self.assert_passes(self.scan_range(removed, restored, "--allow-empty"))
        expected = [
            "sensitive filename added or renamed at diff path #1",
            "access token detected in diff file #1 at line 2",
        ]
        result = self.scan_range(removed, restored, "--direct", "--allow-empty")
        self.assert_findings(result, expected, [self.TOKEN, ".env"])

    def test_binary_paths_are_scanned_as_text(self):
        base = self.commit(".gitattributes", "*.bin binary\nspecs/* -diff\n")
        cases = [
            ("data.bin", "header\n"),
            ("specs/api.yaml", "openapi: 3.0.0\n"),
            ("raw.dat", "nul\0byte\n"),  # binary by content, without any attribute
        ]
        expected = ["access token detected in diff file #1 at line 2"]
        for index, (name, first_line) in enumerate(cases):
            with self.subTest(case=index):
                self.git("checkout", "-q", base)
                head = self.commit(name, first_line + self.TOKEN + "\n")
                self.assert_findings(self.scan_range(base, head), expected, [self.TOKEN, name])

    def test_carriage_returns_do_not_hide_added_lines(self):
        look_alike = "diff --git a/x b/x"
        cases = [
            ("ok\r\n" + self.TOKEN + "\r\n", "access token", 2),
            ("ok\r\n" + self.BARE_CREDENTIAL + "\r\n", "literal credential", 2),
            ("prefix\r" + self.TOKEN + "\n", "access token", 1),
            ("prefix\r" + look_alike + "\n" + self.TOKEN + "\n", "access token", 2),
            ("prefix " + self.KEY_HEADER + "\n", "private key", 1),
        ]
        for index, (content, label, line) in enumerate(cases):
            with self.subTest(case=index):
                self.git("checkout", "-q", self.base)
                head = self.commit("notes.txt", content)
                expected = [f"{label} detected in diff file #1 at line {line}"]
                hidden = [self.TOKEN, self.KEY_HEADER, self.BARE_CREDENTIAL]
                self.assert_findings(self.scan_range(self.base, head), expected, hidden)
        with self.subTest(case=len(cases)):
            self.git("checkout", "-q", self.base)
            head = self.commit(message="fix: subject\n\nprefix\r" + self.TOKEN)
            expected = [f"access token detected in commit #1 ({head[:12]}) message at line 3"]
            self.assert_findings(self.scan_range(self.base, head), expected, [self.TOKEN])

    def test_submodule_ignore_settings_do_not_hide_an_added_gitlink(self):
        gitlink = "vendor/service.pem"
        mapping = '[submodule "vendored"]\n\tpath = ' + gitlink + "\n\turl = ./vendored\n"
        cases = [
            (mapping + "\tignore = all\n", None),
            (mapping, "submodule.vendored.ignore"),
            (None, "diff.ignoreSubmodules"),
        ]
        for index, (gitmodules, setting) in enumerate(cases):
            with self.subTest(case=index):
                self.git("checkout", "-q", self.base)
                if gitmodules:
                    self.stage(".gitmodules", gitmodules)
                if setting:
                    self.git("config", setting, "all")
                self.git("update-index", "--add", "--cacheinfo", f"160000,{self.base},{gitlink}")
                head = self.commit("zz-notes.txt", self.TOKEN + "\n")
                result = self.scan_range(self.base, head)
                if setting:
                    self.git("config", "--unset", setting)
                # Diff entries are sorted by path: .gitmodules if any, the gitlink, the notes.
                position = 2 if gitmodules else 1
                expected = [
                    f"sensitive filename added or renamed at diff path #{position}",
                    f"access token detected in diff file #{position + 1} at line 1",
                ]
                self.assert_findings(result, expected, [self.TOKEN, gitlink, "service.pem"])

    def test_log_output_encoding_does_not_hide_a_message_finding(self):
        head = self.commit(message="chore: record a decision\n\n" + self.TOKEN)
        expected = [f"access token detected in commit #1 ({head[:12]}) message at line 3"]
        for index, encoding in enumerate(["UTF-16LE", "UTF-16", "UTF-32BE"]):
            with self.subTest(case=index):
                self.git("config", "i18n.logOutputEncoding", encoding)
                self.assert_findings(self.scan_range(self.base, head), expected, [self.TOKEN])

    def test_relative_diff_setting_does_not_hide_paths_outside_the_current_directory(self):
        base = self.commit("nested/deep/keep.txt", "keep\n")
        self.stage("deploy/.env", "PORT=3000\n")
        head = self.commit("src/notes.txt", "clean\n" + self.TOKEN + "\n")
        self.git("config", "diff.relative", "true")
        expected = [
            "sensitive filename added or renamed at diff path #1",
            "access token detected in diff file #2 at line 2",
        ]
        for index, flags in enumerate([[], ["--direct"]]):
            with self.subTest(case=index):
                result = self.scan_range(base, head, *flags, cwd=self.repo / "nested/deep")
                self.assert_findings(result, expected, [self.TOKEN, ".env", "notes"])

    def test_tree_expressions_are_rejected_as_revisions(self):
        # With a peel suffix appended, "<rev>:vendor" names the first directory below, a tree.
        self.stage("vendor^{commit}/module.txt", "clean\n")
        head = self.commit("docs/guide.txt", "clean\n")
        trees = [head + ":vendor", head + ":vendor^{commit}", head + ":docs"]
        for index, tree in enumerate(trees):
            for flags in ([], ["--direct"], ["--direct", "--allow-empty"]):
                with self.subTest(case=index, flags=len(flags)):
                    result = self.scan_range(tree, head, *flags)
                    self.assert_closed(result, "unable to resolve git revision")
                    result = self.scan_range(self.base, tree, *flags)
                    self.assert_closed(result, "unable to resolve git revision")

    def test_c1_control_characters_in_a_revision_fail_closed(self):
        head = self.commit("a.txt", "one\n")
        # Git accepts these characters in a ref name, so every revision below does resolve.
        for index, code in enumerate([0x80, 0x85, 0x9F, 0xA0]):
            with self.subTest(case=index):
                name = "topic" + chr(code) + "next"
                self.git("branch", name, head)
                resolved = self.git("rev-parse", "--verify", "--quiet", name + "^{commit}")
                self.require(resolved == head, "fixture ref does not resolve")
                if code == 0xA0:  # first character after the C1 block: an ordinary ref name
                    self.assert_passes(self.scan_range(self.base, name))
                    continue
                self.assert_closed(self.scan_range(self.base, name), "invalid git revision")
                result = self.scan_range(name, head, "--direct", "--allow-empty")
                self.assert_closed(result, "invalid git revision")

    def test_shallow_repository_fails_closed(self):
        flagged = self.commit(message="chore: note\n\n" + self.TOKEN)
        head = self.commit("a.txt", "one\n")
        self.git("branch", "release", self.base)
        expected = [f"access token detected in commit #2 ({flagged[:12]}) message at line 3"]
        result = self.scan_range(self.base, head, "--direct")
        self.assert_findings(result, expected, [self.TOKEN])
        with tempfile.TemporaryDirectory() as clone:
            source = self.repo.resolve().as_uri()
            self.git("clone", "-q", "--depth", "1", "--no-single-branch", source, clone)
            shallow = self.git("rev-parse", "--is-shallow-repository", cwd=clone)
            self.require(shallow == "true", "fixture clone is not shallow")
            # Both ends resolve in the clone, but the flagged commit between them is cut off.
            for commit in (self.base, head):
                self.git("cat-file", "-e", commit + "^{commit}", cwd=clone)
            listed = self.git("rev-list", f"{self.base}..{head}", "--", cwd=clone).split()
            self.require(listed == [head], "fixture history is not truncated")
            detail = "shallow repository, full history is required"
            for index, flags in enumerate([[], ["--direct"], ["--direct", "--allow-empty"]]):
                with self.subTest(case=index):
                    result = self.scan_range(self.base, head, *flags, cwd=clone)
                    self.assert_closed(result, detail)

    def test_submodule_diff_format_does_not_scan_inside_a_populated_submodule(self):
        gitlink = "vendor/service.pem"
        inner = self.repo / gitlink
        self.git("init", "-q", "-b", "main", str(inner))
        (inner / "inner.txt").write_bytes((self.TOKEN + "\n").encode())
        self.git("add", "--", "inner.txt", cwd=inner)
        self.git("commit", "-q", "-F", "-", stdin="chore: seed", cwd=inner)
        pinned = self.git("rev-parse", "HEAD", cwd=inner)
        self.git("update-index", "--add", "--cacheinfo", f"160000,{pinned},{gitlink}")
        head = self.commit("zz-notes.txt", self.TOKEN + "\n")
        # The gitlink is reported by name; what the submodule itself contains is not scanned.
        expected = [
            "sensitive filename added or renamed at diff path #1",
            "access token detected in diff file #2 at line 1",
        ]
        hidden = [self.TOKEN, gitlink, "service.pem", "inner"]
        for index, style in enumerate(["diff", "log", "short"]):
            with self.subTest(case=index):
                self.git("config", "diff.submodule", style)
                self.assert_findings(self.scan_range(self.base, head), expected, hidden)

    def test_line_numbers_ignore_hunk_merging_and_blank_context_settings(self):
        base = self.commit("notes.txt", "one\n\ntwo\n\nthree\n")
        head = self.commit("notes.txt", "changed\n\ntwo\n\n" + self.TOKEN + "\n")
        expected = ["access token detected in diff file #1 at line 5"]
        cases = [
            ["diff.interHunkContext"],
            ["diff.suppressBlankEmpty"],
            ["diff.interHunkContext", "diff.suppressBlankEmpty"],
        ]
        values = {"diff.interHunkContext": "8", "diff.suppressBlankEmpty": "true"}
        for index, settings in enumerate(cases):
            with self.subTest(case=index):
                for setting in settings:
                    self.git("config", setting, values[setting])
                result = self.scan_range(base, head)
                for setting in settings:
                    self.git("config", "--unset", setting)
                self.assert_findings(result, expected, [self.TOKEN])

    def test_parser_counts_blank_context_lines_written_without_a_prefix(self):
        patch = [
            "diff --git a/notes.txt b/notes.txt",
            "--- a/notes.txt",
            "+++ b/notes.txt",
            "@@ -1,5 +1,5 @@",
            "-one",
            "+changed",
            "",  # blank context line, as written under diff.suppressBlankEmpty
            " two",
            "",
            "-three",
            "+final",
            "diff --git a/other.txt b/other.txt",
            "--- a/other.txt",
            "+++ b/other.txt",
            "@@ -2,0 +3 @@",
            "+added",
            "",
        ]
        found = [entry[:2] for entry in self.load_guard().added_lines("\n".join(patch))]
        self.require(found == [(1, 1), (1, 5), (2, 3)], "unexpected added line positions")

    def test_git_failure_after_revision_resolution_fails_closed(self):
        middle = self.commit("a.txt", "one\n", "chore: note\n\n" + self.TOKEN)
        head = self.commit("b.txt", self.TOKEN + "\n")
        # Without its tree the diff of HEAD fails; without the middle commit the history walk does.
        missing = [self.git("rev-parse", head + "^{tree}"), middle]
        for index, object_id in enumerate(missing):
            with self.subTest(case=index):
                stored = self.repo / ".git/objects" / object_id[:2] / object_id[2:]
                self.require(stored.is_file(), "fixture object is not a loose object")
                stored.unlink()
                for revision in (self.base, head):
                    resolved = self.git("rev-parse", "--verify", "--quiet", revision + "^{commit}")
                    self.require(resolved == revision, "fixture revision does not resolve")
                for flags in ([], ["--direct"]):
                    result = self.scan_range(self.base, head, *flags)
                    self.assert_closed(result, "unable to read scan input")

    def test_staged_mode_is_unchanged(self):
        # Without arguments only the staged diff counts, whatever the history contains.
        self.commit("old.txt", self.TOKEN + "\n", "chore: note\n\n" + self.TOKEN)
        self.assert_passes(self.scan())
        self.stage("sample.txt", "clean\n" + self.TOKEN + "\n")
        self.assert_legacy(self.scan(), "access token detected at scanned line 2")
        self.git("reset", "-q", "--hard")
        self.stage("deploy/.env", "clean\n")
        self.assert_legacy(self.scan(), "sensitive filename added or renamed")

    def test_single_argument_is_still_a_message_file(self):
        for index, name in enumerate(["--range", "--allow-empty", "--direct"]):
            with self.subTest(case=index):
                path = self.repo / name
                path.write_text("fix: clean subject\n", encoding="utf-8")
                self.assert_passes(self.scan(name))
                path.write_text("fix: subject\n\n" + self.TOKEN + "\n", encoding="utf-8")
                self.assert_legacy(self.scan(name), "access token detected at scanned line 3")
                path.unlink()
                self.assert_legacy(self.scan(name), "unable to read scan input")

    def test_range_mode_needs_both_revisions(self):
        cases = [
            ["--range", self.base],
            ["message", "extra"],
            ["--allow-empty", "--range", self.base, self.base],
        ]
        for index, args in enumerate(cases):
            with self.subTest(case=index):
                self.assert_legacy(self.scan(*args), "expected at most one commit message file")
