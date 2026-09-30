"""Synthetic prompt text of an approximate target token count.

We do not tokenize with the target model's real tokenizer (that would add a
heavy dependency for a load generator). Instead we use the common rule of
thumb that English text averages about 0.75 words per token and build a
prompt of the matching word count from a small pool of varied technical
sentences. The token count in the report is always labeled "approx" for this
reason.
"""

from __future__ import annotations

_SENTENCES = [
    "Summarize the trade-offs of eventual consistency in a distributed key-value store.",
    "Explain why a hash join can beat a nested loop join on a large unsorted table.",
    "Describe how a bloom filter reduces disk reads in a log-structured merge tree.",
    "Compare optimistic and pessimistic locking for a high-contention counter.",
    "Walk through what happens when a TCP connection hits a retransmission timeout.",
    "Explain the difference between a page fault and a segmentation fault.",
    "Describe how consistent hashing avoids a full remap when a node joins a cluster.",
    "Explain why garbage collection pauses matter for a low-latency trading system.",
    "Compare a write-ahead log to a copy-on-write B-tree for crash recovery.",
    "Describe what makes a cache stampede happen and one way to prevent it.",
]


def build_prompt(target_tokens: int) -> str:
    """Return a prompt of roughly `target_tokens` tokens, minimum a few words."""
    target_tokens = max(int(target_tokens), 1)
    word_target = max(int(target_tokens * 0.75), 4)
    words: list[str] = []
    i = 0
    while len(words) < word_target:
        words.extend(_SENTENCES[i % len(_SENTENCES)].split())
        i += 1
    body = " ".join(words[:word_target])
    return f"{body}\nRespond with a short paragraph."
