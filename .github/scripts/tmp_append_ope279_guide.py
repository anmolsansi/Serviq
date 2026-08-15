from pathlib import Path


guide = Path("docs/SERVIQ_BUILD_GUIDE.md")
marker = "# OPE-279 — trusted RequestContext"
section = """

---

# OPE-279 — trusted RequestContext

OPE-279 implements Architecture Contract C-1 as real backend code. Before this ticket, `services/api/app/core/auth.py` was only a reserved placeholder. Serviq had an architecture description of trusted identity and tenant context, but there was no canonical Python object that later services could safely accept.

The ticket adds strict actor categories (`tenant_user`, `customer`, `service`, `platform_operator`) and strict assurance levels (`anonymous`, `verified`, `workforce`, `platform`). Unknown values are rejected during validation instead of being treated as approximately correct.

The new `RequestContext` keeps the exact meaning of Contract C-1: request ID, tenant UUID, actor, optional internal user/customer IDs, permissions, and assurance level. Python code uses snake_case names while Pydantic aliases preserve the frozen camelCase contract names when serialized.

The context is frozen after construction. The nested actor is frozen too, and the in-process permission collection is immutable. This prevents later code from changing trusted tenant or identity information after authentication/authorization resolution has already occurred.

A small `has_permission()` helper provides capability lookup without creating route guards in this ticket. A separate `require_tenant_id()` helper fails closed with a typed `MissingTenantContextError` when trusted context is unavailable. It never falls back to a default tenant, request body, or arbitrary tenant header.

OPE-279 also introduces the minimum internal typed authorization-context error hierarchy needed by that fail-closed helper. It deliberately does not add global HTTP exception handling. HTTP mapping remains a later concern.

Focused unit tests cover valid workforce, verified-customer, and anonymous-customer contexts, exact Contract C-1 serialization, invalid actor/assurance values, missing trusted tenant context, and immutability.

This ticket does **not** validate OIDC tokens, create sessions, query memberships, add route guards, or read tenant IDs from client input. Its purpose is narrower: provide one safe shape that later trusted auth and tenancy code can populate.

The detailed file-by-file explanation for this ticket is also recorded in `docs/OPE_279_285_IMPLEMENTATION_GUIDE.md`.
"""

text = guide.read_text()
if marker not in text:
    guide.write_text(text + section)
