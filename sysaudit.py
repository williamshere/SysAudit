"""SysAudit: portable Windows system-inventory CLI.

Collects hardware, OS, software, network, and security posture, then writes
a professional HTML report and/or a JSON export. Local-first: no network
calls, no telemetry, no analytics.

Usage:
    python sysaudit.py [--format html|json|both] [--output DIR]
"""

import argparse
import os
import sys

from collectors import run_all
from report import write_reports


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="SysAudit: local-first Windows system inventory."
    )
    parser.add_argument(
        "--format",
        choices=("html", "json", "both"),
        default="both",
        help="report format to generate (default: both)",
    )
    parser.add_argument(
        "--output",
        default=".",
        help="directory to write reports into (default: current directory)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print("SysAudit: collecting system inventory...")
    inventory = run_all()
    print("SysAudit: generating reports...")
    written = write_reports(inventory, os.path.abspath(args.output), fmt=args.format)
    for path in written:
        print(f"  wrote {path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
