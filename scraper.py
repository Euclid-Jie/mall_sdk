# -*- coding: utf-8 -*-
"""Reusable web scraping helpers for FOF99 pages.

This module intentionally lives outside the ``fof99`` SDK package because that
package is vendor-supplied code.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pandas as pd
import requests


class FOF99ScrapeError(RuntimeError):
    """Raised when a FOF99 web endpoint request fails."""


def load_dotenv_value(
    key: str, env_path: str | Path = ".env", encoding: str = "utf-8"
) -> Optional[str]:
    """Read a single key from a simple .env file without extra dependencies."""
    path = Path(env_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    if not path.exists():
        return None

    for line in path.read_text(encoding=encoding).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip("\"'")
    return None


def get_fof99_web_token(env_path: str | Path = ".env") -> Optional[str]:
    """Return FOF99 web token from environment or project .env."""
    return os.getenv("FOF99_WEB_TOKEN") or load_dotenv_value(
        "FOF99_WEB_TOKEN", env_path=env_path
    )


@dataclass
class FOF99WebScraper:
    """Client for the web endpoints behind ``mp.fof99.com`` pages."""

    token: Optional[str] = None
    base_url: str = "https://api.huofuniu.com"
    timeout: int = 30
    session: Optional[requests.Session] = None

    def __post_init__(self) -> None:
        if self.token is None:
            self.token = get_fof99_web_token()
        if not self.token:
            raise ValueError("token is required; set FOF99_WEB_TOKEN in .env")
        self.base_url = self.base_url.rstrip("/")
        if self.session is None:
            self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://mp.fof99.com",
                "Referer": "https://mp.fof99.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
            }
        )

    def _get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise FOF99ScrapeError(f"Unexpected response: {payload!r}")
        if payload.get("error_code") != 0:
            raise FOF99ScrapeError(
                f"{path} failed: error_code={payload.get('error_code')} "
                f"msg={payload.get('msg')!r}"
            )
        return payload

    def get_fund_nav(
        self,
        fid: str,
        source: Optional[int] = None,
        order: int = 1,
        page_size: int = 500,
        use_df: bool = True,
    ) -> pd.DataFrame | List[Dict[str, Any]]:
        """Fetch the NAV table shown on ``/fund/view/{fid}``.

        When ``source`` is omitted, the scraper tries team/company NAV first
        and falls back to platform NAV. The API returns ``pc`` as a decimal
        return; the normalized ``change_pct`` value is already multiplied by
        100.
        """
        if not fid:
            raise ValueError("fid is required")
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        sources = [source] if source is not None else [2, 1]
        rows = self._fetch_first_non_empty_nav(
            fid=fid,
            sources=sources,
            order=order,
            page_size=page_size,
        )

        if use_df:
            return pd.DataFrame(rows)
        return rows

    def _fetch_first_non_empty_nav(
        self,
        fid: str,
        sources: Sequence[int],
        order: int,
        page_size: int,
    ) -> List[Dict[str, Any]]:
        for source in sources:
            rows = self._fetch_nav_by_source(
                fid=fid, source=source, order=order, page_size=page_size
            )
            if rows:
                return rows
        return []

    def _fetch_nav_by_source(
        self,
        fid: str,
        source: int,
        order: int,
        page_size: int,
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        page = 1
        total: Optional[int] = None

        while True:
            payload = self._get(
                "/newgoapi/fund/priceList",
                {
                    "token": self.token,
                    "fid": fid,
                    "source": source,
                    "order": order,
                    "page": page,
                    "pagesize": page_size,
                },
            )
            data = payload.get("data") or {}
            page_rows = data.get("list") or []
            if not isinstance(page_rows, list):
                raise FOF99ScrapeError(f"Unexpected price list: {page_rows!r}")

            rows.extend(self._normalize_nav_rows(page_rows))
            total = data.get("total", total)
            if not page_rows:
                break
            if total is not None and page >= ceil(int(total) / page_size):
                break
            page += 1
        return rows

    @staticmethod
    def _normalize_nav_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for row in rows:
            change = row.get("pc")
            normalized.append(
                {
                    "date": row.get("pd"),
                    "unit_nav": row.get("pn"),
                    "cumulative_nav": row.get("cnw"),
                    "adjusted_nav": row.get("cn"),
                    "change_pct": change * 100 if change is not None else None,
                    "id": row.get("id"),
                    "fid": row.get("fid"),
                    "source": row.get("from_type"),
                    "insert_date": row.get("insert_date"),
                }
            )
        return normalized
