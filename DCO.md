# Developer Certificate of Origin

STOA Platform uses the Developer Certificate of Origin (DCO) as a lightweight way to certify that you wrote or otherwise have the right to submit the code you are contributing.

## The DCO

The DCO is a declaration that you make when contributing to STOA:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## How to Sign-Off

You must sign-off your commits to certify the DCO. This is done by adding a `Signed-off-by` line to your commit message:

```
feat(gateway): add rate limiting support

Implemented token bucket algorithm for rate limiting.

Signed-off-by: Your Name <your.email@example.com>
```

### Using Git

The easiest way is to use the `-s` or `--signoff` flag when committing:

```bash
git commit -s -m "feat(gateway): add rate limiting support"
```

### Configuring Git

Make sure your Git configuration has your correct name and email:

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### Amending a Commit

If you forgot to sign-off a commit, you can amend it:

```bash
git commit --amend --signoff
```

### Signing Off Multiple Commits

For a branch with multiple unsigned commits:

```bash
git rebase --signoff HEAD~N  # where N is the number of commits
```

## GPG Signing (Recommended)

For additional security, we recommend GPG signing your commits:

```bash
# Generate a GPG key (if you don't have one)
gpg --full-generate-key

# Configure Git to use your GPG key
git config --global user.signingkey YOUR_KEY_ID
git config --global commit.gpgsign true

# Sign and sign-off
git commit -s -S -m "your commit message"
```

## Enforcement

All pull requests are automatically checked for DCO sign-off. PRs without proper sign-off will not be merged.

## Questions?

If you have questions about the DCO or need help with the sign-off process, please open an issue or reach out on [Discord](https://discord.gg/stoa).

---

The DCO is the same mechanism used by the Linux Kernel, Kubernetes, and many CNCF projects.
