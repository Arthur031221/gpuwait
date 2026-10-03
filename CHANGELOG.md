# Changelog

## Unreleased

- Include non-streamed reasoning text in the output estimate when a server omits token usage.
- Count streamed reasoning output from vLLM's legacy `reasoning_content` field toward TTFT and
  throughput.

## 0.1.0

Initial release.

- Sampler with three modes: `powermetrics --samplers gpu_power` on macOS when passwordless
  sudo is available, `nvidia-smi` on Linux, and an Ollama `/api/ps` plus request-timing
  fallback everywhere else. Sampler mode is auto-detected and never prompts for a password.
- Load generator over `httpx` and `asyncio`, concurrency 1, 4 and 16 by default, configurable
  prompt length, output length, think time, and streaming.
- Terminal timeline and summary table, `report.html` with a score, a bar chart and an inline
  SVG badge, and `--json` output.
- Stream parser counts a reasoning model's thinking tokens (`delta.reasoning`), not only
  `delta.content`, toward time-to-first-token and throughput. Without this, a model that
  spends its output budget thinking (Qwen3 in the default mode) reported a false zero
  throughput and no time-to-first-token.
- Measured idle percent at concurrency 1 and concurrency 16 against Ollama `qwen3:4b` on the
  reference machine, method documented in the README.
