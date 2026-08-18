# OPE-299 — Runtime validation evidence

## Scope

This record captures the exact-head validation for the OPE-299 tenant-scoped model-configuration CRUD implementation before the runtime stage was merged.

Validated implementation head:

```text
0fc1bfd0922175193e3857afb6a16cb6ea0e91ed
```

Runtime merge commit:

```text
723709276ce3ac52e1129084f29d008c48ceb57f
```

Runtime review:

```text
PR #145 — OPE-299: implement tenant-scoped model configuration CRUD
```

## CI evidence

GitHub Actions CI run #236 completed successfully on the exact implementation head.

The run verified:

- repository setup from frozen dependency definitions;
- Ruff linting;
- strict Python type checking;
- repository unit tests;
- Docker Compose configuration validation;
- clean PostgreSQL migration upgrade to head;
- real PostgreSQL integration tests;
- downgrade to the previous invitation-era revision;
- re-upgrade to migration head;
- full migration-chain downgrade to base.

The database integration suite specifically exercised OPE-299 create/list/update/delete behavior, tenant isolation, alias validation, active-provider eligibility, permission denial, and blocking-reference deletion protection.

## Security evidence

GitHub Actions Security run #212 completed successfully on the exact implementation head.

The run verified:

- Gitleaks repository/history secret scanning;
- Trivy filesystem and configuration scanning;
- CodeQL analysis for Python;
- CodeQL analysis for JavaScript/TypeScript;
- Node dependency vulnerability audit;
- API Python dependency vulnerability audit;
- worker Python dependency vulnerability audit;
- LLM Gateway Python dependency vulnerability audit.

## Database safety verified

The OPE-299 migration adds `model_configuration_references` and a composite tenant/model relationship used to make deletion protection tenant-safe.

The successful migration cycle proves the new schema can be installed on a clean integration database, rolled back through the existing chain, and installed again without manual repair.

## Acceptance behavior verified

The integration suite covers the ticket's required behavior, including:

- valid generation alias creation;
- valid embedding alias creation;
- valid rerank alias creation;
- duplicate same-tenant alias conflict;
- identical aliases in different tenants;
- trimmed alias/upstream-model validation;
- invalid purpose rejection;
- unknown field rejection;
- foreign provider non-disclosure;
- inactive provider rejection;
- tenant-scoped listing;
- authorized updates of frozen mutable fields;
- rejection of alias/purpose mutation;
- unauthorized model-management operations;
- referenced-delete conflict;
- unreferenced-delete success;
- credential-free model responses.

## Result

The runtime stage was merged only after CI #236 and Security #212 both passed on the same exact head. The cumulative documentation stage is performed separately so the large existing `docs/SERVIQ_BUILD_GUIDE.md` can be appended without truncating earlier ticket history.
