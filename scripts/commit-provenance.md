# Optional local commit provenance

Traceability start marker: **2026-11-05** (introduction of this local tool).
This is a prospective convention, not evidence of adoption by all contributors.
Do not amend, rebase, or rewrite past commits to add provenance. A missing
trailer makes no claim about how older or opted-out commits were produced.

The exact trailers are:

- `AI-Generated-By: <tool>` for content produced by an AI tool.
- `Human-Verified-By: <name>` for an actual human review.

These are self-reported provenance statements, not certification or signatures.
Never infer human review from the author, committer, or DCO sign-off.

## Install locally (optional)

Requires POSIX sh and Python 3. This repository manages Git hooks with husky
(`"prepare": "husky"` in `package.json`): `npm install` sets `core.hooksPath`
to `.husky/_` and regenerates every file in that directory, including a stub
for `prepare-commit-msg`. Never create a file or a symlink in `.husky/_`. The
next `npm install` silently overwrites it, and husky writes through symlinks,
so a link placed there would replace the tracked `scripts/prepare-commit-msg`
with the stub.

The stub runs `.husky/prepare-commit-msg` when that file exists, the same way
the tracked hooks in `.husky/` run. Install the tool as a local, untracked file
there and hide it from `git status` through `.git/info/exclude`. Run this from
the checkout root; husky hooks, including this one, only run once
`npm install` has generated `.husky/_` in this checkout:

```sh
if [ -e .husky/prepare-commit-msg ] || [ -L .husky/prepare-commit-msg ]; then
    printf '%s\n' 'Existing hook preserved. Manually integrate the following call into it, keeping its existing commands:' \
        '"$(git rev-parse --show-toplevel)/scripts/prepare-commit-msg" "$@" || :'
else
    cat > .husky/prepare-commit-msg <<'EOF'
"$(git rev-parse --show-toplevel)/scripts/prepare-commit-msg" "$@" || :
EOF
    exclude=$(git rev-parse --git-path info/exclude)
    grep -qxF '/.husky/prepare-commit-msg' "$exclude" 2>/dev/null \
        || echo '/.husky/prepare-commit-msg' >> "$exclude"
fi
```

Husky runs that file with `sh -e`; its `|| :` and the script's own `|| :` and
`exit 0` keep any failure from blocking a commit. `npm install` may regenerate
`.husky/_` at any time; it never touches `.husky/prepare-commit-msg` or the
tracked script. Do not commit `.husky/prepare-commit-msg`: the tool stays
opt-in per checkout. Git worktrees share `info/exclude` but each has its own
`.husky/`, so repeat `npm install` and the first command in every worktree
that should run the hook. To uninstall, delete `.husky/prepare-commit-msg`.

In a repository without husky, call this script with `"$@"` from the
`prepare-commit-msg` hook of the active hooks directory
(`git rev-parse --git-path hooks`), using the absolute checkout path, only if
that directory does not end in `.husky/_`. Preserve any existing hook behavior.

Provide only the applicable values explicitly for each new commit:

```sh
STOA_AI_TOOL=Codex git commit -S -s
# Only after Jane has actually reviewed the content:
STOA_AI_TOOL=Codex STOA_HUMAN_VERIFIED_BY='Jane Doe' git commit -S -s
```

Omit both variables to disable suggestions without changing the installation.
Do not persist human verification in shell profiles. Review and edit suggested
trailers in the commit editor. `git commit -m` has no editor review step. With
a `commit.template` that makes the message start with a `#` comment (for
example a template made only of commented prompts), the hook adds nothing:
type the trailers manually in the editor in that case.

The hook reads only the supplied message and these two variables. It does not
read credentials, repository content/history, Git identity/configuration, or
call the network. Invalid values are ignored. Existing trailers are preserved
case-insensitively. Amend/reuse (`commit` source), merge, and squash messages
are untouched. Git's default `#` comments/scissors are preserved; with a custom
comment character, leave the variables unset and add trailers manually.
Errors, including missing Python or an unwritable message, never veto a commit.

## Local verification

```sh
shellcheck scripts/prepare-commit-msg
python3 -m unittest discover -s scripts/tests -p test_commit_provenance.py -v
```
