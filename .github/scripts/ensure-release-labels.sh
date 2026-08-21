#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"

gh label create "release:major" --color B60205 --description "Breaking change requiring a major version" --force
gh label create "release:minor" --color 0E8A16 --description "Backward-compatible feature for a minor version" --force
gh label create "release:patch" --color 1D76DB --description "Backward-compatible fix for a patch version" --force
gh label create "release:skip" --color C5DEF5 --description "Exclude this pull request from generated release notes" --force
gh label create "breaking-change" --color D93F0B --description "Introduces a breaking compatibility change" --force
gh label create "feature" --color 0E8A16 --description "Adds user-visible or platform functionality" --force
gh label create "fix" --color D4C5F9 --description "Corrects faulty behavior" --force
gh label create "security" --color B60205 --description "Security hardening or vulnerability remediation" --force
gh label create "infrastructure" --color 5319E7 --description "Infrastructure, deployment, or operations change" --force
gh label create "testing" --color FBCA04 --description "Testing or quality-system change" --force
gh label create "dependencies" --color 0366D6 --description "Dependency update or dependency-management change" --force
gh label create "refactor" --color C2E0C6 --description "Internal restructuring without intended behavior change" --force
gh label create "performance" --color F9D0C4 --description "Performance or efficiency improvement" --force
