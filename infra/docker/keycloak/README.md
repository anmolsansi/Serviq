# Local Keycloak boundary

OPE-265 reserves Keycloak 26.7.x as Serviq's local workforce OIDC development service.

The service is development-only. It must use `start-dev`, expose only loopback host ports, enable Keycloak health endpoints, and receive bootstrap-admin values through environment substitution. No Serviq realm, OIDC client, user, role mapping, or production identity configuration belongs in this ticket.

The future application login work will consume an issuer URL only after a separate realm/client provisioning ticket defines that contract.
