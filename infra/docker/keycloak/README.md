# Local Keycloak boundary

OPE-265 reserves Keycloak 26.7.x as Serviq's local workforce OIDC development service.

The service is development-only. It runs with `start-dev`, exposes browser traffic on loopback port `8080`, exposes the management interface on loopback port `9000`, and enables Keycloak's `/health/ready` readiness endpoint.

Before starting Compose, set `KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD` in the developer's ignored local environment. `KEYCLOAK_BOOTSTRAP_ADMIN_USERNAME` may also be overridden; otherwise the non-production username `serviq-local-admin` is used. No bootstrap password is committed to Git.

No Serviq realm, OIDC client, permanent user, role mapping, application login flow, or production identity configuration belongs in this ticket. The future application login work will consume an issuer URL only after a separate realm/client provisioning ticket defines that contract.
