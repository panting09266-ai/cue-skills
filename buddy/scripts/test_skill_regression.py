#!/usr/bin/env python3
"""Skill-level regression tests (stdlib only, no pytest needed).

Run after editing tune_template.py / cue_api.py / validate_template.py to
catch drift against the cubemanus public API contract. Covers codex
!450 r3 review findings:

1. +tune prompt 不能再含 `introduction`(cubemanus contract phase 已落地)
2. cue_api 接受 legacy `task_configs` payload 转换为 `schedules`
3. search_plan 某个维度缺三件套 → error(block-level)
4. report_format 某节缺执行蓝图 → error(block-level)
5. search_tool_company / crawl_tool_site 在工具名 lint 被拦

Usage:
    python3 scripts/test_skill_regression.py

Exit 0 = all passed; non-zero = at least one failed (with detail).
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# Loaded lazily inside each test so import errors point to the right file.


class Case1_TunePromptUsesCanonicalName(unittest.TestCase):
    """codex !450 r3 #1 — tune prompt must use input_form_spec, not introduction."""

    def test_build_user_requirement_omits_introduction(self) -> None:
        from tune_template import build_user_requirement

        current = {
            "title": "示例",
            "primary_category": "投研",
            "secondary_category": "财报点评",
            "input_form_spec": "需提供: [目标_点评_公司]",
            "goal": "测试目标",
            "search_plan": "测试",
            "report_format": "## 1. 测试",
        }
        prompt = build_user_requirement(current, "略")
        # Prompt 必须用 canonical 名字,不应再提 introduction
        self.assertNotIn("introduction", prompt, "+tune prompt 仍含 'introduction'")
        self.assertIn("input_form_spec", prompt, "+tune prompt 缺 'input_form_spec'")


class Case2_LegacyTaskConfigsNormalizedToSchedules(unittest.TestCase):
    """codex !450 r3 #2 — cue_api 把 legacy task_configs 自动转 schedules,
    并 strip server-internal keys。"""

    def test_task_configs_to_schedules(self) -> None:
        from cue_api import _normalize_template_payload

        payload = {
            "title": "X",
            "task_input": "宁德时代",
            "task_cron_expressions": ["0 9 * * *", "0 9 * * 1"],
            "task_configs": [
                {
                    "type": "daily",
                    "time": "09:00",
                    "date_param": None,
                    "dates": None,
                    "name": "should-be-dropped",
                },
                {
                    "type": "weekly",
                    "time": "09:00",
                    "date_param": "MON",
                    "dates": None,
                    "name": "weekly",
                },
            ],
        }
        out = _normalize_template_payload(payload)
        # task_cron_expressions / task_configs 必须从 outbound 抹除
        self.assertNotIn("task_cron_expressions", out)
        self.assertNotIn("task_configs", out)
        # schedules 必须从 task_configs 派生,带正确 4 字段且无 name
        self.assertIn("schedules", out)
        self.assertEqual(len(out["schedules"]), 2)
        for s in out["schedules"]:
            self.assertEqual(set(s.keys()), {"type", "time", "date_param", "dates"})
        self.assertEqual(out["schedules"][0]["type"], "daily")
        self.assertEqual(out["schedules"][1]["date_param"], "MON")

    def test_schedules_present_wins_over_task_configs(self) -> None:
        """如果 caller 已传 schedules,不被 task_configs 覆盖。"""
        from cue_api import _normalize_template_payload

        payload = {
            "schedules": [
                {"type": "daily", "time": "10:00", "date_param": None, "dates": None}
            ],
            "task_configs": [
                {"type": "weekly", "time": "11:00", "date_param": "TUE", "dates": None}
            ],
        }
        out = _normalize_template_payload(payload)
        self.assertEqual(out["schedules"][0]["time"], "10:00")
        self.assertNotIn("task_configs", out)


class Case3_SearchPlanMissingTripletInOneDimension(unittest.TestCase):
    """codex !450 r3 #3 — block-level check finds per-dimension misses
    that global count would mask."""

    def test_dimension_missing_validation_strategy(self) -> None:
        from validate_template import validate

        # 3 维度,前 2 个完整,第 3 缺验证策略。全局 count=2/3/2 都 ≥ 2,
        # 旧 lint 全过;block-level 必须抓出第 3 维度缺。
        sp = (
            "**[[主体核验] 公开身份信息]**\n"
            "- **数据路由**: 工商 / 上市公告\n"
            "- **执行动作**: 法定代表人 / 注册资本\n"
            "- **验证策略**: 不一致时以披露为准\n\n"
            "**[[财务实证] 三年财务]**\n"
            "- **数据路由**: 年报\n"
            "- **执行动作**: 营收 / 净利润\n"
            "- **验证策略**: 评级最新\n\n"
            "**[[行业景气] 行业]**\n"
            "- **数据路由**: 协会数据\n"
            "- **执行动作**: 行业增长\n"
            # 故意缺 **验证策略**
        )
        payload = {
            "title": "x",
            "primary_category": "x",
            "secondary_category": "x",
            # 三段式变量必须中文(R1);用合规 `[目标_授信_企业]` 避免 fixture 污染
            # (codex !450 r3 review: 旧 `[目标_X_主体]` 含英文 X 会污染 errors)
            "input_form_spec": "需提供: [目标_授信_企业]，可提供: [关注_风险_主题] (默认: 通用)",
            "goal": "作为银行客户经理的预尽调助手，识别风险信号",
            "search_plan": sp,
            "report_format": (
                "> **关键配置**\n> - **目标对象**: [目标_授信_企业]\n\n"
                "# [目标_授信_企业] 测试\n\n"
                "## 1. A\n> **[执行蓝图]**\n> - **研究目标**: x\n"
                "> - **逻辑链条**: x\n> - **信息需求**: x\n> - **输出形式**: 段落\n"
                "## 2. B\n> **[执行蓝图]**\n> - **研究目标**: x\n"
                "> - **逻辑链条**: x\n> - **信息需求**: x\n> - **输出形式**: 段落\n"
                "## 3. C\n> **[执行蓝图]**\n> - **研究目标**: x\n"
                "> - **逻辑链条**: x\n> - **信息需求**: x\n> - **输出形式**: 段落\n"
                "本报告基于公开信息编制\n"
            ),
        }
        findings = validate(payload)
        errors = [f for f in findings if f.severity == "error"]
        # 必须有一条 error 指向 search_plan 第 3 维度 + 验证策略 缺失
        relevant = [
            f
            for f in errors
            if f.field == "search_plan" and "验证策略" in f.message and "行业" in f.message
        ]
        self.assertTrue(
            relevant,
            f"block-level lint 没抓到第 3 维度缺验证策略;all errors: {[str(f) for f in errors]}",
        )
        # 且其他字段不应被该 fixture 污染产生 errors (codex !450 r3 NICE)
        unrelated = [f for f in errors if f.field != "search_plan"]
        self.assertEqual(
            unrelated, [], f"fixture 污染:非 search_plan field 也报 errors: {[str(f) for f in unrelated]}"
        )


class Case4_ReportSectionMissingBlueprint(unittest.TestCase):
    """codex !450 r3 #4 — 某节缺执行蓝图引用块时,error 必须按章节定位。"""

    def test_section_missing_blueprint_block_is_error(self) -> None:
        from validate_template import validate

        # 第 2 节有蓝图,第 1/3 节缺
        rf = (
            "> **关键配置**\n> - **目标对象**: [目标_X_主体]\n\n"
            "# [目标_X_主体] 测试报告\n\n"
            "## 1. 第一节\n内容(无蓝图)\n\n"
            "## 2. 第二节\n> **[执行蓝图]**\n"
            "> - **研究目标**: x\n> - **逻辑链条**: x\n"
            "> - **信息需求**: x\n> - **输出形式**: 段落\n\n"
            "## 3. 第三节\n内容(也无蓝图)\n\n"
            "本报告基于公开信息编制\n"
        )
        payload = {
            "title": "x",
            "primary_category": "x",
            "secondary_category": "x",
            # 合规三段式 + 合规维度 label (codex !450 r3 fixture cleanup)
            "input_form_spec": "需提供: [目标_授信_企业]，可提供: [关注_风险_主题] (默认: 通用)",
            "goal": "作为银行客户经理的预尽调助手，识别风险信号",
            "search_plan": (
                "**[[主体核验] 公开身份]**\n- **数据路由**: 工商\n"
                "- **执行动作**: 法人\n- **验证策略**: 以披露为准\n\n"
                "**[[财务实证] 三年财务]**\n- **数据路由**: 年报\n"
                "- **执行动作**: 营收\n- **验证策略**: 评级最新\n"
            ),
            "report_format": rf,
        }
        findings = validate(payload)
        errors = [f for f in findings if f.severity == "error"]
        # 必须有两条 error 指向第 1 / 第 3 节缺蓝图
        sec1 = [
            f
            for f in errors
            if "执行蓝图" in f.message and ("第 1 节" in f.message or "「第一节」" in f.message)
        ]
        sec3 = [
            f
            for f in errors
            if "执行蓝图" in f.message and ("第 3 节" in f.message or "「第三节」" in f.message)
        ]
        self.assertTrue(sec1, f"未抓到第 1 节缺蓝图;errors: {[str(f) for f in errors]}")
        self.assertTrue(sec3, f"未抓到第 3 节缺蓝图;errors: {[str(f) for f in errors]}")
        # 非 report_format 字段不应被 fixture 污染 (codex !450 r3 NICE)
        unrelated = [f for f in errors if f.field != "report_format"]
        self.assertEqual(
            unrelated, [], f"fixture 污染:非 report_format 报 errors: {[str(f) for f in unrelated]}"
        )


class Case5_ToolNameLeakRegexCoversAllFamilies(unittest.TestCase):
    """codex !450 r3 #5 — search_tool* / crawl_tool* 必须被工具名 lint 拦。"""

    def test_search_tool_company_caught(self) -> None:
        from validate_template import TOOL_NAME_LEAK_RE

        for sample in (
            "调用 search_tool_company 拉公司",
            "用 search_tool 检索",
            "执行 search_tool_disclosure 获取披露",
            "走 crawl_tool_site 抓页",
            "通过 crawl_tool 爬取",
            "用 get_disclosure 拉公告",  # 原有 family,保持工作
            "调 list_companies",
            "find_recent_news",
        ):
            with self.subTest(sample=sample):
                self.assertRegex(sample, TOOL_NAME_LEAK_RE, f"未抓 {sample!r}")

    def test_legitimate_text_not_falsely_flagged(self) -> None:
        """合规中文文本(无下划线工具名)不应被 leak regex 命中。

        Codex !450 r3 confirmation: `search_tools` 复数形式也属于工具名引用
        (meta 描述里写工具集合也是 R5 leak),应被命中 — 故不在"不应被抓"列表。
        """
        from validate_template import TOOL_NAME_LEAK_RE

        for sample in (
            "通过监管披露与行业数据交叉验证",
            "数据路由: 上市公司公告",
            "司法 / 舆情 / 监管处罚",
            "穿透 [目标_授信_企业] 的公开监管披露",
        ):
            with self.subTest(sample=sample):
                self.assertNotRegex(sample, TOOL_NAME_LEAK_RE, f"误报: {sample!r}")


# Bonus: cue_api task_input client-side lint regression
class Case6_TaskInputClientSideFastFail(unittest.TestCase):
    """codex !450 r3 #2 mirror — `cue_api._normalize_template_payload`
    在 send 前本地拦截违 R9 task_input。"""

    def test_placeholder_text_raises(self) -> None:
        from cue_api import _normalize_template_payload

        with self.assertRaises(ValueError) as cm:
            _normalize_template_payload(
                {"task_input": "请输入企业名称或统一社会信用代码。可选补充..."}
            )
        self.assertIn("R9", str(cm.exception))

    def test_placeholder_variable_raises(self) -> None:
        from cue_api import _normalize_template_payload

        with self.assertRaises(ValueError) as cm:
            _normalize_template_payload({"task_input": "[目标_授信_企业]"})
        self.assertIn("占位", str(cm.exception))

    def test_concrete_subject_passes(self) -> None:
        from cue_api import _normalize_template_payload

        out = _normalize_template_payload({"task_input": "宁德时代"})
        self.assertEqual(out["task_input"], "宁德时代")


class Case7_DimRegexCoversNonChineseLabels(unittest.TestCase):
    """codex !450 r3 #2 — search_plan dim regex must accept English/digit/
    dash labels like `[[ESG-2026]]`, `[[A股]]`, `[[2026]]`."""

    def test_english_dash_digit_labels_match(self) -> None:
        from validate_template import _SEARCH_PLAN_DIM_RE

        for sample in (
            "**[[ESG-2026] ESG事项]**",
            "**[[A股] 披露]**",
            "**[[2026] 年度趋势]**",
            "**[[主体核验] 公开身份信息]**",  # 中文 label 不退化
        ):
            with self.subTest(sample=sample):
                self.assertRegex(sample, _SEARCH_PLAN_DIM_RE)


class Case8_RecommendedTaskHelperRequiresSchedules(unittest.TestCase):
    """codex !450 r3 #1 — update_template_recommended_task 必须本地 raise
    若 schedules 缺失/为空,而不是发到后端拿 422。"""

    def test_missing_schedules_raises(self) -> None:
        from cue_api import update_template_recommended_task

        with self.assertRaises(ValueError) as cm:
            # 注意: 不能真发 HTTP, 但 schedules 校验在 _request 之前
            update_template_recommended_task("tpl_x", schedules=[])
        self.assertIn("schedules", str(cm.exception))

    def test_non_list_schedules_raises(self) -> None:
        from cue_api import update_template_recommended_task

        with self.assertRaises(ValueError):
            update_template_recommended_task("tpl_x", schedules=None)  # type: ignore[arg-type]


class Case9_CronExpressionsTypoRejected(unittest.TestCase):
    """codex !450 r3 #4 — `cron_expressions` (no `task_` prefix) typo 必须
    本地 raise; 否则后端 extra='ignore' 会静默吞掉。"""

    def test_typo_field_raises(self) -> None:
        from cue_api import _normalize_template_payload

        with self.assertRaises(ValueError) as cm:
            _normalize_template_payload(
                {"title": "x", "cron_expressions": ["0 9 * * *"]}
            )
        self.assertIn("cron_expressions", str(cm.exception))

    def test_task_configs_missing_type_raises(self) -> None:
        """codex !450 r3 #3 — task_configs item 缺 type/time 应本地 raise."""
        from cue_api import _normalize_template_payload

        with self.assertRaises(ValueError) as cm:
            _normalize_template_payload(
                {
                    "task_configs": [
                        {"time": "09:00", "date_param": None, "dates": None}
                    ]
                }
            )
        self.assertIn("type", str(cm.exception))


class Case10_TestTemplateDiagnosis(unittest.TestCase):
    """codex r4 finding — test_template.py _diagnose_empty_report 分类正确性.

    +test SSE 长流断连场景的诊断函数,决定要不要走 replay fallback。
    """

    def test_stream_cut_before_reporter(self) -> None:
        """events 只有 coordinator/researcher,reporter 还没 start 就断流。"""
        import json

        from test_template import _diagnose_empty_report

        events = [
            ("start_of_agent", json.dumps({"data": {"agent_name": "coordinator"}})),
            ("message", json.dumps({"data": {"delta": {"content": "x"}}})),
            ("end_of_agent", json.dumps({"data": {"agent_name": "coordinator"}})),
            ("start_of_agent", json.dumps({"data": {"agent_name": "researcher"}})),
            ("message", json.dumps({"data": {"delta": {"content": "y"}}})),
        ]
        d = _diagnose_empty_report(events, elapsed=372.9, timeout=300.0)
        self.assertEqual(d["kind"], "stream_cut_before_reporter")
        self.assertEqual(d["last_agent"], "researcher")
        self.assertFalse(d["reporter_started"])
        self.assertTrue(d["hit_timeout"])

    def test_top_level_agent_name_events_are_supported(self) -> None:
        """Replay SSE uses top-level agent_name; extractor must support it."""
        import json

        from test_template import _diagnose_empty_report, _extract_reporter_content

        events = [
            ("start_of_agent", json.dumps({"agent_name": "reporter"})),
            (
                "message",
                json.dumps(
                    {
                        "agent_name": "reporter",
                        "delta": {"content": "# 淡水泉 尽调报告\n"},
                    }
                ),
            ),
            ("end_of_agent", json.dumps({"agent_name": "reporter"})),
        ]
        report = _extract_reporter_content(events)
        self.assertIn("淡水泉", report)

        d = _diagnose_empty_report(events, elapsed=1.0, timeout=300.0)
        self.assertTrue(d["reporter_started"])
        self.assertTrue(d["reporter_ended"])

    def test_no_agent_events(self) -> None:
        """events 完全无 agent — auth/template_id 错或后端没响应。"""
        import json

        from test_template import _diagnose_empty_report

        events = [
            ("message", json.dumps({"data": {"delta": {"content": "noise"}}})),
        ]
        d = _diagnose_empty_report(events, elapsed=2.0, timeout=300.0)
        self.assertEqual(d["kind"], "no_agent_events")
        self.assertIsNone(d["last_agent"])
        self.assertFalse(d["hit_timeout"])

    def test_reporter_started_no_text(self) -> None:
        """reporter start 看到了但没 message text — 罕见 server-side fail。"""
        import json

        from test_template import _diagnose_empty_report

        events = [
            ("start_of_agent", json.dumps({"data": {"agent_name": "reporter"}})),
            # 没 message events,直接 end
            ("end_of_agent", json.dumps({"data": {"agent_name": "reporter"}})),
        ]
        d = _diagnose_empty_report(events, elapsed=10.0, timeout=300.0)
        self.assertEqual(d["kind"], "reporter_started_no_text")
        self.assertTrue(d["reporter_started"])
        self.assertTrue(d["reporter_ended"])

    def test_extractor_works_without_end_marker(self) -> None:
        """codex r4 关键纠错:end_of_agent 缺失**不会**让 extractor 空 —
        in_reporter 保持 True 直到流结束,后续 message 仍累加。"""
        import json

        from test_template import _extract_reporter_content

        events = [
            ("start_of_agent", json.dumps({"data": {"agent_name": "reporter"}})),
            (
                "message",
                json.dumps({"data": {"delta": {"content": "## 1. 业绩\n"}}}),
            ),
            (
                "message",
                json.dumps({"data": {"delta": {"content": "营收增长 20%\n"}}}),
            ),
            # 没 end_of_agent — 流断在 reporter 中间
        ]
        report = _extract_reporter_content(events)
        # ✓ 即使 end 没到,extractor 仍累加,report 非空
        self.assertIn("业绩", report)
        self.assertIn("营收增长 20%", report)


if __name__ == "__main__":
    # Unbuffered + verbose for skill author workflow.
    unittest.main(verbosity=2)
