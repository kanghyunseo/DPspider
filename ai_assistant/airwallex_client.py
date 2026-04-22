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
        """Paginated list of transactions in [from_time, to_time)."""
        from_ts = int(from_time.timestamp() * 1000)
        to_ts = int(to_time.timestamp() * 1000)
        all_items: list[dict] = []
        page_after: str | None = None

        for _ in range(50):  # hard cap to prevent runaway pagination
            params = {
                "from_created_at_timestamp": from_ts,
                "to_created_at_timestamp": to_ts,
                "page_size": 100,
            }
            if page_after:
                params["page_after"] = page_after

            data = self._get("/api/v1/transactions", params=params)
            items = data.get("items", [])
            all_items.extend(items)

            page_after = data.get("page_after")
            if not page_after or not items:
                break

        return all_items
