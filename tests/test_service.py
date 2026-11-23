import json

import httpx
import respx
from fastapi.testclient import TestClient

from secid.openfigi import MAPPING_URL, OpenFIGIClient
from secid.service import app

client = TestClient(app)


def test_probes():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_validate():
    resp = client.post("/v1/validate", json={"identifiers": ["US0378331005", "037833100", "nope"]})
    assert resp.status_code == 200
    assert [r["type"] for r in resp.json()] == ["ISIN", "CUSIP", None]


def test_convert():
    resp = client.post("/v1/convert", json={"identifier": "037833100", "to": "ISIN"})
    assert resp.json()["result"] == "US0378331005"
    resp = client.post("/v1/convert", json={"identifier": "037833100", "to": "SEDOL"})
    assert resp.status_code == 422


def test_reconcile_endpoint():
    resp = client.post(
        "/v1/reconcile",
        json={
            "left": [{"identifier": "037833100", "quantity": "100"}],
            "right": [{"identifier": "US0378331005", "quantity": "95"}],
        },
    )
    body = resp.json()
    assert body["summary"] == {"quantity_break": 1}
    assert body["rows"][0]["difference"] == "5"


@respx.mock
def test_figi_endpoint(monkeypatch):
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    route = respx.post(MAPPING_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"data": [{"figi": "BBG000B9XRY4", "ticker": "AAPL", "exchCode": "US"}]},
                {"warning": "No identifier found."},
            ],
        )
    )
    resp = client.post("/v1/figi", json={"identifiers": ["US0378331005", "GB0002634946"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["found"] and body[0]["matches"][0]["figi"] == "BBG000B9XRY4"
    assert not body[1]["found"] and body[1]["message"] == "No identifier found."
    sent = route.calls[0].request
    assert b'"idType":"ID_ISIN"' in sent.content.replace(b" ", b"")
    assert "X-OPENFIGI-APIKEY" not in sent.headers


@respx.mock
def test_client_batches_with_key():
    route = respx.post(MAPPING_URL).mock(
        side_effect=lambda req: httpx.Response(200, json=[{"warning": "x"}] * len(json.loads(req.content)))
    )
    with OpenFIGIClient(api_key="test-key") as c:
        results = c.map([("TICKER", f"T{i}") for i in range(150)])
    assert len(results) == 150
    assert route.call_count == 2
    assert route.calls[0].request.headers["X-OPENFIGI-APIKEY"] == "test-key"
