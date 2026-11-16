"""Publish the requirements tables (Markdown) as a Kiwi Test Plan description.

Kiwi has no wiki, but a Test Plan's description is rendered Markdown (tables
included) and the plan appears in the dashboard's plan list.

    python import_requirements.py docs/exigences.md --product "Budget Tracker"

Re-running updates the same plan. Credentials come from ~/.tcms.conf.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from import_xlsx import KiwiRpcClient, insecure_tls_allowed, read_kiwi_url

DEFAULT_PLAN_NAME = "Exigences (BF / NFR)"


def read_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def publish_requirements(client, product: str, plan_name: str, text: str) -> int:
    plan_id = client.ensure_plan(product, plan_name)
    client.set_plan_text(plan_id, text)
    return plan_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("--product", required=True)
    parser.add_argument("--plan-name", default=DEFAULT_PLAN_NAME)
    args = parser.parse_args(argv)

    import os

    if os.environ.get("KIWI_INSECURE_TLS") == "1":  # LOCAL TESTING ONLY
        url = read_kiwi_url(Path.home() / ".tcms.conf")
        if not insecure_tls_allowed(url):
            print(f"Refusing KIWI_INSECURE_TLS: {url or 'no url'} is not a loopback address", file=sys.stderr)
            return 2
        import ssl

        ssl._create_default_https_context = ssl._create_unverified_context

    plan_id = publish_requirements(KiwiRpcClient(), args.product, args.plan_name, read_markdown(args.markdown))
    print(f"Published '{args.plan_name}' as test plan #{plan_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
