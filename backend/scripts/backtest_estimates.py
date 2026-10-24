"""Write the aggregate walk-forward estimate report from real order events.

By default only the clearly labelled simulated-history dataset is read. For a
real database, explicitly use `--data-source real --idempotency-prefix ""`.
"""

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.services.backtest_service import build_report, load_history, replay_history
from app.services.history_seed_service import SIMULATED_FILE_PREFIX, SIMULATED_HISTORY_PREFIX

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = BACKEND_ROOT / "estimate_backtest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--data-source", choices=["simulated", "real"], default="simulated")
    parser.add_argument("--idempotency-prefix", default=None)
    args = parser.parse_args()
    prefix = args.idempotency_prefix
    if prefix is None:
        prefix = SIMULATED_HISTORY_PREFIX if args.data_source == "simulated" else ""
    if args.data_source == "simulated" and not prefix.startswith("simulated-history-"):
        parser.error("a simulated report must only read a simulated-history-* dataset")
    storage_prefix = SIMULATED_FILE_PREFIX if args.data_source == "simulated" else ""

    with SessionLocal() as session:
        result = replay_history(
            load_history(
                session,
                idempotency_prefix=prefix,
                storage_key_prefix=storage_prefix,
            )
        )
    report = build_report(result, data_source=args.data_source)
    args.output.write_text(json.dumps(report, indent=2) + "\n")

    overall = report["overall"]
    print(f"Data source: {args.data_source}; orders read: {report['orders_read']}")
    print(f"Evaluated: {overall['n']}; warm-up skipped: {report['skipped_warmup']}")
    print(f"Rule MAE: {overall['rule_mae_minutes']} minutes")
    print(f"Global-average MAE: {overall['baseline_mae_minutes']} minutes")
    print(f"Wrote {args.output}")
    return 0 if overall["n"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
