# results/

Files written by running the code. They are deterministic (no timestamps, no timings), so a rerun on the same data produces the same bytes. Do not edit them by hand.

| File | Written by | Contents |
|---|---|---|
| `run_summary.json` | `python code/main.py --dataset dataset` | cases, status counts, rows in `output.csv` and its SHA-256 |
| `sample_scores.json` | `python code/main.py --dataset dataset` | the 32 public samples scored against HackerRank's published answers: status accuracy, step precision, recall and F1, field and sequence accuracy, false COMPLETE count |
| `insight_summary.json` | `python code/main.py --dataset dataset --insight` | headline numbers of the failure-risk model, the failure patterns, the recreation-path graph and the stored model explanations |

The full per-case data behind the dashboard is `dashboard/insight_data.json`. The graded answer file is `output.csv` at the repository root.
