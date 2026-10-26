# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/ci/check_licences_offline.py'
SPEC = importlib.util.spec_from_file_location('collector', SCRIPT.with_name('collect_licences_local.py'))
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class LocalCI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('Cargo.toml', '[package]\nname="local"\nversion="1.0"\nlicense="Apache-2.0"\n[dependencies]\nmissing="1"\n')
        self.write('Cargo.lock', 'version=3\n[[package]]\nname="missing"\nversion="1.0.0"\nsource="registry+fixture"\n')
        self.output = self.root / 'report.json'

    def write(self, relative, text):
        p = self.root / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def run_cli(self, *extra):
        result = subprocess.run(['python3', '-B', str(SCRIPT), '--root', str(self.root),
            '--report', str(self.output), *extra], capture_output=True, text=True)
        return result.returncode

    def test_warning_and_enforce_keep_unknown_visible(self):
        self.assertEqual(self.run_cli(), 0)
        data = json.loads(self.output.read_text())
        self.assertEqual(data['mode'], 'warn')
        self.assertGreater(data['counts']['à confirmer'], 0)
        self.assertEqual(self.run_cli('--enforce'), 1)
        self.assertEqual(self.run_cli('--mode', 'enforce'), 1)

    def test_all_ecosystems_and_no_inherited_license(self):
        self.write('go.mod', 'module fixture\nrequire (\n example.test/lib v1.2.3\n)\nreplace example.test/lib => ../local\n')
        self.write('go.sum', 'example.test/other v0.2.0 h1:fixture\n')
        self.write('pyproject.toml', '[project]\nname="fixture"\nversion="1"\ndependencies=["dep==2.0; python_version > \'3\'"]\n')
        self.write('requirements.txt', '-r other.txt\nother>=1\n')
        self.write('Dockerfile', 'FROM alpine:3 AS build\nFROM build AS next\nFROM scratch\n')
        self.write('deploy/values.yaml', 'image:\n  repository: example/image\n  tag: v1\n')
        rows, _ = collector.collect(self.root)
        ecos = {r['ecosystem'] for r in rows}
        self.assertTrue({'cargo', 'cargo-declaration', 'go', 'go-sum', 'pypi', 'oci'} <= ecos)
        self.assertTrue(all(r['license'] == collector.MARK for r in rows if r['ecosystem'] != 'cargo-project'))
        self.assertEqual(len([r for r in rows if r['ecosystem'] == 'oci' and r['name'] == 'alpine:3']), 1)

    def evidence(self, kind='cargo'):
        path = self.write('audit/licences/evidence/missing.toml',
            '[package]\nname="missing"\nversion="1.0.0"\nlicense="MIT"\n')
        entry = dict(ecosystem='cargo', name='missing', version='1.0.0', source='Cargo.lock',
            source_sha256=collector.digest(self.root / 'Cargo.lock'), path=path.relative_to(self.root).as_posix(),
            sha256=collector.digest(path), kind=kind, reason='artefact local relu et rapproché du lock')
        self.write('audit/licences/local-evidence.json', json.dumps(dict(schema=1, entries=[entry])))
        return entry

    def test_local_license_and_stale_evidence(self):
        entry = self.evidence()
        rows, sources = collector.collect(self.root)
        dep = next(r for r in rows if r['ecosystem'] == 'cargo' and r['name'] == 'missing')
        self.assertEqual(dep['license'], 'MIT')
        self.assertIn(entry['path'], sources)
        self.write(entry['path'], 'changed')
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(self.run_cli('--enforce'), 2)

    def test_python_metadata_and_go_image_text(self):
        self.write('requirements.txt', 'other==2.0\n')
        self.write('go.mod', 'module fixture\nrequire example.test/lib v1.2.3\n')
        self.write('Dockerfile', 'FROM image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n')
        entries = []
        for eco, name, version, source, kind, path, content in [
            ('pypi','other','2.0','requirements.txt','python','evidence/METADATA','Name: other\nVersion: 2.0\nLicense-Expression: ISC\n'),
            ('go','example.test/lib','v1.2.3','go.mod','spdx-text','evidence/GO-LICENSE','SPDX-License-Identifier: BSD-3-Clause\n'),
            ('oci','image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','image@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','Dockerfile','spdx-text','evidence/IMAGE-LICENSE','SPDX-License-Identifier: Apache-2.0\n')]:
            p = self.write(path,content)
            entries.append(dict(ecosystem=eco,name=name,version=version,source=source,kind=kind,path=path,
                sha256=collector.digest(p),source_sha256=collector.digest(self.root/source),reason='rapprochement exact revu'))
        self.write('audit/licences/local-evidence.json',json.dumps(dict(schema=1,entries=entries)))
        rows,_ = collector.collect(self.root)
        for entry in entries:
            row = next(r for r in rows if all(r[k] == entry[k] for k in ('ecosystem','name','version','source')))
            self.assertNotEqual(row['license'],collector.MARK)

    def test_no_links_or_credential_reads(self):
        outside = self.write('outside.txt','DO NOT READ')
        self.write('.ssh/credentials','secret')
        self.write('vendor/credentials','secret')
        (self.root/'package.json').symlink_to(outside)
        self.assertEqual(self.run_cli(),2)
        (self.root/'package.json').unlink()
        entry = self.evidence()
        entry['path'] = '.ssh/credentials'
        self.write('audit/licences/local-evidence.json',json.dumps(dict(schema=1,entries=[entry])))
        self.assertEqual(self.run_cli(),2)

    def test_malformed_manifest_fails_in_warning(self):
        self.write('pyproject.toml','[broken')
        self.assertEqual(self.run_cli(),2)

    def test_empty_scope_is_not_compliant(self):
        (self.root/'Cargo.toml').unlink(); (self.root/'Cargo.lock').unlink()
        self.assertEqual(self.run_cli(),2)

    def test_targeted_exception_expiry_and_unused(self):
        # A lock-only scope has one reference and no resolution claim.
        (self.root/'Cargo.toml').unlink()
        entry = dict(ecosystem='cargo',name='missing',version='1.0.0',source='Cargo.lock',
            license=collector.MARK,source_sha256=collector.digest(self.root/'Cargo.lock'),
            reason='preuve fournisseur attendue; usage de test limité',approved_by='Juridique fixture',
            decision='decision-locale-fixture',expires='2099-01-01')
        policy = json.loads(SCRIPT.with_name('licences-policy.json').read_text())
        policy['exceptions'] = [entry]
        p = self.write('policy.json',json.dumps(policy))
        self.assertEqual(self.run_cli('--enforce','--config',str(p)),0)
        data=json.loads(self.output.read_text())
        self.assertEqual(data['counts']['dérogation'],1)
        self.assertEqual(data['rows'][0]['original_status'],'à confirmer')
        for change in [dict(expires='2000-01-01'),dict(expires='20990101'),dict(reason=''),dict(name='*'),dict(version='9.9'),dict(source_sha256='0'*64)]:
            policy['exceptions']=[dict(entry,**change)]; p.write_text(json.dumps(policy))
            self.assertEqual(self.run_cli('--enforce','--config',str(p)),2)

    def test_npm_unknown_and_changed_manifests(self):
        self.write('package.json','{"dependencies":{"new":"1"}}')
        self.write('package-lock.json',json.dumps(dict(lockfileVersion=3,packages={'':{},'node_modules/ok':dict(version='1',license='MIT')})))
        rows,_=collector.collect(self.root)
        self.assertTrue(any(r['name']=='new' and r['license']==collector.MARK for r in rows))
        self.assertEqual(self.run_cli('--enforce'),1)

    def test_ci_gate_propagates_failures_and_exposes_switch(self):
        text = (ROOT / '.github/workflows/required-checks.yml').read_text()
        job = text.split('  license-compliance:', 1)[1].split('  sbom-generation:', 1)[0]
        self.assertNotIn('continue-on-error', job)
        self.assertNotIn('uses: aquasecurity/trivy', job.lower())
        self.assertNotIn('|| echo', job)
        self.assertIn("vars.LICENSES_ENFORCE == 'true'", job)
        self.assertIn('--mode "$LICENSES_MODE"', job)
        self.assertIn('if: always()', job)

    def test_policy_switch_and_invalid_policy(self):
        policy = json.loads(SCRIPT.with_name('licences-policy.json').read_text())
        policy['mode'] = 'enforce'
        path = self.write('policy.json', json.dumps(policy))
        self.assertEqual(self.run_cli('--config', str(path)), 1)
        self.assertEqual(self.run_cli('--config', str(path), '--mode', 'warn'), 0)
        policy['mode'] = 'disabled'
        path.write_text(json.dumps(policy))
        self.assertEqual(self.run_cli('--config', str(path)), 2)

    def test_findings_report_is_replaced_on_invalid_input(self):
        self.assertEqual(self.run_cli(), 0)
        self.write('Cargo.toml', '[broken')
        self.assertEqual(self.run_cli(), 2)
        self.assertEqual(json.loads(self.output.read_text())['result'], 'invalid-input')

    def test_conflicting_spdx_metadata_stays_unknown(self):
        entry = self.evidence()
        entry['kind'] = 'spdx-text'
        path = self.write(entry['path'], 'SPDX-License-Identifier: MIT\nSPDX-License-Identifier: GPL-3.0-only\n')
        entry['sha256'] = collector.digest(path)
        self.write('audit/licences/local-evidence.json', json.dumps(dict(schema=1, entries=[entry])))
        rows, _ = collector.collect(self.root)
        dep = next(r for r in rows if r['ecosystem'] == 'cargo' and r['name'] == 'missing')
        self.assertEqual(dep['license'], collector.MARK)

    def test_local_crate_does_not_license_same_name_registry_crate(self):
        self.write('Cargo.lock', 'version=3\n[[package]]\nname="local"\nversion="1.0"\n'
                   '[[package]]\nname="local"\nversion="1.0"\nsource="registry+fixture"\n')
        rows, _ = collector.collect(self.root)
        crates = [r for r in rows if r['ecosystem'] == 'cargo' and r['name'] == 'local']
        self.assertEqual([r['license'] for r in crates], ['Apache-2.0', collector.MARK])

    def test_bad_archive_is_invalid_input(self):
        self.write('chart.tgz', 'not an archive')
        self.assertEqual(self.run_cli(), 2)

    def test_image_evidence_needs_immutable_digest(self):
        self.write('Dockerfile', 'FROM image:latest\n')
        p = self.write('evidence/LICENSE', 'SPDX-License-Identifier: MIT\n')
        entry = dict(ecosystem='oci', name='image:latest', version='image:latest', source='Dockerfile',
            source_sha256=collector.digest(self.root/'Dockerfile'), path='evidence/LICENSE',
            sha256=collector.digest(p), kind='spdx-text', reason='fixture tag mutable')
        self.write('audit/licences/local-evidence.json', json.dumps(dict(schema=1, entries=[entry])))
        self.assertEqual(self.run_cli(), 2)

    def test_same_crate_version_different_origins_requires_locator(self):
        self.write('Cargo.lock', 'version=3\n[[package]]\nname="missing"\nversion="1.0.0"\nsource="registry+fixture"\n'
                   '[[package]]\nname="missing"\nversion="1.0.0"\nsource="git+fixture"\n')
        entry = self.evidence()
        self.assertEqual(self.run_cli(), 2)
        entry['locator'] = 'registry+fixture'
        self.write('audit/licences/local-evidence.json', json.dumps(dict(schema=1, entries=[entry])))
        rows, _ = collector.collect(self.root)
        crates = [r for r in rows if r['ecosystem'] == 'cargo' and r['name'] == 'missing']
        self.assertEqual([r['license'] for r in crates], ['MIT', collector.MARK])

    def test_local_conflicting_license_is_not_silently_accepted(self):
        self.write('Cargo.lock', 'version=3\n[[package]]\nname="local"\nversion="1.0"\n')
        path = self.write('evidence/LICENSE', 'SPDX-License-Identifier: MIT\n')
        entry = dict(ecosystem='cargo', name='local', version='1.0', source='Cargo.lock',
            source_sha256=collector.digest(self.root/'Cargo.lock'), path='evidence/LICENSE',
            sha256=collector.digest(path), kind='spdx-text', reason='fixture de divergence')
        self.write('audit/licences/local-evidence.json', json.dumps(dict(schema=1, entries=[entry])))
        rows, _ = collector.collect(self.root)
        row = next(r for r in rows if r['ecosystem'] == 'cargo' and r['name'] == 'local')
        self.assertEqual(row['license'], collector.MARK)
        self.assertEqual(row['declared_license'], 'Apache-2.0')
        self.assertEqual(row['local_license'], 'MIT')

    def test_exceptions_do_not_waive_other_crate_origins(self):
        (self.root/'Cargo.toml').unlink()
        self.write('Cargo.lock', 'version=3\n[[package]]\nname="missing"\nversion="1.0.0"\nsource="registry+fixture"\n'
                   '[[package]]\nname="missing"\nversion="1.0.0"\nsource="git+fixture"\n')
        entry = dict(ecosystem='cargo', name='missing', version='1.0.0', source='Cargo.lock',
            license=collector.MARK, source_sha256=collector.digest(self.root/'Cargo.lock'),
            reason='dérogation fixture ciblée par origine', approved_by='Juridique fixture',
            decision='fixture', expires='2099-01-01')
        policy = json.loads(SCRIPT.with_name('licences-policy.json').read_text())
        policy['exceptions'] = [entry]
        path = self.write('policy.json', json.dumps(policy))
        self.assertEqual(self.run_cli('--enforce', '--config', str(path)), 2)
        policy['exceptions'] = [dict(entry, locator='registry+fixture')]
        path.write_text(json.dumps(policy))
        self.assertEqual(self.run_cli('--enforce', '--config', str(path)), 1)
        data = json.loads(self.output.read_text())
        self.assertEqual(data['counts'], {'dérogation': 1, 'à confirmer': 1})
        policy['exceptions'].append(dict(entry, locator='git+fixture'))
        path.write_text(json.dumps(policy))
        self.assertEqual(self.run_cli('--enforce', '--config', str(path)), 0)

    def test_no_network_or_external_process_in_collection(self):
        from unittest.mock import patch
        with patch('socket.socket', side_effect=AssertionError('network forbidden')), \
             patch('subprocess.Popen', side_effect=AssertionError('external process forbidden')):
            rows, _ = collector.collect(self.root)
        self.assertTrue(rows)

    def test_explicit_docker_installations_are_kept_unknown(self):
        self.write('Dockerfile', 'FROM alpine:3\nRUN apk add --no-cache curl=1 libexample \\\n  && pip install --no-cache-dir -r requirements.txt other==2.0 \\\n  && cargo install --locked helper --version 1.0\n')
        rows, _ = collector.collect(self.root)
        self.assertTrue(any(r['ecosystem']=='os-package' and r['name']=='curl' and r['version']=='1' for r in rows))
        self.assertTrue(any(r['ecosystem']=='pypi' and r['name']=='other' and r['version']=='2.0' for r in rows))
        self.assertTrue(any(r['ecosystem']=='cargo-tool' and r['name']=='helper' for r in rows))
        self.assertTrue(all(r['license']==collector.MARK for r in rows if r['ecosystem'] in {'os-package','pypi','cargo-tool'}))

    def test_chart_archives_read_local_text_and_nested_image_references(self):
        import io
        import tarfile
        contents = {
            'chart/Chart.yaml': 'name: chart\nversion: 1.0\n',
            'chart/LICENSE': 'SPDX-License-Identifier: MIT\n',
            'chart/values.yaml': 'image: image@sha256:' + 'a'*64 + '\n',
            'chart/charts/nested/Chart.yaml': 'name: nested\nversion: 2.0\n',
        }
        with tarfile.open(self.root/'chart.tgz', 'w:gz') as archive:
            for name,content in contents.items():
                data=content.encode(); member=tarfile.TarInfo(name); member.size=len(data)
                archive.addfile(member,io.BytesIO(data))
        self.write('Chart.yaml', 'name: root\nversion: 1.0\ndependencies:\n  - name: chart\n    version: 1.0\n    repository: https://example.test/charts\n')
        self.write('Chart.lock', 'dependencies:\n- name: locked\n  version: 2.0\ndigest: fixture\n')
        rows,_=collector.collect(self.root)
        self.assertTrue(any(r['ecosystem']=='helm' and r['name']=='locked' for r in rows))
        chart=next(r for r in rows if r['ecosystem']=='helm' and r['name']=='chart' and r['source']=='chart.tgz')
        nested=next(r for r in rows if r['ecosystem']=='helm' and r['name']=='nested')
        self.assertEqual(chart['license'],'MIT')
        self.assertEqual(nested['license'],collector.MARK)
        self.assertTrue(any(r['ecosystem']=='oci' and r['name'].startswith('image@sha256:') for r in rows))
        self.assertFalse(any(r['ecosystem']=='oci' and r['name'].startswith('https:') for r in rows))
        self.assertTrue(any(r['ecosystem']=='helm' and r['name']=='chart' and r['source']=='Chart.yaml' for r in rows))


if __name__ == '__main__':
    unittest.main()
