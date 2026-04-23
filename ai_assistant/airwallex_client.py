"""Airwallex REST API wrapper — transactions and balances.

Auth flow: exchange (client_id, api_key) for a short-lived bearer token
via /api/v1/authentication/login, then reuse the token until it expires.
Docs: https://www.airwallex.com/docs/api
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# Access tokens expire after ~30 min. Refresh 5 min early to be safe.
_TOKEN_LIFETIME_SEC = 25 * 60


class AirwallexError(RuntimeError):
    pass


class Airwallex:
    def __init__(self, client_id: str, api_key: str, base_url: str):
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ---------- auth ----------

    def _authenticate(self) -> None:
        resp = requests.post(
            f"{self.base_url}/api/v1/authentication/login",
            headers={
                "x-client-id": self.client_id,
                "x-api-key": self.api_key,
            },
            timeout=30,
        )
        if resp.status_code != 201 and resp.status_code != 200:
            raise AirwallexError(
                f"Airwallex auth failed ({resp.status_code}): {resp.text[:200]}"
            )
        data = resp.json()
        self._token = data.get("token")
        if not self._token:
            raise AirwallexError(f"No token in auth response: {data}")
        self._token_expires_at = time.time() + _TOKEN_LIFETIME_SEC
        logger.info("Airwallex auth OK")

    def _ensure_auth(self) -> None:
        if not self._token or time.time() >= self._token_expires_at:
            self._authenticate()

    # ---------- requests ----------

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._ensure_auth()
        resp = requests.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self._token}"},
            params=params,
            timeout=30,
        )
        if resp.status_code == 401:
            # Token may have been invalidated server-side — re-auth once
            self._token = None
            self._ensure_auth()
            resp = requests.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                params=params,
                timeout=30,
            )
        if not resp.ok:
            raise AirwallexError(
                f"Airwallex GET {path} failed ({resp.status_code}): "
                f"{resp.text[:300]}"
            )
        return resp.json()

    # ---------- public API ----------

    def get_balances(self) -> list[dict]:
        """Current balance per currency across all accounts."""
        data = self._get("/api/v1/balances/current")
        if isinstance(data, list):
            return data
        # Some Airwallex endpoints wrap lists in {items: []}
        return data.get("items", data.get("balances", []))

    def list_transactions(
        self, from_time: datetime, to_time: datetime
    ) -> list[dict]:
        """List financial transactions in [from_time, to_time).

        Airwallex /financial_transactions returns items newest-first and
        ignores cursor-style pagination params on this endpoint, so we
        page by narrowing `to_created_at` toward the oldest seen item.
        """
        from datetime import timedelta as _td

        all_items: list[dict] = []
        seen_ids: set[str] = set()
        upper = to_time

        for _ in range(50):  # hard cap to prevent runaway pagination
            params = {
                "from_created_at": from_time.isoformat(),
                "to_created_at": upper.isoformat(),
                "page_size": 1000,
            }
            data = self._get("/api/v1/financial_transactions", params=params)
            items = data.get("items", [])
            new_items = [it for it in items if it.get("id") not in seen_ids]
            if not new_items:
                break
            for it in new_items:
                seen_ids.add(it.get("id"))
            all_items.extend(new_items)

            if not data.get("has_more"):
                break

            # Step upper back to the oldest item's created_at to fetch next page
            oldest = items[-1].get("created_at")
            if not oldest:
                break
            try:
                upper = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
                upper -= _td(milliseconds=1)
            except ValueError:
                break

        return all_items
