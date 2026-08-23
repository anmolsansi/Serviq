from __future__ import annotations

import subprocess
from pathlib import Path

SOURCE_COMMIT = "1939d7b7054881ad432af5fa822355f16dffc533"
SOURCE_PATH = ".github/v1.1.15-build-guide-finalizer.py"

subprocess.run(
    ["git", "fetch", "--depth=1", "origin", SOURCE_COMMIT],
    check=True,
)
source = subprocess.check_output(
    ["git", "show", f"{SOURCE_COMMIT}:{SOURCE_PATH}"],
    text=True,
)
append_only_source = source.split(
    '\nci = Path(".github/workflows/ci.yml")',
    maxsplit=1,
)[0]
exec(compile(append_only_source, "v1.1.15-build-guide-append", "exec"))

guide = Path("docs/SERVIQ_BUILD_GUIDE.md")
text = guide.read_text(encoding="utf-8")
text = text.replace(
    "/opt/keycloak/data/import/serviq-test-realm.json:ro",
    "/opt/keycloak/data/import/serviq-realm.json:ro",
)
guide.write_text(text, encoding="utf-8")
