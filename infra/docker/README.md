# Serviq local infrastructure

Run Docker Compose from `infra/docker`.

PostgreSQL uses the Compose hostname `postgres` and container port `5432`.

Valkey uses the Compose hostname `valkey` and container port `6379`. It is local development infrastructure and is rebuildable rather than authoritative business storage.
