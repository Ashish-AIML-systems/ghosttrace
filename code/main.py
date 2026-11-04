"""SLAM command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from slam.config import Settings
from slam.contracts import CONTRACT_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SLAM deletion-audit agent")
    parser.add_argument("--dataset", type=Path, help="participant dataset directory")
    parser.add_argument("--foundation-status", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = Settings()
    if args.foundation_status or args.dataset is None:
        print(
            f"SLAM foundation contract={CONTRACT_VERSION} "
            f"provider={settings.model_provider.value} model={settings.model}"
        )
        if args.dataset is None:
            return 0
    raise SystemExit(
        "The shared foundation is ready; ingestion, reconstruction, and planning "
        "must be integrated before a dataset run."
    )


if __name__ == "__main__":
    raise SystemExit(main())
