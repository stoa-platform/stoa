"""The publish path must validate and consume content-addressed images."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / '.github/workflows'


def workflow(name):
    return yaml.safe_load((WORKFLOWS / f'{name}.yml').read_text())


@pytest.mark.parametrize('name,job', [
    ('reusable-docker-ghcr', 'docker'), ('docker-publish', 'build'),
])
def test_regression_publish_validates_digest_before_consumption(name, job):
    document = workflow(name)
    steps = document['jobs'][job]['steps']
    build = next(i for i, step in enumerate(steps) if step.get('id') == 'build')
    validate = next(i for i, step in enumerate(steps) if step.get('id') == 'image')
    assert validate == build + 1
    step = steps[validate]
    assert step['run'] == 'python3 -B scripts/ci/publish_image_ref.py'
    assert step['env']['IMAGE_DIGEST'] == '${{ steps.build.outputs.digest }}'
    assert 'continue-on-error' not in step
    assert 'if' not in step
    metadata = next(step for step in steps if step.get('id') == 'meta')['with']
    assert metadata['flavor'] == 'latest=false'
    assert 'latest' not in metadata['tags']
    if name == 'reusable-docker-ghcr':
        assert document[True]['workflow_call']['outputs']['image-ref']['value'] == (
            '${{ jobs.docker.outputs.image_ref }}'
        )
        assert document['jobs'][job]['outputs']['image_ref'] == '${{ steps.image.outputs.ref }}'
        assert document['jobs'][job]['outputs']['image_tag'] == (
            '${{ env.IMAGE_NAME }}:${{ inputs.environment }}-${{ github.sha }}'
        )
    else:
        sign = next(step for step in steps if step['name'] == 'Sign image with Cosign (keyless)')
        assert sign['env'] == {'IMAGE_REF': '${{ steps.image.outputs.ref }}'}
        assert sign['run'].strip() == 'cosign sign --yes "$IMAGE_REF"'
        sbom = next(step for step in steps if step['name'] == 'Generate SBOM')
        assert sbom['with']['image'] == (
            '${{ env.IMAGE_PREFIX }}/${{ matrix.service }}@${{ steps.build.outputs.digest }}'
        )
        for name in ('Attach SBOM to image', 'Sign SBOM attestation', 'Output image info'):
            consumer = next(step for step in steps if step['name'] == name)
            assert '${{ steps.image.outputs.ref }}' in consumer['run']


@pytest.mark.parametrize('name', [
    'control-plane-api-ci', 'control-plane-ui-ci', 'stoa-portal-ci', 'stoa-gateway-ci',
])
def test_regression_deploy_retains_full_commit_tag_contract(name):
    assert workflow(name)['jobs']['deploy']['with']['image-tag'] == (
        '${{ needs.docker.outputs.image-tag }}'
    )


@pytest.mark.parametrize('digest', [
    'sha256:' + 'a' * 64, '', 'latest', 'dev-latest', 'sha256:abc',
    'sha256:' + 'A' * 64, 'sha256:' + 'a' * 64 + '\nref=evil',
])
def test_regression_digest_validation_is_fail_closed(tmp_path, digest):
    output = tmp_path / 'output'
    result = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'scripts/ci/publish_image_ref.py')],
        env={**os.environ, 'IMAGE_NAME': 'ghcr.io/stoa-platform/example',
             'IMAGE_DIGEST': digest, 'GITHUB_OUTPUT': str(output)},
        capture_output=True, text=True, check=False,
    )
    if digest == 'sha256:' + 'a' * 64:
        assert result.returncode == 0, result.stderr
        assert output.read_text() == f'ref=ghcr.io/stoa-platform/example@{digest}\n'
    else:
        assert result.returncode == 1
        assert '::error::Expected a published sha256 image digest' in result.stderr
        assert not output.exists()


@pytest.mark.parametrize('image', [
    '', 'ghcr.io/team/app' + ':latest', 'ghcr.io/team/app' + ':dev-latest',
    'ghcr.io/team/app@sha256:' + 'a' * 64, 'ghcr.io/team/app\nref=evil',
])
def test_regression_rejects_tagged_or_injected_repository(tmp_path, image):
    output = tmp_path / 'output'
    result = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'scripts/ci/publish_image_ref.py')],
        env={**os.environ, 'IMAGE_NAME': image, 'IMAGE_DIGEST': 'sha256:' + 'a' * 64,
             'GITHUB_OUTPUT': str(output)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert '::error::Expected an untagged GHCR image repository' in result.stderr
    assert not output.exists()
