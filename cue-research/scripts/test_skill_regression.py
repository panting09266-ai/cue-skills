#!/usr/bin/env python3
"""cue-research skill regression — placeholder.

Full coverage added in Task 7. This stub keeps the CI matrix happy from
the moment Task 8 wires the skill in.
"""

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE.parent


class TestSkillStructure(unittest.TestCase):
    def test_skill_md_has_required_frontmatter_keys(self):
        md = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
        self.assertIsNotNone(m, "SKILL.md missing YAML frontmatter")
        fm = m.group(1)
        for required in ("name:", "description:"):
            self.assertIn(required, fm, f"SKILL.md frontmatter missing `{required}`")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
