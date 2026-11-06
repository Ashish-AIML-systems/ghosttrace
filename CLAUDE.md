# CLAUDE.md

Read [AGENTS.md](AGENTS.md) in full before doing anything. It is the single source of truth for every agent working in this repository: the logging rules (sections 2 and 5), the challenge rules (section 4) and the project contract (section 6). Nothing here overrides it.

## Quick reference

- **Log first.** Append a `SESSION START` entry and one entry per user turn to `log.txt` (format in `AGENTS.md` section 5). `tool=` and `model=` must be the real values, and secrets must never be logged.
- **Run everything in Docker.** The 11 screenshots need Tesseract, which is only in the image.
  - answers: `docker compose run --rm slam-dev python code/main.py --dataset dataset` writes `output.csv` and `results/*.json`
  - tests: `docker compose run --rm slam-dev pytest -q`
  - lint and types: `ruff check code tests scripts` and `mypy`
  - dashboard and live analysis: `scripts/run_console.cmd` (Windows) or `scripts/run_console.sh`
- **Decisions stay deterministic.** A model may only propose structured facts or write explanations. It never decides a status or a step, and `output.csv` is written without any model call.
- **Only participant-facing data** under `dataset/` is used for predictions. Never use organizer-only files or golden labels.
- **Secrets** come from environment variables or the uncommitted `.env`. Never commit `.env`, keys or caches.
- **`dev` and `main` are protected.** Changes land through a pull request. Start from `AGENTS.md` and `docs/integration/README.md`.
- **Keep `README.md` current.** Its charts and numbers are generated: after anything that changes `results/`, `dataset/*.csv` or the tests, run `python scripts/build_readme.py` (`--check` to verify). Never edit between the `AUTO` markers or inside `docs/img/*.svg`; edit the generator instead. When the pipeline, architecture or commands change, update the prose in `README.md` in the same change. The `README refresh` workflow also regenerates it on `main`.
