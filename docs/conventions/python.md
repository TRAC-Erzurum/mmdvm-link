# Python conventions

Derived from the existing code. `AGENTS.md` links here; `python scripts/verify.py` enforces the mechanical parts.

## Style

- Formatting and lint are done by **ruff** (`pyproject.toml`): target `py311`, line length 100, rules `E`, `F`, `I`, `UP`, `B`.
- Run `python scripts/verify.py` before committing. Do not hand-format around the formatter; run `ruff format .` instead.
- Use type hints on public functions. Use built-in generics (`dict[str, str]`, `str | None`), not `typing.Dict` / `Optional`.
- Prefer `from __future__ import annotations` in new modules that use forward references (as `server/core/*` does).
- Docstrings and comments are in Turkish or English; match the surrounding file. Keep the first line short.
- Mark intentional exceptions locally with `# ruff: noqa: <code>` plus a reason, not with global ignores.

## Module layout

- Entry points are top-level scripts: `server/server_proto.py`, `client/client_proto.py`. Keep them thin: parse config, wire objects together, call `main()`.
- Server code lives in the `server` package and is imported as `server.core.*`. The entry point adds the repository root to `sys.path` so that import works from `server/`.
- Client code lives in the `client` package: `client/core/` for platform-neutral pieces (MQTT wrapper, identity), `client/agents/<platform>/` for platform code (Pi-Star).
- Keep modules focused. Shared state goes through `server/core/state.py`; do not reach into its internals from other modules.

## Configuration

- Server: read `os.environ` after `load_dotenv(SERVER_DIR / ".env")`. Required values go through a `_require_env` helper that logs the missing name and exits with status 1.
- Client: parse its own `.env` (stdlib only; no `python-dotenv` on the device). Real environment variables override file values.
- Parse integers and booleans with explicit defaults and clear error messages (see `_require_int_env` and `PERSIST_BINDINGS` handling).
- Every new variable must be documented in the matching `.env.example` and in `README.md`.

## Logging and output

- Each module defines `logger = logging.getLogger(__name__)`. Use `%s`-style lazy arguments, not f-strings, in log calls.
- `logging.basicConfig` is called only in entry points, never in library modules.
- The interactive server CLI uses `print()` for user-facing output. Diagnostics go through `logger`.
- Do not log secrets: tokens, passwords, and full `.env` contents. Log node IDs and topic names only.

## Secrets and state

- No secrets, tokens, or passwords in source code, examples, or tests. Use `.env` files (ignored by git) or environment variables.
- Installer tokens are stored as fingerprints (`state.py`), not in plain text. Keep that property when changing persistence.
- Generated files (`server/bindings.json`, `server/install_*.sh`) must stay out of git; see `.gitignore`.

## Concurrency

- Shared mutable state is guarded by a `threading.Lock`. Acquire it in the method that touches the data, not in callers.
- Background workers are `daemon=True` threads that receive everything they need as arguments. Do not close over loop variables.

## Dependencies

- Runtime dependencies go in `requirements.txt`; tooling goes in `requirements-dev.txt`.
- Do not add a dependency for a small helper that the standard library covers.
- Version bumps are separate tasks (see `AGENTS.md`).
