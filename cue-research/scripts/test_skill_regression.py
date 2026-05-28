#!/usr/bin/env python3
"""cue-research skill regression — stdlib unittest.

Checks the skill's structural contract:
  - SKILL.md frontmatter shape (CI also enforces this globally).
  - SKILL.md declares every verb its decision-tree references.
  - Shared cue-buddy scripts (cue_api, sse_report) are importable from
    cue-research/scripts/ via the documented sys.path pattern.
  - The functions cue-research depends on actually exist in cue_api +
    sse_report (catches accidental rename/drift).
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SKILL_DIR = _HERE.parent
_REPO_ROOT = _SKILL_DIR.parent
_BUDDY_SCRIPTS = _REPO_ROOT / "buddy" / "scripts"

# This sys.path pattern is the one SKILL.md tells the agent/scripts to use.
sys.path.insert(0, str(_BUDDY_SCRIPTS))


class TestSkillMd(unittest.TestCase):
    def setUp(self):
        self.md = (_SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_frontmatter_has_required_keys(self):
        m = re.match(r"^---\n(.*?)\n---\n", self.md, re.S)
        self.assertIsNotNone(m, "missing frontmatter")
        fm = m.group(1)
        for required in ("name:", "description:"):
            self.assertIn(required, fm)

    def test_every_declared_verb_appears_in_decision_tree(self):
        # Verbs declared in the verb table (e.g. backtick `+ask` etc.)
        verbs = set(re.findall(r"`\+([a-z]+)`", self.md))
        self.assertIn("ask", verbs)
        self.assertIn("match", verbs)
        self.assertIn("rewrite", verbs)
        self.assertIn("save", verbs)

    def test_freeform_path_mentions_rewrite_endpoint(self):
        # Codex Block C fix: free-form path must call /api/rewrite first
        # AND disable backend need_analysis. Accept any of: kwarg form
        # `need_analysis=False`, dict form `"need_analysis": False`, or
        # JSON form `'need_analysis': false` — what matters is the intent,
        # not the syntax.
        self.assertIn("/api/rewrite", self.md)
        self.assertRegex(
            self.md,
            r'["\']?need_analysis["\']?\s*[=:]\s*["\']?\s*[Ff]alse\b',
            "SKILL.md must show need_analysis being set to False (any syntax)",
        )

    def test_never_autoselects_buddy_hard_rule(self):
        # Codex Block B fix: matching is low-confidence, never auto-pick.
        self.assertRegex(self.md, r"不自动选搭子|never auto-?select")

    def test_no_delete_verb_in_verb_table(self):
        # Hard rule 5: skill must not DECLARE +delete in the verb table.
        # Scoped to verb-table row form `| `+delete`` so the hard-rule prose
        # ("**不实现 `+delete`**") explaining WHY we don't have it is allowed.
        self.assertNotRegex(
            self.md, r"\|\s*`\+delete`",
            "SKILL.md verb table must not declare +delete — deletion is web-only",
        )

    def test_credit_confirmation_hard_rule_present(self):
        # Hard rule 2: every real run must explicitly confirm credits.
        self.assertRegex(
            self.md, r"确认\s*credits|confirm credits",
            "SKILL.md hard rules must mention credit confirmation",
        )

    def test_no_client_side_rewrite_reimpl_rule_present(self):
        # Hard rule 4: don't reimplement backend rewrite logic in the agent.
        # Look for either a Chinese phrasing or an English one.
        self.assertRegex(
            self.md,
            r"不在 agent 侧重写|不重写深研逻辑|don'?t (?:re-?implement|reimplement) (?:the )?rewrite",
            "SKILL.md must forbid client-side rewrite reimplementation",
        )


class TestSharedScriptImports(unittest.TestCase):
    def test_cue_api_search_templates_exists(self):
        import cue_api
        self.assertTrue(hasattr(cue_api, "search_templates"),
                        "cue_api.search_templates missing — Task 2 not applied?")
        self.assertTrue(callable(cue_api.search_templates))

    def test_cue_api_rewrite_exists(self):
        import cue_api
        self.assertTrue(hasattr(cue_api, "rewrite"),
                        "cue_api.rewrite missing — Task 3 not applied?")
        self.assertTrue(callable(cue_api.rewrite))

    def test_cue_api_chat_stream_and_replay_exist(self):
        import cue_api
        for fn in ("chat_stream", "replay", "create_template", "generate_template"):
            self.assertTrue(hasattr(cue_api, fn), f"cue_api.{fn} missing")

    def test_sse_report_helpers_exist(self):
        import sse_report
        for fn in ("extract_reporter_content", "diagnose_empty_report",
                   "extract_tool_calls", "extract_agent_timeline"):
            self.assertTrue(hasattr(sse_report, fn),
                            f"sse_report.{fn} missing — Task 1 not applied?")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)
