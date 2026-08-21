# Serviq Release Guide

This document explains how Serviq versions are named, how a tested commit becomes a GitHub Release, and what a release does and does not mean.

GitHub Releases are the official public version history for Serviq. A release points to one exact Git tag, and that tag points to one exact commit. The release page then adds a readable title, release notes, source archives, and a permanent place for future release assets.

## Version format

Serviq uses Semantic Versioning with a leading `v`:

```text
vMAJOR.MINOR.PATCH
```

Examples:

```text
v0.1.0-alpha.1
v0.4.0-beta.1
v1.0.0-rc.1
v1.0.0
v1.1.0
v1.1.1
v2.0.0
```

Use the version components this way:

- `MAJOR` changes when an approved release introduces breaking compatibility changes.
- `MINOR` changes when backward-compatible functionality is added.
- `PATCH` changes for backward-compatible fixes.
- `alpha`, `beta`, and `rc` suffixes identify prereleases that are not the final stable version.

The release workflow enforces the supported Semantic Versioning form before any release command runs. Core numeric components cannot contain leading zeroes, and numeric prerelease identifiers cannot contain leading zeroes either. For example, `v0.2.0-alpha.1` is valid while `v0.2.0-alpha.01` is rejected. Build metadata such as `+build.7` is not accepted by the current Serviq release workflow because OPE-304 only defines the version-plus-optional-prerelease form.

A release below `v1.0.0`, or any release carrying `alpha`, `beta`, or `rc`, must not be presented as proof that the complete Serviq product is production-ready.

## Relationship between tickets, pull requests, tags, and releases

The normal Serviq delivery chain is:

```text
Linear ticket
    -> GitHub issue
    -> dedicated branch
    -> pull request
    -> CI and review
    -> merge to main
    -> one or more merged changes form a release
    -> semantic-version tag
    -> GitHub Release
```

A ticket represents one unit of work. A pull request represents one reviewed code change. A release represents a tested product snapshot that can contain many tickets and pull requests.

## Release-impact labels

Each pull request declares one release-impact label:

- `release:major` — approved breaking compatibility change.
- `release:minor` — backward-compatible functionality.
- `release:patch` — backward-compatible fix.
- `release:skip` — do not include the PR in generated release notes.

The repository also uses type labels such as `feature`, `fix`, `security`, `infrastructure`, `testing`, `dependencies`, `refactor`, `performance`, and the existing `documentation`, `enhancement`, and `bug` labels.

`.github/release.yml` maps these labels into readable sections in GitHub-generated release notes. Pull requests that do not match a specific category still appear in the catch-all `Other Changes` section unless they have `release:skip`.

Every supported release path runs the same idempotent release-label bootstrap before publishing. If one of the release labels is missing, the workflow restores it with the repository-scoped `GITHUB_TOKEN` without deleting or replacing GitHub's existing default labels.

## Release workflow

The permanent workflow is `.github/workflows/release.yml`.

Before publishing a release, it runs the same baseline quality expectations used by contributors:

```text
make setup
make lint
make typecheck
make test
docker compose -f infra/docker/compose.yml --profile "*" config --no-interpolate
```

The workflow deliberately does not call `make security`, `make e2e`, or `make load-test` while those targets are still intentional non-zero placeholders. Later tickets should add those gates to release publishing after the real implementations exist.

The workflow does not need a personal access token or a paid service. It uses GitHub's repository-scoped `GITHUB_TOKEN` with explicit permissions for the jobs that publish releases and ensure release labels exist.

## Creating a release from the GitHub UI

The recommended operator path is the manual workflow because it validates the current `main` commit before creating the tag and release.

1. Open the repository's **Actions** tab.
2. Select the **Release** workflow.
3. Select **Run workflow** and run it from `main`.
4. Enter a semantic version such as `v0.2.0-alpha.1`.
5. Optionally provide a custom title. If left empty, the title becomes `Serviq <version>`.
6. Set **prerelease** to `true` only when the version has an explicit prerelease suffix such as `-alpha.1`, `-beta.1`, or `-rc.1`.
7. Run the workflow.

The workflow rejects invalid version strings, an existing tag, or an existing release. It validates the checked-out `main` commit, creates the release tag at that exact tested commit, and asks GitHub to generate the merged-PR changelog.

## Creating a release from an existing tag

An externally created tag can also trigger the workflow.

The tag must use the approved semantic-version format and its commit must already be contained in `main`. The workflow refuses to publish a tag from an unmerged feature branch.

For example, a trusted maintainer could create and push:

```bash
git checkout main
git pull --ff-only
git tag v0.3.0-beta.1
git push origin v0.3.0-beta.1
```

The tag-triggered release job then validates that exact commit before creating the GitHub Release. A prerelease suffix causes the GitHub Release to be marked as a prerelease.

For normal Serviq operation, prefer the manual GitHub Actions path because it creates the tag only after the validation run succeeds.

## First release bootstrap

OPE-304 introduces the release system when the repository has no existing tags or releases. The workflow therefore contains a one-time idempotent bootstrap for:

```text
v0.1.0-alpha.1
Serviq v0.1.0-alpha.1 — Platform Foundation
```

The bootstrap runs only from the merged `main` release-system files. It runs the quality gates, creates the release labels, verifies the release/tag do not already exist, and publishes the first release as a prerelease.

On later updates to the release-system files, the bootstrap detects that `v0.1.0-alpha.1` already exists and exits without changing it.

## Release notes

Every release should have a short human-readable introduction explaining the meaningful product state. GitHub-generated notes then provide the traceable list of merged pull requests and contributors.

A good release introduction answers:

- What can a customer, operator, or developer do now that they could not do before?
- Is this alpha, beta, release-candidate, or stable software?
- Are there breaking changes or migrations?
- What important limitations remain?

Do not use release notes to claim unsupported scale, security certification, production readiness, or completed features that have not been validated.

## Published versions are immutable by policy

Even before repository-level immutable-release protection is enabled, Serviq treats a published tag/release as permanent history.

Never move an existing published tag to another commit. Never replace a broken published version with different code under the same version number. If a problem is found, fix it through the normal ticket/PR/CI process and publish a new version such as:

```text
v0.3.0-beta.1 -> v0.3.0-beta.2
v1.2.0 -> v1.2.1
```

Repository-level immutable releases can be enabled later after the release automation has been exercised enough that draft/assets/signing behavior is fully defined.

## What a GitHub Release does not do yet

Publishing a Serviq GitHub Release currently does not automatically:

- deploy a production environment;
- publish Docker images to GHCR;
- generate an SBOM;
- sign source or container artifacts;
- create provenance/attestations;
- run the future security, E2E, or load-test gates;
- create release branches or backports.

Those capabilities should be added only through dedicated reviewed tickets rather than being hidden inside the release workflow.

## Future stable-release gate

`v1.0.0` must not be created merely because enough time has passed or enough tickets have closed. It should represent an explicitly reviewed production-readiness milestone that includes the required product workflows, security controls, observability, migration/backup procedures, tests, deployment/recovery procedures, and measured performance evidence.

Until then, Serviq should continue using honest pre-1.0 and prerelease versions.

## Post-release verification

After each release, verify:

1. The release is visible on the repository's Releases page.
2. The displayed tag matches the requested version exactly.
3. The tag commit is the validated `main` commit from the release workflow.
4. Prerelease/stable status is correct.
5. Generated release notes contain the expected pull requests.
6. No secret, credential, customer data, or unintended binary asset is attached.
7. The workflow run completed successfully.

The release is considered complete only after these checks pass.
