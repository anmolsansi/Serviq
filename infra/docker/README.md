# Serviq local infrastructure

Run Docker Compose from `infra/docker`.

PostgreSQL uses the Compose hostname `postgres` and container port `5432`.

Valkey uses the Compose hostname `valkey` and container port `6379`. It is local development infrastructure and is rebuildable rather than authoritative business storage.

The S3-compatible object-storage service uses the Compose hostname `object-storage` and S3 port `8333`. Host access is loopback-only at `127.0.0.1:8333`. The required local bucket name is `serviq-local-objects`.

Local overrides use `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, and `S3_BUCKET`. These are development-only values and must never be reused as staging or production credentials.
