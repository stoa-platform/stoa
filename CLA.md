# Contributor License Agreement

STOA is an open source project licensed under the [Apache License 2.0](LICENSE). We use the [Developer Certificate of Origin (DCO)](DCO) to ensure that contributors have the right to submit their contributions.

## What is the DCO?

The Developer Certificate of Origin (DCO) is a lightweight mechanism for contributors to certify that they wrote or otherwise have the right to submit the code they are contributing. The DCO was created by the Linux Foundation and is used by many open source projects including the Linux kernel, Kubernetes, and CNCF projects.

By signing off on your commits, you certify that:

1. You created the contribution, or
2. It's based on previous work with a compatible open source license, or
3. It was provided to you by someone who certified the above

The full text is available in the [DCO](DCO) file.

## How to Sign Your Commits

### Using the `-s` Flag

Add the `-s` (or `--signoff`) flag to your git commit command:

```bash
git commit -s -m "feat(api): add rate limiting support"
```

This adds a `Signed-off-by` line to your commit message:

```
feat(api): add rate limiting support

Signed-off-by: Your Name <your.email@example.com>
```

### Configure Git for Automatic Sign-off

To automatically sign off all commits in this repository:

```bash
cd stoa
git config commit.gpgsign true  # Optional: GPG signing
```

Or add a git hook. Create `.git/hooks/prepare-commit-msg`:

```bash
#!/bin/sh
# Add Signed-off-by line if not present
NAME=$(git config user.name)
EMAIL=$(git config user.email)
SIGNOFF="Signed-off-by: $NAME <$EMAIL>"

if ! grep -q "^Signed-off-by:" "$1"; then
    echo "" >> "$1"
    echo "$SIGNOFF" >> "$1"
fi
```

Make it executable:

```bash
chmod +x .git/hooks/prepare-commit-msg
```

### IDE Integration

Most IDEs support automatic sign-off:

- **VS Code**: Add `"git.alwaysSignOff": true` to settings
- **JetBrains IDEs**: Enable in Git settings > "Sign-off commit"
- **GitHub Desktop**: Configure in Preferences > Git

## FAQ

### How do I fix a commit I forgot to sign off?

**For the last commit:**

```bash
git commit --amend -s --no-edit
```

**For multiple commits:**

```bash
# Rebase the last N commits
git rebase -i HEAD~N

# In the editor, change 'pick' to 'edit' for unsigned commits
# Then for each commit:
git commit --amend -s --no-edit
git rebase --continue
```

**After pushing (force push required):**

```bash
git push --force-with-lease
```

### What if I have multiple email addresses?

Use the email associated with your GitHub account:

```bash
git config user.email "your.github.email@example.com"
```

### Can I sign off commits from the GitHub web interface?

GitHub's web editor doesn't add sign-off automatically. You'll need to:

1. Clone the repository locally
2. Make your changes and commit with `-s`
3. Push to your fork

### What information is stored?

Your sign-off (name and email) is part of the commit metadata and will be publicly visible in the git history. This is standard practice for open source contributions.

### Why DCO instead of a CLA?

The DCO is:

- **Lightweight**: No legal paperwork or registration required
- **Per-commit**: Each contribution is certified individually
- **Standard**: Used by Linux, Kubernetes, and many CNCF projects
- **Compatible**: Works with Apache 2.0 licensing

## CI Enforcement

All pull requests are automatically checked for DCO compliance. If your PR fails the DCO check:

1. Ensure all commits have the `Signed-off-by` line
2. Follow the instructions above to fix unsigned commits
3. Push the updated commits

## Questions?

If you have questions about the DCO or contribution process:

- Open a [GitHub Discussion](https://github.com/PotoMitan/stoa/discussions)
- Email us at [hello@gostoa.dev](mailto:hello@gostoa.dev)

---

Thank you for contributing to STOA!
