# Copyright © 2023-2024 Apple Inc.

import argparse
import json
import sys
import time
from pathlib import Path

import mlx.core as mx


def parse_args():
    parser = argparse.ArgumentParser(
        description="Load one model once and sweep prompt prefill lengths."
    )
    parser.add_argument("--model", required=True, help="Local model directory.")
    parser.add_argument("--adapter-path", default=None)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=1)
    parser.add_argument("--prefill-step-size", type=int, default=None)
    parser.add_argument(
        "--prompt-token-lengths",
        default="8,16,32,64,128,256",
        help="Comma-separated synthetic prompt token lengths to measure.",
    )
    parser.add_argument("--warmup-prompt-tokens", type=int, default=64)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--output-jsonl", type=Path, default=None)
    parser.add_argument("--require-gpu", action="store_true")
    return parser.parse_args()


def detect_backend(model_path: str) -> str:
    config_path = Path(model_path) / "config.json"
    config = json.loads(config_path.read_text())
    architectures = config.get("architectures") or []
    if config.get("model_type") == "gpt_oss":
        return "text"
    if any(str(arch).endswith("ForConditionalGeneration") for arch in architectures):
        if not any("VL" in str(arch) or "Vision" in str(arch) for arch in architectures):
            return "text"
    if any(
        key in config
        for key in ("vision_tower", "audio_tower", "vision_config", "audio_config")
    ):
        return "vlm"
    return "text"


def runtime_device_info():
    return {
        "metal_available": bool(mx.metal.is_available()),
        "default_device": str(mx.default_device()),
    }


def parse_lengths(raw: str):
    try:
        lengths = [int(part.strip()) for part in raw.split(",") if part.strip()]
    except ValueError as exc:
        raise SystemExit(f"invalid --prompt-token-lengths: {raw}") from exc
    if not lengths or any(length <= 0 for length in lengths):
        raise SystemExit("--prompt-token-lengths must contain positive integers")
    return lengths


def build_token_prompt(tokenizer, target_tokens: int):
    base = (
        "Prompt processing dominates inference latency because the full input must be "
        "encoded before the first token can be emitted. "
    )
    tokens = list(tokenizer.encode(base, add_special_tokens=False))
    if not tokens:
        raise RuntimeError("Tokenizer produced no tokens for the base prompt.")
    while len(tokens) < target_tokens:
        tokens.extend(tokens[: max(1, min(len(tokens), target_tokens - len(tokens)))])
    return tokens[:target_tokens]


def run_once(
    *,
    model,
    processor,
    stream_generate,
    backend: str,
    tokenizer,
    prompt_tokens: int,
    max_tokens: int,
    prefill_step_size: int | None,
):
    token_prompt = build_token_prompt(tokenizer, prompt_tokens)
    run_kwargs = {"max_tokens": max_tokens}
    if prefill_step_size is not None:
        run_kwargs["prefill_step_size"] = prefill_step_size

    if backend == "vlm":
        prompt = "placeholder"
        run_kwargs["temperature"] = 0.0
        run_kwargs["input_ids"] = mx.array([token_prompt])
        run_kwargs["mask"] = mx.ones_like(run_kwargs["input_ids"])
    else:
        prompt = token_prompt

    run_t0 = time.perf_counter()
    result = None
    for response in stream_generate(model, processor, prompt, **run_kwargs):
        result = response
    run_ms = 1e3 * (time.perf_counter() - run_t0)
    if result is None:
        raise RuntimeError("No generation response returned")
    return {
        "requested_prompt_tokens": prompt_tokens,
        "prompt_tokens": int(result.prompt_tokens),
        "generation_tokens": int(result.generation_tokens),
        "run_ms": run_ms,
        "prompt_tps": float(result.prompt_tps),
        "generation_tps": float(result.generation_tps),
        "peak_memory_gb": float(result.peak_memory),
    }


def main():
    args = parse_args()
    backend = detect_backend(args.model)
    lengths = parse_lengths(args.prompt_token_lengths)
    device_info = runtime_device_info()
    print(f"mx.metal.is_available: {device_info['metal_available']}", flush=True)
    print(f"mx.default_device: {device_info['default_device']}", flush=True)

    if args.require_gpu and not (
        device_info["metal_available"] and "gpu" in device_info["default_device"]
    ):
        print(
            "error: --require-gpu was set, but MLX is not using a Metal GPU",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)

    if backend == "vlm":
        from mlx_vlm.generate import stream_generate
        from mlx_vlm.utils import load
    else:
        from mlx_lm.generate import stream_generate
        from mlx_lm.utils import load

    print("load: start", flush=True)
    load_t0 = time.perf_counter()
    if backend == "vlm":
        model, processor = load(
            args.model,
            adapter_path=args.adapter_path,
            revision=args.revision,
            force_download=args.force_download,
            trust_remote_code=args.trust_remote_code,
        )
    else:
        model, processor = load(
            args.model,
            adapter_path=args.adapter_path,
            revision=args.revision,
        )
    load_ms = 1e3 * (time.perf_counter() - load_t0)
    print(f"load: done ({load_ms:.2f} ms)", flush=True)

    tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    if args.warmup_runs > 0:
        print(
            f"warmup: {args.warmup_runs} run(s) at {args.warmup_prompt_tokens} prompt tokens",
            flush=True,
        )
    for _ in range(args.warmup_runs):
        run_once(
            model=model,
            processor=processor,
            stream_generate=stream_generate,
            backend=backend,
            tokenizer=tokenizer,
            prompt_tokens=args.warmup_prompt_tokens,
            max_tokens=args.max_tokens,
            prefill_step_size=args.prefill_step_size,
        )

    output = args.output_jsonl.open("w") if args.output_jsonl else None
    try:
        for prompt_tokens in lengths:
            for repeat in range(args.repeats):
                row = {
                    "model": args.model,
                    "backend": backend,
                    "metal_available": device_info["metal_available"],
                    "default_device": device_info["default_device"],
                    "load_ms": load_ms,
                    "warmup_runs": args.warmup_runs,
                    "warmup_prompt_tokens": args.warmup_prompt_tokens,
                    "repeat": repeat,
                    "max_tokens": args.max_tokens,
                    "prefill_step_size": args.prefill_step_size,
                }
                row.update(
                    run_once(
                        model=model,
                        processor=processor,
                        stream_generate=stream_generate,
                        backend=backend,
                        tokenizer=tokenizer,
                        prompt_tokens=prompt_tokens,
                        max_tokens=args.max_tokens,
                        prefill_step_size=args.prefill_step_size,
                    )
                )
                print(
                    "measure: "
                    f"tokens={row['prompt_tokens']} "
                    f"run_ms={row['run_ms']:.2f} "
                    f"prompt_tps={row['prompt_tps']:.3f} "
                    f"peak_memory_gb={row['peak_memory_gb']:.3f}",
                    flush=True,
                )
                line = json.dumps(row, sort_keys=True)
                if output:
                    output.write(line + "\n")
                    output.flush()
                else:
                    print(line)
    finally:
        if output:
            output.close()
            print(f"wrote {args.output_jsonl}", flush=True)


if __name__ == "__main__":
    main()
