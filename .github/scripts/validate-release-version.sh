#!/usr/bin/env bash
set -euo pipefail

version="${1:-}"

if [[ ! "$version" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$ ]]; then
  echo "Version must be vMAJOR.MINOR.PATCH with an optional prerelease suffix, for example v0.2.0-alpha.1 or v1.0.0." >&2
  exit 1
fi

if [[ "$version" == *-* ]]; then
  prerelease="${version#*-}"
  IFS='.' read -r -a identifiers <<< "$prerelease"

  for identifier in "${identifiers[@]}"; do
    if [[ "$identifier" =~ ^0[0-9]+$ ]]; then
      echo "Numeric prerelease identifiers must not contain leading zeroes: $identifier" >&2
      exit 1
    fi
  done
fi
