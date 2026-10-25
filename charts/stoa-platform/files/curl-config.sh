#!/bin/sh
# The bootstrap hook passes request credentials over stdin to curl.
set +x
curl() {
  local config key value option
  config=$(
    while [ "$#" -gt 0 ]; do
      option=$1; shift
      case "$option" in
        -s) printf 'silent\n'; continue ;;
        -sf) printf 'silent\nfail\n'; continue ;;
        -X) key=request ;; -H) key=header ;; -d) key=data ;;
        -o) key=output ;; -w) key=write-out ;;
        -*) echo "Unsupported curl option." >&2; exit 2 ;;
        *) key=url; set -- "$option" "$@" ;;
      esac
      [ "$#" -gt 0 ] || exit 2
      value=$1; shift
      printf '%s = "' "$key"
      printf '%s.' "$value" | awk '
        { text = text (NR > 1 ? "\n" : "") $0 }
        END {
          text = substr(text, 1, length(text) - 1);
          for (i = 1; i <= length(text); i++) {
            c = substr(text, i, 1);
            if (c == "\\") printf "%s", "\\\\";
            else if (c == "\"") printf "%s", "\\\"";
            else if (c == "\n") printf "%s", "\\n";
            else if (c == "\r") printf "%s", "\\r";
            else if (c == "\t") printf "%s", "\\t";
            else printf "%s", c;
          }
        }
      '
      printf '"\n'
    done
  ) || return 2
  printf '%s\n' "$config" | command curl -q --config -
}
