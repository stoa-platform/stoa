#!/usr/bin/env bash
# Keep request bodies and authorization headers out of child process arguments.
set +x

curl() {
  local config='' key value option flag
  while [[ $# -gt 0 ]]; do
    option=$1
    shift
    case "$option" in
      -X|--request) key=request ;;
      -H|--header) key=header ;;
      -d|--data) key=data ;;
      --data-urlencode) key=data-urlencode ;;
      --data-binary) key=data-binary ;;
      -u|--user) key=user ;;
      -o|--output) key=output ;;
      -w|--write-out) key=write-out ;;
      -D|--dump-header) key=dump-header ;;
      -T|--upload-file) key=upload-file ;;
      --max-time|--connect-timeout|--cacert|--resolve|--retry|--url)
        key=${option#--} ;;
      --fail|--silent|--show-error|--insecure|--head)
        config+="${option#--}"$'\n'
        continue ;;
      -*)
        if [[ ! "$option" =~ ^-[sfSkI]+$ ]]; then
          echo "Unsupported curl option in secret-input helper." >&2
          return 2
        fi
        for ((flag=1; flag<${#option}; flag++)); do
          case "${option:flag:1}" in
            s) key=silent ;; f) key=fail ;; S) key=show-error ;;
            k) key=insecure ;; I) key='head' ;;
          esac
          config+="$key"$'\n'
        done
        continue ;;
      *)
        key=url
        set -- "$option" "$@" ;;
    esac
    [[ $# -gt 0 ]] || { echo "Missing curl option value." >&2; return 2; }
    value=$1
    shift
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//$'\n'/\\n}
    value=${value//$'\r'/\\r}
    value=${value//$'\t'/\\t}
    config+="$key = \"$value\""$'\n'
  done
  command curl -q --config /dev/fd/3 3< <(printf '%s' "$config")
}
