# Repository Guidelines

## Project Structure & Module Organization
- Source: `src/` (core modules, agents, utilities). Keep public APIs shallow; move internals under `src/<feature>/`.
- Tests: `tests/` mirrors `src/` (e.g., `tests/<feature>/test_*.py` or `*.test.ts`).
- Config & scripts: `configs/`, `scripts/`, and `.env.example` for local configuration.
- Assets & docs: `assets/` for fixtures or static files, `docs/` for design notes.

## Build, Test, and Development Commands
- Build: use the project’s task runner. Common patterns: `make build`, `npm run build`, or `python -m build`.
- Test: `make test`, `pytest -q`, `npm test`/`vitest`, or `cargo test` (match what exists here: `Makefile`, `package.json`, `pyproject.toml`, or `Cargo.toml`).
- Lint/Format: `make lint`, `ruff check`, `black .`, `eslint .`, or `prettier --check .`.
- Run locally: `make run`, `python -m src`, `npm run dev`, or `cargo run`.

## Coding Style & Naming Conventions
- Indentation: Python 4 spaces; JS/TS 2 spaces; Rust `rustfmt` defaults.
- Naming: modules/files `snake_case` (Py) or `kebab-case` (JS); classes `PascalCase`; functions/vars `snake_case` (Py) or `camelCase` (JS/TS).
- Formatting: auto-format on save. Use `black` (Py), `prettier` (JS/TS), `rustfmt` (Rust). Address lints (`ruff`, `eslint`, `clippy`) before committing.

## Testing Guidelines
- Scope: prefer fast, deterministic unit tests; add integration tests around IO or external APIs with fakes.
- Layout: mirror `src/` structure; Python files as `test_*.py`, JS/TS as `*.test.ts`/`*.spec.ts`.
- Running: `make test` or the language-specific command above. Aim to keep new code covered.

## Commit & Pull Request Guidelines
- Commits: follow Conventional Commits (e.g., `feat: add retry to tool runner`, `fix(agent): handle empty config`). Keep diffs focused.
- PRs: include purpose, approach, and tradeoffs; link issues; attach logs/screenshots for UX; list tests added/affected; update docs when behavior changes.

## Security & Configuration Tips
- Config via environment only. Copy `.env.example` → `.env` locally; never commit secrets.
- Avoid network access in tests; use stubs/mocks. Gate external calls behind interfaces for easy testing.

## Agent-Specific Notes
- Common envs: `OPENAI_API_KEY`, model names, and rate limits. Provide safe defaults and clear errors when unset.
- Reproducibility: prefer deterministic seeds and captured fixtures for model calls during tests.
