# Contributing

## Setup

```
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Guidelines

- Keep the dependency count low. Ask before adding a new one.
- Every sampler mode must be covered by a test with the subprocess or HTTP call mocked.
  Do not add a test that requires a real GPU or a real Ollama server, CI does not have either.
- Run `uv run ruff format .` before committing.
- Match the existing style: dataclasses for data, no framework beyond httpx, rich and argparse.
- Update `CHANGELOG.md` for any user-visible change.

## Reporting a bug

Open an issue with the command you ran, the full output including `--json` if possible, your
platform (macOS or Linux), and which sampler mode was selected (printed at the top of the
terminal output).
