#!/usr/bin/env bash
# Garde anti-réapparition des chemins purgés (CAB-2327 P2)
#
# Échoue si un chemin retiré de l'historique existe dans l'arbre de HEAD ou
# apparaît dans les commits d'un intervalle donné. Les chemins ne figurent ici
# qu'en empreintes SHA-256 : chaque chemin de fichier, et chacun de ses
# dossiers parents suivi d'un « / », est haché puis comparé à la liste.
# Aucun chemin n'est jamais affiché. Aucune valeur n'est recherchée.
#
# Usage : ./scripts/ci/purged-paths-guard.sh [<plage-git> ...]
#   sans argument : arbre de HEAD seulement
#   avec arguments : arbre de HEAD + fichiers touchés par
#                    git log <plage-git> ... (ex. base..head, ou head --not main)
# Sortie : 0 = conforme, 1 = chemin purgé détecté, 2 = erreur d'exécution
set -euo pipefail
export LC_ALL=C

readonly PURGED_SHA256="
932cc396aee0553ff4b74b5f5a9453c798728762cae6e2f4054e96dc82ee0eda
cadc8a39e04108a078bf2ee1d5a251a4e97c5591303042f018751ba98adb3d8e
e5a5e0e66bc984c0477cb510bc759de59e6168904c8dcf375dca5909bbadab94
aae8897075ba88a8b10aab1c82474ea6279d439d4c997fab2d2c52be27091a30
c95f66f1ac972c53dd1be2d5783613d8b1662aeedaee11f9696424ed5c65967c
4d2140b84d603143c98422a54e18251b67c86a9656204b92277d4bdf93076552
aa1e7477e5e84940d6a652c49563557f30bb4596f1fcb0f61bdf6c1b2b2d4d5a
0e99144a400b2df6854854405b5b019c361833432adee75509145c27c8f7e762
"

readonly MSG="Un chemin retiré de l'historique est réapparu. Voir la procédure interne."

die() { echo "::error::purged-paths-guard : $1" >&2; exit 2; }

git rev-parse --git-dir >/dev/null 2>&1 || die "pas de dépôt git"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# 1. Chemins (séparés par NUL) : arbre de HEAD, puis fichiers des commits.
git -c core.quotepath=off ls-tree -r -z --name-only --full-tree HEAD >"$tmp/paths" \
  || die "lecture de l'arbre impossible"
if [ "$#" -gt 0 ]; then
  # -m : diff de chaque parent des fusions ; --no-renames : ancien et nouveau nom.
  git -c core.quotepath=off log -z -m --no-renames --name-only --format= "$@" -- >>"$tmp/paths" \
    || die "lecture des commits impossible"
fi

# 2. Candidats : chaque chemin et chacun de ses dossiers parents (avec « / »).
# 3. Empreintes SHA-256 (perl Digest::SHA en un seul processus, sinon sha256sum).
hash_candidates() {
  if perl -MDigest::SHA -e 1 2>/dev/null; then
    perl -MDigest::SHA=sha256_hex -0ne '
      chomp; next if $_ eq "";
      my @p = split m{/}, $_; my $acc = "";
      for my $i (0 .. $#p - 1) { $acc .= $p[$i] . "/"; $seen{$acc} = 1; }
      $seen{$_} = 1;
      END { print sha256_hex($_), "\n" for keys %seen; }'
  else
    local path acc rest
    while IFS= read -r -d '' path; do
      [ -n "$path" ] || continue
      printf '%s\0' "$path"
      acc=""; rest="$path"
      while [[ "$rest" == */* ]]; do
        acc+="${rest%%/*}/"; rest="${rest#*/}"
        printf '%s\0' "$acc"
      done
    done | sort -zu | while IFS= read -r -d '' path; do
      printf '%s' "$path" | sha256sum | cut -d' ' -f1
    done
  fi
}

hash_candidates <"$tmp/paths" | sort -u >"$tmp/hashes" || die "calcul des empreintes impossible"
printf '%s\n' "$PURGED_SHA256" | grep -E '^[0-9a-f]{64}$' | sort -u >"$tmp/purged"

if [ -n "$(comm -12 "$tmp/hashes" "$tmp/purged")" ]; then
  echo "::error::$MSG" >&2
  exit 1
fi
echo "purged-paths-guard : aucun chemin purgé détecté."
