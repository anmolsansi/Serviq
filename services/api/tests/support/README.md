# API tenant-isolation test support

`tenant_isolation.py` is the reusable real-PostgreSQL test foundation for any Serviq domain that stores tenant-owned data.

## Why it exists

A tenant-isolation test is weak if tenant A and tenant B accidentally use globally unique human-facing values. A repository might omit a tenant predicate and the test could still pass because the fixture happened to use different names, emails, or role labels.

`TenantIsolationFixture` creates two tenants whose organization display names, workforce display names, workforce emails, and role display names deliberately overlap. The UUIDs and tenant ownership are the only reliable separator.

## Basic usage

```python
fixture = TenantIsolationFixture.new()
async with session.begin():
    await seed_tenant_isolation_fixture(session, fixture)

# Use fixture.owner_a as the authenticated tenant-A administrator.
# Attack the domain with fixture.<foreign tenant-B UUID> directly.
# Never obtain the foreign UUID through the UI flow being tested.

assert_list_excludes_foreign(
    items,
    foreign_id=fixture.member_membership_b,
    id_of=lambda item: item.id,
)
assert_foreign_resource_hidden(response.status_code)
assert_value_unchanged(before=before_value, after=after_value)

async with session.begin():
    await cleanup_tenant_isolation_fixture(session, fixture)
```

## Extending it for a future domain

Keep the core fixture small. A future ticket should create its domain resource explicitly under both `fixture.tenant_a` and `fixture.tenant_b`, preferably with the same visible name/value. Then use the known tenant-B UUID to attack tenant-A list/get/update/delete paths.

Do not modify production authorization merely to make the harness easier to use. Do not mock the repository or tenant filter that the test is supposed to prove. For database-backed domain repositories, use the real PostgreSQL integration environment.

## What a passing isolation test should prove

A useful test proves all three facts when applicable:

1. tenant A's list does not contain the known tenant-B resource;
2. tenant A cannot fetch or mutate the known tenant-B UUID;
3. the tenant-B row is unchanged after the rejected mutation.

For privileged paths, run the attack as tenant A's Owner/Admin, not only as an ordinary member. High privilege inside one tenant must never imply access to another tenant.