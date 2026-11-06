#!/usr/bin/env python3
"""Export a validated, content-addressed reference for a published GHCR image."""

import os
import re
import sys
from pathlib import Path


def main():
    image = os.environ.get('IMAGE_NAME', '')
    digest = os.environ.get('IMAGE_DIGEST', '')
    if not re.fullmatch(r'ghcr\.io/[a-z0-9._-]+/[a-z0-9._/-]+', image):
        sys.exit('::error::Expected an untagged GHCR image repository')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        sys.exit('::error::Expected a published sha256 image digest')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write(f'ref={image}@{digest}\n')


if __name__ == '__main__':
    main()
