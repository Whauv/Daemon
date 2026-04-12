# Contributing

## Development Flow

1. Create a feature branch from the current working branch.
2. Keep source changes under `src/daemon`.
3. Add or update tests in `tests/`.
4. Run the local regression suite before opening a pull request.

## Local Checks

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Pull Requests

- Explain the problem being solved
- Summarize architectural or contract changes
- Mention any new environment variables or runtime assumptions
