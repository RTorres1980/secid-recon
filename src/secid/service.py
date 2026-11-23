"""HTTP service exposing validation, conversion, reconciliation and FIGI mapping.

Run locally with ``uvicorn secid.service:app``. Liveness and readiness probes
for Kubernetes are served at ``/healthz`` and ``/readyz``.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .identifiers import (
    IdType,
    InvalidIdentifier,
    cusip_to_isin,
    detect,
    isin_to_cusip,
    isin_to_sedol,
    normalize,
    sedol_to_isin,
)
from .openfigi import OpenFIGIClient
from .reconcile import reconcile

app = FastAPI(
    title="secid-recon",
    version=__version__,
    description="Security identifier validation, conversion, reconciliation and FIGI mapping.",
)

MAX_BATCH = int(os.environ.get("SECID_MAX_BATCH", "1000"))


class ValidateRequest(BaseModel):
    identifiers: list[str] = Field(..., min_length=1)


class ValidateResult(BaseModel):
    identifier: str
    valid: bool
    type: IdType | None


class ConvertRequest(BaseModel):
    identifier: str
    to: Literal["ISIN", "CUSIP", "SEDOL"]
    country: str | None = Field(None, description="ISIN country prefix for CUSIP/SEDOL to ISIN")


class Position(BaseModel):
    identifier: str
    quantity: Decimal


class ReconcileRequest(BaseModel):
    left: list[Position]
    right: list[Position]
    tolerance: Decimal = Decimal(0)
    cusip_country: str = "US"
    sedol_country: str = "GB"


class FigiRequest(BaseModel):
    identifiers: list[str] = Field(..., min_length=1, max_length=100)


def _check_batch(n: int) -> None:
    if n > MAX_BATCH:
        raise HTTPException(status_code=413, detail=f"batch exceeds {MAX_BATCH} items")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict[str, str]:
    return {"status": "ready", "version": __version__}


@app.post("/v1/validate", response_model=list[ValidateResult])
def validate(req: ValidateRequest) -> list[ValidateResult]:
    _check_batch(len(req.identifiers))
    out = []
    for raw in req.identifiers:
        kind = detect(raw)
        out.append(ValidateResult(identifier=normalize(raw), valid=kind is not None, type=kind))
    return out


@app.post("/v1/convert")
def convert(req: ConvertRequest) -> dict[str, str]:
    value = normalize(req.identifier)
    kind = detect(value)
    if kind is None:
        raise HTTPException(status_code=422, detail=f"{value} is not a valid CUSIP, ISIN or SEDOL")
    try:
        if kind.value == req.to:
            result = value
        elif req.to == "ISIN" and kind is IdType.CUSIP:
            result = cusip_to_isin(value, req.country or "US")
        elif req.to == "ISIN" and kind is IdType.SEDOL:
            result = sedol_to_isin(value, req.country or "GB")
        elif req.to == "CUSIP" and kind is IdType.ISIN:
            result = isin_to_cusip(value)
        elif req.to == "SEDOL" and kind is IdType.ISIN:
            result = isin_to_sedol(value)
        else:
            raise InvalidIdentifier(
                f"{kind.value} to {req.to} needs a reference data lookup; convert via ISIN or use /v1/figi"
            )
    except InvalidIdentifier as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"input": value, "input_type": kind.value, "to": req.to, "result": result}


@app.post("/v1/reconcile")
def reconcile_positions(req: ReconcileRequest) -> dict:
    _check_batch(len(req.left) + len(req.right))
    try:
        rows = reconcile(
            [(p.identifier, p.quantity) for p in req.left],
            [(p.identifier, p.quantity) for p in req.right],
            tolerance=req.tolerance,
            cusip_country=req.cusip_country,
            sedol_country=req.sedol_country,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    summary: dict[str, int] = {}
    for row in rows:
        summary[row.status] = summary.get(row.status, 0) + 1
    return {
        "summary": summary,
        "rows": [
            {
                "key": r.key,
                "status": r.status,
                "left_qty": r.left_qty,
                "right_qty": r.right_qty,
                "difference": r.difference,
                "left_ids": list(r.left_ids),
                "right_ids": list(r.right_ids),
            }
            for r in rows
        ],
    }


@app.post("/v1/figi")
def figi(req: FigiRequest) -> list[dict]:
    jobs = []
    for raw in req.identifiers:
        kind = detect(raw)
        if kind is None:
            raise HTTPException(status_code=422, detail=f"{normalize(raw)} is not a valid CUSIP, ISIN or SEDOL")
        jobs.append((kind, raw))
    with OpenFIGIClient() as client:
        results = client.map(jobs)
    return [
        {"id_type": r.id_type, "id_value": r.id_value, "found": r.found, "message": r.message, "matches": r.matches}
        for r in results
    ]
