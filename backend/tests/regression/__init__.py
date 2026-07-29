"""Regression tests for defects found during the Phase 0–8 verification pass.

Every test here reproduces a confirmed bug in production code and is marked
`xfail(strict=True)`. Strict matters: the moment the bug is fixed the test turns
from XFAIL into XPASS, which pytest reports as a **failure**, forcing whoever
fixed it to drop the marker. That is what stops these from rotting into a list
of permanently-red tests everyone learns to ignore.

Each docstring states the defect, the root cause, and the smallest production
change that would fix it. Nothing here has been fixed in production code —
per the brief, the fixes await sign-off. See TEST_REPORT.md for severities.
"""
