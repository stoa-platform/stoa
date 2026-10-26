# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/ci/check_licences_offline.py'
spec = importlib.util.spec_from_file_location('licences', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
POLICY = json.loads(SCRIPT.with_name('licences-policy.json').read_text())


class Expressions(unittest.TestCase):
    def test_decisions(self):
        cases = {
            'MIT': 'conforme', 'Apache-2.0': 'conforme', 'BSL-1.0': 'conforme', 'MIT AND ISC': 'conforme',
            '(BSD-3-Clause OR GPL-2.0)': 'conforme',
            'MIT OR (AGPL-3.0-only AND LicenseRef-private)': 'conforme',
            'MIT AND GPL-3.0-only': 'incompatible',
            'GPL-2.0+': 'incompatible', 'AGPL-3.0-or-later': 'incompatible',
            'SSPL-1.0': 'incompatible', 'BUSL-1.1': 'incompatible',
            'CC-BY-NC-SA-4.0': 'incompatible', 'LicenseRef-NonCommercial': 'incompatible', 'LGPL-2.1-only': 'incompatible',
            '(GPL-2.0-only OR BUSL-1.1)': 'incompatible',
            'GPL-2.0-only OR LicenseRef-private': 'à confirmer',
            'MPL-2.0': 'à confirmer', 'CC-BY-4.0': 'à confirmer',
            'Apache-2.0 WITH LLVM-exception': 'à confirmer',
            'MIT WITH Invented-exception': 'à confirmer',
            'GPL-2.0-only WITH Classpath-exception-2.0': 'à confirmer',
            'MIT AND LicenseRef-private': 'à confirmer',
            'NOASSERTION': 'à confirmer', 'NONE': 'à confirmer', '': 'à confirmer',
            '[[À CONFIRMER]]': 'à confirmer', 'SEE LICENSE IN LICENSE': 'à confirmer',
            'MIT$': 'à confirmer', 'MIT / GPL-3.0': 'à confirmer',
            'MIT OR': 'à confirmer', '(MIT': 'à confirmer', 'MIT AND': 'à confirmer',
            'MIT OR )': 'à confirmer', 'MIT WITH': 'à confirmer',
            'MIT AND (ISC OR GPL-3.0-only)': 'conforme',
        }
        for expr, expected in cases.items():
            with self.subTest(expression=expr):
                self.assertEqual(mod.classify(expr, POLICY), expected)

    def test_reviewed_exception(self):
        policy = dict(POLICY, allowed_exceptions=['Apache-2.0 WITH LLVM-exception'])
        self.assertEqual(mod.classify('Apache-2.0 WITH LLVM-exception', policy), 'conforme')


class Command(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=SCRIPT.parents[2])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'package.json').write_text('{}\n')
        self.inventory = self.root / 'inventory.csv'
        self.snapshot = self.root / 'snapshot.json'
        self.policy = self.root / 'policy.json'
        self.policy.write_text(json.dumps(POLICY))
        self.prepare('MIT')

    def prepare(self, license):
        with self.inventory.open('w', newline='') as stream:
            w = csv.DictWriter(stream, fieldnames=['ecosystem', 'name', 'version', 'license', 'source'])
            w.writeheader()
            w.writerow(dict(ecosystem='npm', name='fixture', version='1.0', license=license,
                            source='package.json:1'))
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        self.snapshot.write_text(json.dumps({'schema': 1, 'inventory_sha256': digest(self.inventory),
            'sources': {'package.json': digest(self.root / 'package.json')}}))

    def run_check(self, *args):
        return subprocess.run(['python3', '-B', str(SCRIPT), '--root', str(self.root),
            '--config', str(self.policy), '--inventory', str(self.inventory),
            '--snapshot', str(self.snapshot), *args], capture_output=True).returncode

    def test_missing_inputs_warn_then_fail_when_blocking(self):
        self.inventory.unlink()
        self.assertEqual(self.run_check(), 0)
        self.assertEqual(self.run_check('--mode', 'deny'), 2)
        self.assertEqual(self.run_check('--enforce'), 2)

    def test_enabled_policy_and_cli(self):
        self.assertEqual(self.run_check('--enforce'), 0)
        self.prepare('GPL-3.0-only')
        self.assertEqual(self.run_check('--enforce'), 1)
        self.policy.write_text(json.dumps(dict(POLICY, enabled=True)))
        self.assertEqual(self.run_check(), 1)

    def test_unknown_is_blocking(self):
        for license in ['', 'NOASSERTION', 'LicenseRef-commercial', 'MPL-2.0']:
            self.prepare(license)
            self.assertEqual(self.run_check('--enforce'), 1)

    def test_missing_stale_added_removed_and_tampered_inputs(self):
        (self.root / 'package.json').write_text('{"changed":true}')
        self.assertEqual(self.run_check('--enforce'), 2)
        self.prepare('MIT')
        (self.root / 'Cargo.toml').write_text('[package]\nname="new"\n')
        self.assertEqual(self.run_check('--enforce'), 2)
        (self.root / 'Cargo.toml').unlink()
        with self.inventory.open('a') as f:
            f.write('npm,extra,1,MIT,package.json:1\n')
        self.assertEqual(self.run_check('--enforce'), 2)
        self.prepare('MIT')
        (self.root / 'package.json').unlink()
        self.assertEqual(self.run_check('--enforce'), 2)
        self.snapshot.unlink()
        self.assertEqual(self.run_check('--enforce'), 2)

    def test_empty_inventory_and_bad_schema_fail(self):
        self.inventory.write_text('ecosystem,name,version,license,source\n')
        data = json.loads(self.snapshot.read_text())
        data['inventory_sha256'] = hashlib.sha256(self.inventory.read_bytes()).hexdigest()
        self.snapshot.write_text(json.dumps(data))
        self.assertEqual(self.run_check('--enforce'), 2)
        self.policy.write_text(json.dumps(dict(POLICY, enabled='false')))
        self.assertEqual(self.run_check(), 2)

    def test_symlink_outside_root_is_rejected(self):
        sibling = tempfile.TemporaryDirectory(dir=SCRIPT.parents[2])
        self.addCleanup(sibling.cleanup)
        target = Path(sibling.name) / 'outside.json'
        target.write_text('{}\n')
        (self.root / 'package.json').unlink()
        (self.root / 'package.json').symlink_to(target)
        self.prepare('MIT')
        self.assertEqual(self.run_check('--enforce'), 2)

    def test_snapshot_path_escape(self):
        data = json.loads(self.snapshot.read_text())
        data['sources']['../outside'] = '0' * 64
        self.snapshot.write_text(json.dumps(data))
        self.assertEqual(self.run_check('--enforce'), 2)


if __name__ == '__main__':
    unittest.main()
