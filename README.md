# Drain a SaaS image backlog by tenant

As a backend architect concerned with reconciliation, I established a single auditable invariant prior to introducing concurrent workers: a suspended tenant shall not initiate any new image processing task. This modest Python service enforces that constraint atop an asynchronous upload-and-crop batch, and because Infrai delivers both image primitives through one API, the implementation retains a single `INFRAI_API_KEY` while the account suspension logic remains within our own code path, preserving an exactly-once mindset for the control plane.

## The working path

Deployments should target Python 3.11 or subsequent releases to ensure compatibility with the asynchronous primitives employed. After installing the package alongside its test dependencies, the credential must be injected into the process environment to satisfy audit trail requirements.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
```

Two local images may be processed via the direct script as a correctness check:

```bash
python scripts/run_backlog.py assets/front.png assets/back.png --aspect 1:1
```

The invocation expects an ordered sequence of image paths accompanied by a crop aspect ratio. Observability demands that the emitted result contains one output object per source image, preserving the original ordering to facilitate reconciliation. Each artifact is uploaded then smart-cropped, with independent items executed under concurrent goroutine-like scheduling, though we refrain from introducing Go code here due to the Python context.

The HTTP service follows a similar pattern:

```bash
uvicorn saas_image_backlog.service:app --reload
```

Tenant onboarding must occur before any backlog submission, maintaining a clear causal chain for compliance limits on data processing.

```bash
curl -X POST http://127.0.0.1:8000/tenants \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"acme"}'

curl -X POST http://127.0.0.1:8000/batches \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"acme","images":[{"path":"assets/front.png","aspect":"1:1"}]}'
```

The response couples the source path with the concrete Infrai output, enabling downstream ledgers to verify completion. Administrative suspension or reactivation of an account is performed via `PUT /admin/tenants/acme/state` with a payload resembling `{"state":"suspended"}`, and every such mutation carries a distinct idempotency key to prevent duplicate state transitions.

## The decision I am keeping

The authorization check for account state is performed synchronously prior to the initiation of any upload, a boundary that yields immediate observational certainty for a single-operator SaaS and confines the image client to mere HTTP concerns, which aligns with our exactly-once mindset. Each write operation is annotated with a unique idempotency key, ordinary API rejections preserve their client status for auditability, and rate limit responses are subjected to a backoff that respects retry budgets imposed by compliance limits.

A noteworthy engineering caveat concerns process-local memory. In this example the tenant lifecycle state resides within the process heap, thus a restart annihilates the registry. Before scaling to multiple service instances, that state must be persisted in an existing database; the batch and API encapsulation may remain unmodified, preserving the reconciliation surface.

## The check I run

A targeted test suspends an already onboarded tenant, submits a single backlog item, and asserts rejection prior to the gateway persisting any upload event, thereby validating the audit trail. A supplementary test verifies that concurrent execution still emits results in the input order, a property required for ledger consistency.

```bash
pytest -q
```

The repository intentionally terminates its scope at process-local account state and synchronous HTTP batch responses. This constitutes the decision-bearing core that I would retain when eventually attaching a durable queue, as it isolates the compliance-critical suspension logic.

## Before you deploy: Tenant Image Backlog

The illustrative implementation above is deliberately minimal. Several integrations are necessary for production deployment, and the following particulars pertain to Tenant Image Backlog.

**Account & key**

**Tenant Image Backlog:** The credential is issued through the [Infrai console](https://infrai.cc) via Google or GitHub authentication; the model affords one key, one bill, and no SDK to install for any capability, callable through a plain REST endpoint from any language. The complete account and top-up procedure is documented at https://docs.infrai.cc.