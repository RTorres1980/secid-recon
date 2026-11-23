# secid-recon

[![CI](https://github.com/RTorres1980/secid-recon/actions/workflows/ci.yml/badge.svg)](https://github.com/RTorres1980/secid-recon/actions/workflows/ci.yml)

Validate, convert and reconcile **CUSIP**, **ISIN** and **SEDOL** security identifiers, map them to Bloomberg **FIGI**s through the free [OpenFIGI](https://www.openfigi.com/api) API, and run it all as a small, hardened API on **Kubernetes**.

## Why

Position files rarely agree on how to key a security. A custodian sends CUSIPs, a fund administrator sends ISINs and a UK broker sends SEDOLs, so a reconciliation that joins on the raw identifier reports false breaks. `secid-recon` validates every identifier's check digit, resolves each one to a common ISIN key offline, and only then compares quantities.

## Library

```bash
pip install "git+https://github.com/RTorres1980/secid-recon"
```

```python
from secid import detect, cusip_to_isin, isin_to_sedol, reconcile

detect("037833100")            # IdType.CUSIP
cusip_to_isin("037833100")     # 'US0378331005'
isin_to_sedol("GB0002634946")  # '0263494'

custodian = [("037833100", 100), ("0263494", 50)]         # CUSIP, SEDOL
administrator = [("US0378331005", 98), ("GB0002634946", 50)]  # ISINs

for row in reconcile(custodian, administrator):
    print(row.key, row.status, row.difference)
# US0378331005 quantity_break 2
# GB0002634946 matched 0
```

Statuses are `matched`, `quantity_break`, `missing_left`, `missing_right` and `invalid_identifier`. Duplicate rows for the same security are summed even when they use different identifier types, quantities are `Decimal`, and a `tolerance` can absorb rounding.

| Conversion | Supported offline | Why |
| --- | --- | --- |
| CUSIP → ISIN | US, CA | These ISINs embed the CUSIP |
| SEDOL → ISIN | GB, IE | These ISINs embed `00` + SEDOL |
| ISIN → CUSIP / SEDOL | Same markets | Extracted from the ISIN |
| CUSIP ↔ SEDOL, any → FIGI | Via OpenFIGI | Needs reference data |

### FIGI mapping

```python
from secid.openfigi import OpenFIGIClient
from secid import IdType

with OpenFIGIClient() as client:  # reads OPENFIGI_API_KEY if set
    for r in client.map([(IdType.ISIN, "US0378331005"), ("TICKER", "IBM")]):
        print(r.id_value, r.found, r.matches[:1])
```

The client batches jobs to OpenFIGI's per-request limit (10 without a key, 100 with one) and retries once on HTTP 429 using `Retry-After`.

## API

```bash
pip install -e ".[service]"
uvicorn secid.service:app --port 8080
```

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/v1/validate` | Validate and type a batch of identifiers |
| POST | `/v1/convert` | Convert between CUSIP, ISIN and SEDOL |
| POST | `/v1/reconcile` | Reconcile two position lists |
| POST | `/v1/figi` | Map identifiers to FIGIs (OpenFIGI) |
| GET | `/healthz`, `/readyz` | Kubernetes probes |

Interactive docs are served at `/docs`.

## Kubernetes

Manifests live in `k8s/` and are built with Kustomize:

- `base/`: namespace with the `restricted` Pod Security Standard, a 2-replica Deployment (non-root, read-only root filesystem, all capabilities dropped, seccomp `RuntimeDefault`), Service, HorizontalPodAutoscaler, PodDisruptionBudget and a NetworkPolicy that allows only the service port in and DNS/HTTPS out.
- `overlays/local/`: one replica using a locally built image, for kind or minikube.

```bash
docker build -t secid-recon:dev .
kind create cluster --name secid
kind load docker-image secid-recon:dev --name secid
kubectl apply -k k8s/overlays/local
kubectl -n secid-recon port-forward svc/secid-recon 8080:80
```

An OpenFIGI API key is optional. To use one:

```bash
kubectl -n secid-recon create secret generic secid-recon-openfigi --from-literal=api-key=<your key>
```

CI runs the tests on Python 3.10 to 3.13, validates the rendered manifests with kubeconform, then builds the image, deploys it to a kind cluster and smoke-tests the live API.

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
```

## License

MIT
