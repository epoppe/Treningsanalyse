"""Guardrail: domenekode skal ikke bruke asyncio.run()."""

from __future__ import annotations

import unittest
from pathlib import Path


DOMAIN_ROOTS = (
    Path(__file__).resolve().parents[1] / "app" / "services",
    Path(__file__).resolve().parents[1] / "app" / "routers",
)


class NoAsyncioRunInDomainTests(unittest.TestCase):
    def test_no_asyncio_run_calls(self):
        violations = []
        for root in DOMAIN_ROOTS:
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                for i, line in enumerate(text.splitlines(), start=1):
                    stripped = line.lstrip()
                    if stripped.startswith("#"):
                        continue
                    if "asyncio.run(" in line:
                        rel = path.relative_to(root.parents[1])
                        violations.append(f"{rel}:{i}: {stripped}")
        self.assertEqual(
            violations,
            [],
            msg="asyncio.run() funnet i domenekode:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
