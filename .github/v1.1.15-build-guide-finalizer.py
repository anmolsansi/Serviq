from __future__ import annotations

import subprocess

source = subprocess.check_output(
    ["git", "show", "HEAD^:.github/v1.1.15-build-guide-finalizer.py"],
    text=True,
)
append_only_source = source.split(
    '\nci = Path(".github/workflows/ci.yml")',
    maxsplit=1,
)[0]
exec(compile(append_only_source, "v1.1.15-build-guide-append", "exec"))
