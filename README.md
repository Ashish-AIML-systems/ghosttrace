# SLAM — Ghost Data Still Exists

SLAM is the planned portable, AI-assisted deletion-audit agent for the HackerRank Orchestrate challenge. The latest approved architecture uses deterministic evidence and policy logic with bounded API-based structured extraction. It does not use Ollama, `llama.cpp`, local model weights, or a GPU-specific development path.

## Start here

- [Revised implementation plan](docs/REVISED_SLAM_PLAN.md)
- [Four-person handoff index](team_handoff/README.md)
- [Shared build contract](team_handoff/SHARED_BUILD_CONTRACT.md)
- [Official participant problem statement](team_handoff/reference/problem_statement.md)

## Team split

| Owner | Workstream |
|---|---|
| Ashish | Evidence ingestion, parsing, normalization, provenance ledger |
| Manya | Request intent, historical identity, temporal state, dependency graph |
| Satvika | Policy, decision, ordered remediation and verification, output export |
| Lalith | Contracts, API adapter, Docker, evaluation, orchestration, integration |

## Development environment

Docker and Compose provide the shared toolchain. Until application code and its lock file are added, the image is only a reproducible Python/uv foundation.

```bash
docker compose build
docker compose run --rm slam-dev
```

Before the application dependency file exists, the second command runs a
Python and SQLite FTS5 foundation check. After `pyproject.toml` is added, the
same command installs the locked environment and runs the test suite.

The default provider is `fake`, so normal tests cannot spend money or require credentials. For a deliberately authorized API run, copy `.env.example` to `.env`, set an explicit provider/model and positive budget, and add the API key locally. Never commit `.env`.

No implementation accuracy or hidden-set performance is claimed by the planning artifacts in this repository.
