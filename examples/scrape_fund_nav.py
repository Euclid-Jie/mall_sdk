# -*- coding: utf-8 -*-
"""Fetch NAV rows from a FOF99 fund detail page without opening a browser."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper import FOF99WebScraper


def parse_fid(value: str) -> str:
    match = re.search(r"/fund/view/([^/?#]+)", value)
    return match.group(1) if match else value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fund",
        help="Fund id or page URL, for example https://mp.fof99.com/fund/view/...",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="FOF99 web token. Defaults to FOF99_WEB_TOKEN from env or .env.",
    )
    parser.add_argument("--page-size", type=int, default=500)
    args = parser.parse_args()

    scraper = FOF99WebScraper(token=args.token)
    df = scraper.get_fund_nav(parse_fid(args.fund), page_size=args.page_size)
    df.to_csv("examples/examples_fund_nav.csv", index=False)


if __name__ == "__main__":
    main()
