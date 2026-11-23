"""Minimal client for the OpenFIGI v3 mapping API.

OpenFIGI is Bloomberg's free, open identifier service. Without an API key it
allows 10 jobs per request and 25 requests per minute; with a key, 100 jobs per
request and 250 requests per minute. This client batches jobs to stay within
the per-request limit and retries once on HTTP 429 using the Retry-After header.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from .identifiers import IdType, normalize

__all__ = ["OPENFIGI_ID_TYPES", "FigiResult", "OpenFIGIClient"]

MAPPING_URL = "https://api.openfigi.com/v3/mapping"

OPENFIGI_ID_TYPES = {
    IdType.ISIN: "ID_ISIN",
    IdType.CUSIP: "ID_CUSIP",
    IdType.SEDOL: "ID_SEDOL",
}


@dataclass
class FigiResult:
    """Result for one identifier sent to OpenFIGI."""

    id_type: str
    id_value: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    message: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.matches)


class OpenFIGIClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
        url: str = MAPPING_URL,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("OPENFIGI_API_KEY")
        self.batch_size = 100 if self.api_key else 10
        self.url = url
        self._client = client or httpx.Client(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        return headers

    def _post(self, jobs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
        response = self._client.post(self.url, json=list(jobs), headers=self._headers())
        if response.status_code == 429:
            wait = float(response.headers.get("retry-after", "6"))
            time.sleep(min(wait, 60.0))
            response = self._client.post(self.url, json=list(jobs), headers=self._headers())
        response.raise_for_status()
        return response.json()

    def map(self, identifiers: Iterable[tuple[IdType | str, str]]) -> list[FigiResult]:
        """Map (id_type, id_value) pairs to FIGIs, preserving input order.

        id_type may be an IdType or a raw OpenFIGI idType such as "TICKER".
        """
        jobs: list[dict[str, Any]] = []
        for id_type, id_value in identifiers:
            raw_type = OPENFIGI_ID_TYPES.get(id_type, id_type) if isinstance(id_type, IdType) else id_type
            jobs.append({"idType": raw_type, "idValue": normalize(id_value)})

        results: list[FigiResult] = []
        for start in range(0, len(jobs), self.batch_size):
            batch = jobs[start : start + self.batch_size]
            for job, item in zip(batch, self._post(batch)):
                results.append(
                    FigiResult(
                        id_type=job["idType"],
                        id_value=job["idValue"],
                        matches=item.get("data", []),
                        message=item.get("warning") or item.get("error"),
                    )
                )
        return results

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenFIGIClient:  # noqa: PYI034 (typing.Self needs 3.11)
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
