#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  install.sh --model MODEL_PATH [options]

Options:
  --repo-root PATH      Repository root. Defaults to this checkout.
  --label LABEL         launchd label. Defaults to com.jecruz.mlx-engine.
  --host HOST           Bind host. Defaults to 127.0.0.1.
  --port PORT           Bind port. Defaults to 8765.
  --log-dir PATH        Log directory. Defaults to ~/Library/Logs/mlx-engine.
  --plist-dir PATH      LaunchAgent directory. Defaults to ~/Library/LaunchAgents.
  --warmup-mode MODE    sync, async, or off. Defaults to async.
  --load                Bootstrap the LaunchAgent after rendering.
  -h, --help            Show this help.
USAGE
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
label="com.jecruz.mlx-engine"
host="127.0.0.1"
port="8765"
log_dir="$HOME/Library/Logs/mlx-engine"
plist_dir="$HOME/Library/LaunchAgents"
warmup_mode="async"
model_path=""
load_after_render="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      repo_root="$2"
      shift 2
      ;;
    --label)
      label="$2"
      shift 2
      ;;
    --host)
      host="$2"
      shift 2
      ;;
    --port)
      port="$2"
      shift 2
      ;;
    --log-dir)
      log_dir="$2"
      shift 2
      ;;
    --plist-dir)
      plist_dir="$2"
      shift 2
      ;;
    --warmup-mode)
      warmup_mode="$2"
      shift 2
      ;;
    --model)
      model_path="$2"
      shift 2
      ;;
    --load)
      load_after_render="true"
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

if [[ -z "$model_path" ]]; then
  echo "--model is required" >&2
  usage >&2
  exit 2
fi

case "$warmup_mode" in
  sync|async|off) ;;
  *)
    echo "--warmup-mode must be sync, async, or off" >&2
    exit 2
    ;;
esac

if [[ ! -x "$repo_root/bin/mlx-engine" ]]; then
  echo "missing executable: $repo_root/bin/mlx-engine" >&2
  exit 1
fi

template="$script_dir/com.jecruz.mlx-engine.plist.template"
plist_path="$plist_dir/$label.plist"
mkdir -p "$log_dir" "$plist_dir"

python3 - "$template" "$plist_path" "$repo_root" "$model_path" "$log_dir" "$label" "$host" "$port" "$warmup_mode" <<'PY'
from pathlib import Path
import sys
from xml.sax.saxutils import escape

template, plist_path, repo_root, model_path, log_dir, label, host, port, warmup_mode = sys.argv[1:]
text = Path(template).read_text()
replacements = {
    "__REPO_ROOT__": repo_root,
    "__MODEL_PATH__": model_path,
    "__LOG_DIR__": log_dir,
    "__LABEL__": label,
    "__HOST__": host,
    "__PORT__": port,
    "__WARMUP_MODE__": warmup_mode,
}
for key, value in replacements.items():
    text = text.replace(key, escape(value))
Path(plist_path).write_text(text)
PY

plutil -lint "$plist_path"

if [[ "$load_after_render" == "true" ]]; then
  launchctl bootout "gui/$(id -u)" "$plist_path" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$plist_path"
fi

echo "mlx_engine_launchd_plist $plist_path"
echo "mlx_engine_launchd_logs $log_dir"
if [[ "$load_after_render" == "true" ]]; then
  echo "mlx_engine_launchd_loaded $label"
fi
