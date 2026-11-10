# Project instructions

## Purpose and approved foundation

Institutional PDF/OCR processing with metadata proposals, durable job history and
least privilege. Approved stack: Python/FastAPI, PostgreSQL, RabbitMQ/Celery and
Docker Compose with Linux services. Docker installation, container definitions and
full runtime integration are explicitly deferred to a FINAL feature by the user.
F002 covers a local backend and verified TLS, not a Linux deployment. The user
reports storage locations are encrypted; final deployment verification is pending.
Keep a modular application with separate API and worker processes. Do not build
independent microservices by default.

## Work and Git

- Work by features recorded in `docs/features/`. State scope, exclusions, files,
  risks, acceptance checks, actual results and pending decisions.
- New branches MUST use `feature/<name>` from `develop` until the user changes this
  rule. Keep existing branches. This overrides the default `codex/` prefix.
- Local commits and merges of verified features into `develop` are authorized.
  Do not merge a feature whose required checks remain unverified.
- Publishing code, tags, releases, images, remote Git operations and destructive
  data/volume operations require express authorization.
- Consult new architecture, security, authentication, database, infrastructure or
  scope decisions. Do not request approval again for decisions already approved.

## Code boundaries and checks

- Keep HTTP, use cases and adapters separate. No business logic in controllers.
- Use typing, explicit errors and centralized validated settings. Avoid unnecessary
  abstractions and empty folders. Public interfaces and complex logic need docs.
- Run checks appropriate to the feature. Use synthetic fixtures, never real
  institutional documents or paid services in tests. Report skipped checks honestly.
- Keep requirements, ADRs, operation guides and feature evidence synchronized.

## Security and document semantics

- All application network connections require verified TLS, including Docker
  internal links. Do not disable certificate or hostname verification.
- Keep keys, secrets and runtime data outside Git and image build contexts.
  Operational passwords and future application secrets belong in the ignored
  root `.env`, as explicitly requested by the user. Keep TLS private keys as
  protected files referenced by path; never embed real values in `.env.example`.
  Never log secrets, extracted text, prompts containing documents or raw errors
  that may expose connection strings.
- Disk/volume/backup encryption is required before real sensitive data; TLS and
  filesystem permissions do not prove encryption at rest.
- Enforce permissions in the backend, by action and authorized resource scope.
  The application's superuser is not a database/host administrator.
  Local user accounts are approved; the detailed F003 schema/session design is
  proposed in its feature document and requires approval before implementation.
- Files physically move from input/processing to success/failed, using a recoverable
  design that preserves content and history. Movement is not implemented in F002.
- `success` means metadata processing completed, without routine human approval.
- Duplicate ingestion codes are logged and skipped. An authorized retry is another
  attempt for the same document.
- Removing a failed item removes it from requeue eligibility, not the PDF or audit.
  Preserve actor, time and reason. Failures can leave partial technical artifacts;
  never publish them as valid completed metadata.

## References

- `docs/requirements.md`: accepted requirements and future features.
- `docs/open-questions.md`: unresolved decisions.
- `docs/decisions/`: approved and proposed ADRs, clearly distinguished.
- `docs/features/`: scope and evidence for each delivery.
- `docs/development.md`: local execution and verification when available.
