# Inference Correctness Risks: Hallucination and Looping

## Summary

Local inference hallucination and looping usually come from runtime integration issues, not just model intelligence. A strong model can degrade quickly if the engine misapplies the prompt template, sampler, cache positions, stop tokens, or model-specific positional encoding.

For the current MLX engine work, the most important split is:

- Model-format compatibility: weights, config, tokenizer, processor, and rotary behavior must match the model family.
- Runtime correctness: prompt construction, KV-cache position IDs, stop conditions, and sampling must preserve the model's training assumptions.
- Performance policy: prefill chunking, graph warm-up, and resident serving must improve speed without changing generated-token semantics.

## Root Causes

### Prompt Template Drift

Modern instruct models are sensitive to exact chat formatting. If LM Studio, MLX, or a custom engine uses the wrong chat template, the model may not see role boundaries, assistant prefixes, tool blocks, or end markers the way it was trained to expect.

Typical symptoms:

- assistant repeats the user prompt
- model writes both user and assistant turns
- responses continue past the expected stop point
- instruction following degrades even when weights are valid

Mitigation:

- Load the tokenizer's own `chat_template`.
- Golden-test prompt rendering for every supported model family.
- Keep template output snapshots in version control.
- Reject serving if tokenizer/config/template metadata is missing or ambiguous.

### Stop Token and EOS Mismatch

Looping often happens when the runtime does not stop on the model's actual end markers. Some models have multiple EOS or turn-end tokens. Others need stop strings in addition to token IDs.

Typical symptoms:

- model keeps generating assistant turns
- model starts a new user turn by itself
- model emits repeated separators or role tags
- generation only stops at `max_tokens`

Mitigation:

- Read EOS and stop-token metadata from tokenizer/config.
- Add per-family stop-token policies for Qwen, GPT-OSS, Llama-derived, and VLM families.
- Test that a short deterministic prompt stops before `max_tokens`.
- Return stop reason in the API response.

### Sampler Instability

Bad sampler defaults can turn minor uncertainty into loops. Temperature, top-p, top-k, min-p, repetition penalty, presence penalty, and frequency penalty interact. A model that is stable at one setting can loop at another.

Typical symptoms:

- repeated phrases
- high-confidence nonsense
- short loops after a correct opening
- sudden topic drift

Mitigation:

- Establish safe default sampler profiles per model family.
- Add a deterministic correctness profile with low temperature for validation.
- Add repetition metrics during test generation.
- Expose sampler settings but keep safe presets as the default.

### KV-Cache Position Bugs

KV-cache bugs are especially damaging because generation may look plausible for a few tokens and then collapse. Long context, chunked prefill, speculative decode, and multimodal token layouts all increase the risk.

Typical symptoms:

- answers degrade after long prompts
- repeated fragments after context reuse
- correct first token followed by incoherent continuation
- different output between single-pass and chunked prefill

Mitigation:

- Compare single-pass prefill vs chunked prefill on the same prompt and seed.
- Track absolute position IDs through cache updates.
- Add tests around long prompts, partial cache reuse, and prompt extension.
- Treat model-specific MROPE/IMROPE as a correctness gate before performance tuning.

### Rotary / MROPE / IMROPE Mismatch

Qwen3.6-family models use interleaved multimodal rotary behavior. If the engine treats the model as normal ROPE or non-interleaved MROPE, the model can run but attend to positions incorrectly.

Typical symptoms:

- plausible but unstable text
- worse long-context behavior
- broken image grounding
- output quality worse than the same checkpoint in a known-good runtime

Mitigation:

- Validate model config fields such as `mrope_interleaved`, `mrope_section`, `partial_rotary_factor`, and `rope_theta`.
- Compare lane ownership against a known-good implementation.
- Keep a repeatable parity probe per model family.

Current status:

- Qwen3.6 dense 27B and 35B-A3B MoE MLX configs passed the IMROPE lane-ownership parity probe against the puma/panthro rule.
- Evidence is recorded in `qwen3_6-imrope-parity-report.json` and `qwen-imrope-parity.md`.

### Processor and Image-Token Layout Drift

For VLMs, the text model is only part of correctness. Image processor behavior, patch layout, special image token placement, and multimodal position IDs must all match.

Typical symptoms:

- good text-only behavior but poor image answers
- model ignores the image
- hallucinated visual details
- failures only when images are included

Mitigation:

- Treat text-only and VLM correctness as separate gates.
- Snapshot image-token layout for known images.
- Compare processor output shapes and position IDs across runtimes.
- Add a small image QA benchmark with deterministic prompts.

## Engineering Controls

### Correctness Gate

Every supported model family should pass these checks before performance claims are accepted:

- config and tokenizer metadata load successfully
- chat-template rendering matches expected snapshots
- EOS and stop-token policy is explicit
- deterministic short prompt stops correctly
- single-pass and chunked prefill agree under deterministic sampling
- model-specific rotary behavior is validated
- VLM processors produce expected token and position layouts when applicable

### Performance Gate

Performance work should be accepted only when correctness remains stable:

- resident model serving avoids reload and graph compile costs
- prefill chunk-size policy is measured per model
- warm-up shapes are explicit
- prompt tokens/sec and generation tokens/sec are reported separately
- peak memory is reported with the selected policy
- benchmark output records device and Metal availability

### Product Gate

For a Mac local-inference engine, the user-facing platform should make correctness visible:

- report model family and detected backend
- report selected prompt template
- report stop reason
- report prefill policy
- expose safe sampler presets
- warn when running a model with incomplete compatibility metadata

## Current Conclusion

The immediate Qwen3.6 IMROPE compatibility risk is substantially reduced for the tested MLX checkpoints. The next correctness work should move to deterministic generation tests, chat-template snapshots, stop-token policy, and full VLM processor validation.
