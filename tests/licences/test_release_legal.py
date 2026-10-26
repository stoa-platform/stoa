# Copyright 2026 Christophe Aboulicam
# SPDX-License-Identifier: Apache-2.0
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/ci/release_legal.py'


class ReleaseLegal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('LICENSE','NOTICE'):
            (self.root/name).write_bytes((ROOT/name).read_bytes())

    def run_cli(self,*args):
        return subprocess.run(['python3','-B',str(SCRIPT),'--root',str(self.root),*args],capture_output=True).returncode

    def test_stage_preserves_bytes_and_refuses_conflict_or_escape(self):
        self.assertEqual(self.run_cli('--dest','component'),0)
        for name in ('LICENSE','NOTICE'):
            self.assertEqual((self.root/'component'/name).read_bytes(),(self.root/name).read_bytes())
        self.assertEqual(self.run_cli('--dest','component'),0)
        (self.root/'component/NOTICE').write_text('different')
        self.assertEqual(self.run_cli('--dest','component'),2)
        self.assertEqual(self.run_cli('--dest','../outside'),2)
        (self.root/'link').symlink_to(self.root/'component',target_is_directory=True)
        self.assertEqual(self.run_cli('--dest','link'),2)

    def archive(self,name,notice=True,corrupt=False):
        path=self.root/name
        docs={'LICENSE':(self.root/'LICENSE').read_bytes()}
        if notice: docs['NOTICE']=b'changed' if corrupt else (self.root/'NOTICE').read_bytes()
        if name.endswith('.zip'):
            with zipfile.ZipFile(path,'w') as archive:
                for key,value in docs.items(): archive.writestr('bundle/'+key,value)
        else:
            with tarfile.open(path,'w:gz') as archive:
                for key,value in docs.items():
                    member=tarfile.TarInfo('bundle/'+key);member.size=len(value)
                    archive.addfile(member,io.BytesIO(value))
        return path

    def test_real_tar_zip_missing_or_wrong_notice(self):
        for ext in ('tar.gz','zip'):
            for notice,corrupt,expected in [(True,False,0),(False,False,2),(True,True,2)]:
                path=self.archive('fixture.'+ext,notice,corrupt)
                self.assertEqual(self.run_cli('--archive',str(path)),expected)

    def test_go_archives_and_docker_context_include_both(self):
        text=(ROOT/'stoa-go/.goreleaser.yaml').read_text()
        archive_section=text.split('archives:',1)[1].split('checksum:',1)[0]
        self.assertEqual(archive_section.count('- NOTICE*'),2)
        docker_section=text.split('dockers:',1)[1]
        self.assertIn('extra_files:',docker_section)
        for name in ('LICENSE','NOTICE'): self.assertIn('- '+name,docker_section)

    def test_final_docker_stages_include_legal_documents(self):
        for component in ('portal','control-plane-ui','control-plane-api','stoa-gateway','keycloak','stoa-go','scripts/security'):
            text=(ROOT/component/'Dockerfile').read_text()
            final=text.rsplit('\nFROM ',1)[-1]
            self.assertIn('COPY LICENSE NOTICE /usr/share/licenses/stoa/',final,component)

    def test_workflows_stage_before_packaging(self):
        for name in ('docker-publish','reusable-docker-ghcr','keycloak-theme','build-tls-cert-monitor','helm-release','reusable-node-ci','security-scan','hegemon-deploy'):
            self.assertIn('scripts/ci/release_legal.py',(ROOT/f'.github/workflows/{name}.yml').read_text(),name)
        text=(ROOT/'.github/workflows/helm-release.yml').read_text()
        self.assertIn('--archive',text)
        self.assertLess(text.index('scripts/ci/release_legal.py'),text.index('          helm package'))

    def test_archive_paths_and_links_cannot_fake_legal_documents(self):
        for names in [('../LICENSE', '../NOTICE'), ('a/LICENSE', 'b/NOTICE'),
                      ('dependencies/deep/LICENSE', 'dependencies/deep/NOTICE')]:
            path = self.root/'unsafe.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                for member, document in zip(names, ('LICENSE', 'NOTICE')):
                    archive.writestr(member, (self.root/document).read_bytes())
            self.assertEqual(self.run_cli('--archive', str(path)), 2)
        path = self.root/'linked.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            for document in ('LICENSE', 'NOTICE'):
                member = zipfile.ZipInfo(document)
                member.create_system = 3
                member.external_attr = 0o120777 << 16
                archive.writestr(member, (self.root/document).read_bytes())
        self.assertEqual(self.run_cli('--archive', str(path)), 2)

    def test_tar_link_cannot_override_an_accepted_document(self):
        path = self.archive('linked.tar.gz')
        # Recreate the archive with regular docs followed by a conflicting link.
        with tarfile.open(path, 'w:gz') as archive:
            for document in ('LICENSE', 'NOTICE'):
                content = (self.root/document).read_bytes()
                member = tarfile.TarInfo(document); member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
            member = tarfile.TarInfo('NOTICE'); member.type = tarfile.SYMTYPE; member.linkname = 'missing'
            archive.addfile(member)
        self.assertEqual(self.run_cli('--archive', str(path)), 2)


if __name__=='__main__': unittest.main()
