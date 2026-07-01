# -*- coding: utf-8 -*-
"""Fetch NAV rows from a FOF99 fund detail page without opening a browser."""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from FOF99Api import FOF99Api
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

    api = FOF99Api(token=args.token or "")
    basic_info = api.get_fund_basic_info_from_id(args.fund)
    print("基金基本信息:")
    for key, value in basic_info.items():
        print(f"{key}: {value}")

    scraper = FOF99WebScraper(token=args.token)
    df = scraper.get_fund_nav(parse_fid(args.fund), page_size=args.page_size)
    output_path = Path(__file__).with_name("examples_fund_nav.csv")
    df.to_csv(output_path, index=False)
    print(f"\n净值行数: {len(df)}")
    print(f"净值样例已写入: {output_path}")
    print(df.head(5).to_string(index=False))


if __name__ == "__main__":
    # .\.venv\Scripts\python.exe examples\scrape_fund_nav.py 1efcf35e914e1b54
    main()
