#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  uninstall.sh [options]

Options:
  --label LABEL       launchd label. Defaults to com.jecruz.mlx-engine.
  --plist-dir PATH    LaunchAgent directory. Defaults to ~/Library/LaunchAgents.
  --keep-plist        Unload but keep the rendered plist file.
  -h, --help          Show this help.
USAGE
}

label="com.jecruz.mlx-engine"
plist_dir="$HOME/Library/LaunchAgents"
keep_plist="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label)
      label="$2"
      shift 2
      ;;
    --plist-dir)
      plist_dir="$2"
      shift 2
      ;;
    --keep-plist)
      keep_plist="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

plist_path="$plist_dir/$label.plist"
launchctl bootout "gui/$(id -u)" "$plist_path" >/dev/null 2>&1 || true

if [[ "$keep_plist" != "true" && -f "$plist_path" ]]; then
  rm -f "$plist_path"
fi

echo "mlx_engine_launchd_unloaded $label"
if [[ "$keep_plist" == "true" ]]; then
  echo "mlx_engine_launchd_plist_kept $plist_path"
else
  echo "mlx_engine_launchd_plist_removed $plist_path"
fi
