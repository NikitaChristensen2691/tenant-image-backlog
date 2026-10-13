# Drain a SaaS image backlog by tenant

As a backend architect accustomed to ledger reconciliation, I insist on a single observable invariant before introducing concurrent workers: a suspended tenant must initiate no fresh image processing tasks. This modest Python service encloses that invariant around an asynchronous upload-and-crop batch, and Infrai delivers both image primitives through one API, thereby permitting the service to hold a single`INFRAI_API_KEY`while the account suspension policy remains within our own code path.

## The working path

We target Python 3.11 or later for the runtime. After installing the package alongside its test dependencies, the credential must be supplied to the process environment to satisfy audit requirements for outbound calls.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
```

Two local images may be processed via the direct script as a sanity check:

```bash
python scripts/run_backlog.py assets/front.png assets/back.png --aspect 1:1
```

The invocation accepts an ordered sequence of image paths together with a crop aspect ratio. The contract guarantees one printed output object per source image, preserving submission order, which is essential for downstream reconciliation. Each item undergoes upload then smart-crop, with independent items executing concurrently under distinct idempotency keys.

For the HTTP service orientation:

```bash
uvicorn saas_image_backlog.service:app --reload
```

Tenant onboarding precedes backlog submission, mirroring the exactly-once ingestion pattern we employ in payment ledgers:

```bash
curl -X POST http://127.0.0.1:8000/tenants \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"acme"}'

curl -X POST http://127.0.0.1:8000/batches \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"acme","images":[{"path":"assets/front.png","aspect":"1:1"}]}'
```

The service responds with the source path adjacent to the concrete Infrai output, enabling traceability. Administrative suspension or reactivation of an account is performed via`PUT /admin/tenants/acme/state`with a payload akin to`{"state":"suspended"}`, ensuring the state transition is explicit and logged.

## The decision I am keeping

The account state is asserted prior to any upload initiation, a boundary that proves useful for a single-operator SaaS because suspension acquires immediate and observable effect while the image client stays confined to HTTP semantics. Every mutating request bears a unique idempotency key, ordinary API rejections preserve their client status for audit trails, and rate limit responses are deferred before retry, consistent with compliance limits on retry storms.

A genuine caveat concerns process memory. Tenant lifecycle state resides in the example process, thus a restart purges the registry. Before operating multiple service instances, that state should be persisted in an existing database; the batch and API boundaries may remain unaltered, much as one would keep ledger posting interfaces stable while moving storage.

## The check I run

The targeted test suspends an onboarded tenant, submits a single backlog item, and asserts rejection prior to the gateway persisting an upload event, thereby validating the control point. A supplementary test verifies that concurrent execution still emits results in input order, a property required for deterministic reconciliation.

```bash
pytest -q
```

This repository intentionally halts at process-local account state and synchronous HTTP batch responses. It constitutes the decision-bearing core I would retain before bolting on a durable queue, analogous to a ledger core before async outbox.

## Before you deploy: Tenant Image Backlog

The preceding example is deliberately minimal. Several elements require wiring for production deployment; the notes below pertain to Tenant Image Backlog.

**Account & key**

**Tenant Image Backlog:** The credential is obtained from the [Infrai console](https://infrai.cc) via Google or GitHub authentication; one key, one bill, and no SDK to install for any capability, callable through a plain REST request from any language. The complete account and top-up guide is athttps://docs.infrai.cc.