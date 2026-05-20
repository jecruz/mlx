"""Prefix-cache bookkeeping helpers that do not initialize MLX runtime state."""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from typing import Any


class PrefixOpportunityTracker:
    def __init__(self, *, max_recent: int = 32, min_match_tokens: int = 32):
        self.max_recent = max_recent
        self.min_match_tokens = min_match_tokens
        self.lock = threading.Lock()
        self.recent_prompts = deque()
        self.exact_token_index: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()

    @staticmethod
    def _hash_tokens(tokens: list[int]) -> str:
        payload = ",".join(str(token) for token in tokens).encode("utf-8")
        return hashlib.blake2b(payload, digest_size=16).hexdigest()

    @staticmethod
    def _common_prefix_len(left: list[int], right: list[int]) -> int:
        count = 0
        for left_token, right_token in zip(left, right, strict=False):
            if left_token != right_token:
                break
            count += 1
        return count

    def inspect(self, *, prompt: str, tokens: list[int]) -> dict[str, Any]:
        prompt_hash = self._hash_text(prompt)
        token_hash = self._hash_tokens(tokens)
        token_count = len(tokens)

        with self.lock:
            exact_match = self.exact_token_index.get(token_hash)
            best_match = {
                "request_id": None,
                "prompt_hash": None,
                "tokenized_prompt_hash": None,
                "tokens": [],
                "match_tokens": 0,
            }
            prefix_lookup_path = "scan"
            prefix_lookup_fast_path = False
            prefix_scan_candidates = 0
            if exact_match is not None and exact_match["tokens"] == tokens:
                best_match = {**exact_match, "match_tokens": token_count}
                prefix_lookup_path = "exact_token_hash"
                prefix_lookup_fast_path = True
            else:
                for prior in self.recent_prompts:
                    prefix_scan_candidates += 1
                    match_tokens = self._common_prefix_len(tokens, prior["tokens"])
                    if match_tokens > best_match["match_tokens"]:
                        best_match = {**prior, "match_tokens": match_tokens}

            longest_prefix_match_tokens = int(best_match["match_tokens"])
            prefix_reuse_ratio = (
                longest_prefix_match_tokens / token_count if token_count else 0.0
            )
            estimated_recompute_tokens = max(token_count - longest_prefix_match_tokens, 0)
            cache_candidate = longest_prefix_match_tokens >= self.min_match_tokens
            return {
                "prompt_hash": prompt_hash,
                "tokenized_prompt_hash": token_hash,
                "prefix_signature": (
                    self._hash_tokens(tokens[: min(token_count, self.min_match_tokens)])
                    if tokens
                    else None
                ),
                "longest_prefix_match_tokens": longest_prefix_match_tokens,
                "prefix_reuse_ratio": prefix_reuse_ratio,
                "estimated_recompute_tokens": estimated_recompute_tokens,
                "cache_candidate": cache_candidate,
                "matched_request_id": best_match["request_id"],
                "matched_prompt_hash": best_match["prompt_hash"],
                "matched_tokenized_prompt_hash": best_match["tokenized_prompt_hash"],
                "prefix_tracker_recent_size": len(self.recent_prompts),
                "prefix_lookup_fast_path": prefix_lookup_fast_path,
                "prefix_lookup_path": prefix_lookup_path,
                "prefix_scan_candidates": prefix_scan_candidates,
            }

    def record(self, *, request_id: str, prompt: str, tokens: list[int]) -> None:
        entry = {
            "request_id": request_id,
            "prompt_hash": self._hash_text(prompt),
            "tokenized_prompt_hash": self._hash_tokens(tokens),
            "tokens": list(tokens),
        }
        with self.lock:
            while len(self.recent_prompts) >= self.max_recent:
                evicted = self.recent_prompts.popleft()
                evicted_hash = evicted["tokenized_prompt_hash"]
                if self.exact_token_index.get(evicted_hash) is evicted:
                    self.exact_token_index.pop(evicted_hash, None)
            self.recent_prompts.append(entry)
            self.exact_token_index[entry["tokenized_prompt_hash"]] = entry

    def record_tokens(
        self,
        *,
        request_id: str,
        prompt: str,
        tokens: list[int],
    ) -> None:
        self.record(request_id=request_id, prompt=prompt, tokens=tokens)
