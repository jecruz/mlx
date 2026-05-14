# launchd Packaging

This directory contains a template for running the resident MLX engine as a
macOS launchd job.

## Template

- `com.jecruz.mlx-engine.plist.template`
- `install.sh`
- `uninstall.sh`

Replace:

- `__REPO_ROOT__` with the repository/worktree path.
- `__MODEL_PATH__` with the MLX model directory.
- `__LOG_DIR__` with a writable log directory.
- `__LABEL__` with the launchd label.
- `__HOST__` with the bind host.
- `__PORT__` with the bind port.
- `__WARMUP_MODE__` with `sync`, `async`, or `off`.

The template uses:

- `bin/mlx-engine serve`
- `--warmup-mode async`
- `--require-gpu`

## Install

Render and lint the user LaunchAgent without loading it:

```bash
packaging/launchd/install.sh \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8
```

Render, lint, and load it:

```bash
packaging/launchd/install.sh \
  --model /Volumes/StudioStackSSD4TB/Development/LLM/lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8 \
  --load
```

The default rendered paths are:

- plist: `~/Library/LaunchAgents/com.jecruz.mlx-engine.plist`
- logs: `~/Library/Logs/mlx-engine/`

Use a temporary plist/log path for dry validation:

```bash
packaging/launchd/install.sh \
  --model /path/to/model \
  --plist-dir /tmp/mlx-engine-launchagents \
  --log-dir /tmp/mlx-engine-logs
```

## Uninstall

Unload and remove the rendered plist:

```bash
packaging/launchd/uninstall.sh
```

Unload but keep the plist:

```bash
packaging/launchd/uninstall.sh --keep-plist
```

## Readiness

launchd can keep the process running, but clients should use the packaged
readiness gate before sending latency-sensitive requests:

```bash
bin/mlx-engine ready \
  --base-url http://127.0.0.1:8765 \
  --require-gpu \
  --require-warmup
```

Use loaded readiness for process liveness:

```bash
bin/mlx-engine ready \
  --base-url http://127.0.0.1:8765 \
  --require-gpu
```
