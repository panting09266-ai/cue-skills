#!/usr/bin/env python3
"""+test verb — run a real chat conversation against a template and
verify the resulting report against parametric checks derived from the
template's own `report_format` spec.

Usage:
    python3 test_template.py <template_id> <entity_name> [--save <md_path>]

Flow:
    1. GET /api/templates/<id>            → fetch template
    2. POST /api/chat/stream              → run real conversation
    3. Collect SSE events, accumulate reporter messages → final report
    4. Parametric 8-check verification
    5. Print + (optional) save Markdown run report

Notes:
    - Each invocation consumes Cue credits (typical 5-15 per run).
    - The script asks for explicit confirmation before starting.
    - No deletion / publishing / sensitive actions — read-only test.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow `python3 scripts/test_template.py` to find cue_api on sys.path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from cue_api import (  # noqa: E402
    CueAPIError,
    chat_stream,
    get_template,
    load_config,
    replay,
)
from validate_template import (  # noqa: E402
    FORBIDDEN_VERDICT_PHRASES,
    TOOL_NAME_LEAK_RE,
)


# ---------------------------------------------------------------------------
# SSE → report assembly
# ---------------------------------------------------------------------------


def _extract_reporter_content(events: list[tuple[str, str]]) -> str:
    """Walk the SSE event stream and accumulate text emitted while inside
    the reporter agent's `start_of_agent`/`end_of_agent` window.

    Matches the server-side reporter window logic from
    src/service/workflow/report.py."""
    in_reporter = False
    pieces: list[str] = []
    for event, data in events:
        if not data:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if event == "start_of_agent" and _agent_name(payload) == "reporter":
            in_reporter = True
            continue
        if event == "end_of_agent" and _agent_name(payload) == "reporter":
            in_reporter = False
            continue
        if in_reporter and event == "message":
            delta = (payload.get("data") or {}).get("delta") or {}
            text = delta.get("content") or ""
            if text:
                pieces.append(text)
    return "".join(pieces)


def _agent_name(payload: dict) -> str:
    return (payload.get("data") or {}).get("agent_name", "")


def _diagnose_empty_report(
    events: list[tuple[str, str]],
    elapsed: float,
    timeout: float,
) -> dict:
    """Classify why `_extract_reporter_content` returned empty.

    Returns dict with keys:
      - kind: 'stream_cut_before_reporter' | 'reporter_started_no_text'
              | 'no_agent_events' | 'unknown'
      - last_agent: last `start_of_agent` agent_name seen, or None
      - reporter_started: bool
      - reporter_ended: bool
      - message_event_count: int
      - hit_timeout: bool (elapsed >= timeout - epsilon)
    """
    last_agent: str | None = None
    reporter_started = False
    reporter_ended = False
    message_count = 0
    for event, data in events:
        if not data:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        if event == "start_of_agent":
            ag = _agent_name(payload)
            if ag:
                last_agent = ag
            if ag == "reporter":
                reporter_started = True
        elif event == "end_of_agent" and _agent_name(payload) == "reporter":
            reporter_ended = True
        elif event == "message":
            message_count += 1

    hit_timeout = elapsed >= (timeout - 5.0)

    if not last_agent:
        kind = "no_agent_events"
    elif not reporter_started:
        kind = "stream_cut_before_reporter"
    else:
        # reporter started but no text accumulated — rare server-side case
        kind = "reporter_started_no_text"

    return {
        "kind": kind,
        "last_agent": last_agent,
        "reporter_started": reporter_started,
        "reporter_ended": reporter_ended,
        "message_event_count": message_count,
        "hit_timeout": hit_timeout,
    }


def _extract_tool_calls(events: list[tuple[str, str]]) -> list[dict]:
    """Build a per-call dict: name, input summary, result preview, owning agent.

    End users debugging a +test run don't have ES trace access — but the
    SSE stream carries all of: tool_call (input), tool_call_result
    (output), agent context. This reconstructs that view from SSE alone.
    """
    calls: dict[str, dict] = {}
    order: list[str] = []
    current_agent = ""
    for event, data in events:
        if not data:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        d = payload.get("data") or {}
        if event == "start_of_agent":
            current_agent = d.get("agent_name", "")
        if event == "tool_call":
            tid = d.get("tool_call_id") or f"_anon_{len(order)}"
            inp = d.get("tool_input") or d.get("tool_plain_input") or {}
            calls[tid] = {
                "tool_name": d.get("tool_name", "?"),
                "tool_title": d.get("tool_title", ""),
                "input": inp,
                "result": None,
                "agent": current_agent,
            }
            order.append(tid)
        elif event == "tool_call_result":
            tid = d.get("tool_call_id")
            if tid in calls:
                calls[tid]["result"] = d.get("tool_result", "")
    return [calls[tid] for tid in order]


def _extract_agent_timeline(events: list[tuple[str, str]]) -> list[dict]:
    """Return per-agent (name, execution_time_s). One entry per
    end_of_agent event."""
    timeline: list[dict] = []
    for event, data in events:
        if event != "end_of_agent" or not data:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        d = payload.get("data") or {}
        timeline.append(
            {
                "agent": d.get("agent_name", "?"),
                "execution_time": d.get("execution_time", 0),
            }
        )
    return timeline


def _summarize_tool_input(inp) -> str:
    """Render tool_input as a short single-line summary for the run.md table."""
    if isinstance(inp, dict):
        # Common keys: query / keyword / entity / params
        for k in ("query", "keyword", "entity", "company_name", "params"):
            if k in inp and inp[k]:
                v = str(inp[k]).replace("\n", " ")
                return f"{k}={v[:80]}"
        # Fallback: first key=value pair
        for k, v in inp.items():
            return f"{k}={str(v)[:80]}".replace("\n", " ")
        return "(empty)"
    s = str(inp).replace("\n", " ")
    return s[:120] or "(empty)"


def _preview_tool_result(result) -> str:
    """Render tool_result as ≤120 char preview for the run.md table."""
    if result is None:
        return "(no result captured)"
    s = str(result).replace("\n", " ").replace("|", "\\|")
    return s[:120] + ("..." if len(s) > 120 else "")


# ---------------------------------------------------------------------------
# Parametric 8 checks
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str

    def render(self) -> str:
        mark = "✅" if self.ok else "❌"
        return f"  {mark} {self.name}\n      {self.detail}"


THREE_SEG = re.compile(r"\[[一-鿿]+_[一-鿿]+_[一-鿿]+\]")
SECTION_HEADING = re.compile(r"(?m)^##\s*(\d+)[.、]\s*(.+?)\s*$")
# Reuse validator's tool-name pattern to avoid validator/runtime-test drift
# (codex !450 r3 Block 5). Covers get_/list_/find_/search_tool*/crawl_tool*.
TOOL_NAME_PATTERN = TOOL_NAME_LEAK_RE


def _check_title_contains_entity(report: str, entity: str) -> CheckResult:
    first_line = next((ln for ln in report.splitlines() if ln.startswith("#")), "")
    return CheckResult(
        name="标题含主体名",
        ok=entity in first_line,
        detail=f"first heading: {first_line[:80] or '(missing)'}",
    )


def _check_no_var_residue(report: str) -> CheckResult:
    hits = THREE_SEG.findall(report)
    return CheckResult(
        name="无三段式变量字面残留",
        ok=not hits,
        detail=f"found {len(hits)} residual variables: {hits[:3]}" if hits else "0",
    )


def _check_no_verdict_phrases(report: str) -> CheckResult:
    leaks = [p for p in FORBIDDEN_VERDICT_PHRASES if p in report]
    return CheckResult(
        name="无准入决策语",
        ok=not leaks,
        detail=f"found verdict phrases: {leaks}" if leaks else "0",
    )


def _check_section_count(template_rf: str, report: str) -> CheckResult:
    t = SECTION_HEADING.findall(template_rf)
    r = SECTION_HEADING.findall(report)
    return CheckResult(
        name="章节数与模板一致",
        ok=len(t) == len(r),
        detail=f"template={len(t)}, report={len(r)}",
    )


def _check_section_sequential(report: str) -> CheckResult:
    nums = [int(n) for n, _ in SECTION_HEADING.findall(report)]
    expected = list(range(1, len(nums) + 1))
    return CheckResult(
        name="章节编号连续递增",
        ok=nums == expected and len(nums) > 0,
        detail=f"observed: {nums}",
    )


def _check_section_titles_appear(template_rf: str, report: str) -> CheckResult:
    t_titles = [title for _, title in SECTION_HEADING.findall(template_rf)]
    r_titles_blob = "\n".join(title for _, title in SECTION_HEADING.findall(report))
    misses = [t for t in t_titles if t not in r_titles_blob]
    return CheckResult(
        name="模板各章节标题在报告中出现",
        ok=not misses,
        detail=(
            f"all {len(t_titles)} present"
            if not misses
            else f"missing {len(misses)}: {misses[:3]}"
        ),
    )


def _check_no_tool_names(report: str) -> CheckResult:
    hits = TOOL_NAME_PATTERN.findall(report)
    return CheckResult(
        name="报告中无工具名泄漏",
        ok=not hits,
        detail=f"found {len(hits)} tool names: {hits[:3]}" if hits else "0",
    )


def _check_disclaimer(template_rf: str, report: str) -> CheckResult:
    needs = "本报告基于公开信息编制" in template_rf or "免责声明" in template_rf
    has = "本报告基于公开信息编制" in report or "免责声明" in report
    if not needs:
        return CheckResult(name="免责声明", ok=True, detail="(template requires none)")
    return CheckResult(
        name="免责声明（模板要求）",
        ok=has,
        detail="present" if has else "missing",
    )


def run_checks(template: dict, entity: str, report: str) -> list[CheckResult]:
    rf = template.get("report_format", "")
    return [
        _check_title_contains_entity(report, entity),
        _check_no_var_residue(report),
        _check_no_verdict_phrases(report),
        _check_section_count(rf, report),
        _check_section_sequential(report),
        _check_section_titles_appear(rf, report),
        _check_no_tool_names(report),
        _check_disclaimer(rf, report),
    ]


# ---------------------------------------------------------------------------
# Chat orchestration
# ---------------------------------------------------------------------------


def build_chat_payload(template_id: str, entity: str) -> dict:
    """Minimal /api/chat/stream payload that exercises the template path.

    Backend-automation flags (all default to True on the server, must be
    explicitly disabled for non-interactive runs):

    - need_analysis=False: per Cue API docs, when called as a backend
      integration, leaving this on causes the workflow to interrupt and
      wait for a user clarification form, hanging the SSE stream.
    - need_confirm=False: skip the 仿写 confirmation step
    - need_underlying=False: we already provide the entity in the prompt
    - need_recommend=False: no follow-up question suggestions needed
    """
    conv_id = f"buddy-test-{uuid.uuid4().hex[:12]}"
    return {
        "messages": [
            {"role": "user", "content": f"请基于公开信息研究 {entity}"},
        ],
        "conversation_id": conv_id,
        "chat_id": uuid.uuid4().hex,
        "template_id": template_id,
        "need_confirm": False,
        "need_analysis": False,
        "need_underlying": False,
        "need_recommend": False,
    }


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------


def _render_run_md(
    template_id: str,
    entity: str,
    template: dict,
    report: str,
    checks: list[CheckResult],
    conv_id: str,
    elapsed_s: float,
    events: list[tuple[str, str]] | None = None,
) -> str:
    rows = "\n".join(c.render() for c in checks)
    passed = sum(1 for c in checks if c.ok)
    header = (
        f"# Buddy +test run — {template.get('title', template_id)}\n\n"
        f"- template_id: `{template_id}`\n"
        f"- entity: `{entity}`\n"
        f"- conv_id: `{conv_id}`\n"
        f"- elapsed: {elapsed_s:.1f}s\n"
        f"- report_chars: {len(report)}\n"
        f"- checks: **{passed}/{len(checks)}** passed\n\n"
        f"## Checks\n\n{rows}\n\n"
    )

    debug_sections = ""
    if events:
        timeline = _extract_agent_timeline(events)
        tool_calls = _extract_tool_calls(events)

        if timeline:
            tl_rows = "\n".join(
                f"| {i + 1} | {t['agent']} | {t['execution_time']:.2f}s |"
                for i, t in enumerate(timeline)
            )
            debug_sections += (
                "## Agent timeline\n\n"
                "| # | agent | execution_time |\n"
                "|---|---|---|\n"
                f"{tl_rows}\n\n"
            )

        if tool_calls:
            tc_rows = "\n".join(
                "| {i} | {agent} | {tool} | {title} | {inp} | {res} |".format(
                    i=i + 1,
                    agent=tc.get("agent") or "-",
                    tool=tc.get("tool_name") or "?",
                    title=tc.get("tool_title") or "-",
                    inp=_summarize_tool_input(tc.get("input")).replace("|", "\\|"),
                    res=_preview_tool_result(tc.get("result")),
                )
                for i, tc in enumerate(tool_calls)
            )
            debug_sections += (
                "## Tool calls\n\n"
                "（按调用顺序；end users 调试时可对照报告里的引用 ↔ 工具结果）\n\n"
                "| # | agent | tool | title | input | result preview |\n"
                "|---|---|---|---|---|---|\n"
                f"{tc_rows}\n\n"
            )

        # Event count breakdown — useful "did the stream look healthy" check
        event_counts: dict[str, int] = {}
        for ev, _ in events:
            event_counts[ev] = event_counts.get(ev, 0) + 1
        if event_counts:
            ec_rows = "\n".join(
                f"| {ev} | {n} |" for ev, n in sorted(event_counts.items())
            )
            debug_sections += (
                "## Event counts\n\n"
                "| event | count |\n|---|---|\n"
                f"{ec_rows}\n\n"
            )

    report_section = f"## Report (raw)\n\n```markdown\n{report}\n```\n"
    return header + debug_sections + report_section


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("template_id")
    p.add_argument("entity", help="测试主体（如 万科 / 宁德时代）")
    p.add_argument(
        "--save",
        metavar="PATH",
        help=(
            "保存 Markdown 运行记录的路径（默认 ./buddy-run-<ts>.md）。"
            "失败时也保存，方便事后排查。"
        ),
    )
    p.add_argument(
        "--no-save",
        action="store_true",
        help="不保存运行记录（默认会保存到 ./buddy-run-<ts>.md）",
    )
    p.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="跳过 credits 消耗确认（默认会问)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=900.0,
        help="SSE 流总超时秒（默认 900）",
    )
    args = p.parse_args(argv)

    try:
        load_config()
    except SystemExit:
        return 2

    if not args.yes:
        sys.stderr.write(
            f"\n[+test] 将以主体 '{args.entity}' 跑模板 {args.template_id}\n"
            f"        实际消耗的 credits 取决于模板复杂度（章节数、调研维度数、"
            "工具触发次数），可能远超过粗略估算的 5-15。"
            "前 1-2 次跑是为了校准——确切费用见 cuecue.cn 工作台。"
            "继续？[y/N]: "
        )
        sys.stderr.flush()
        if input().strip().lower() not in ("y", "yes"):
            print("[+test] cancelled.")
            return 1

    try:
        template = get_template(args.template_id)
    except CueAPIError as e:
        sys.stderr.write(f"[+test] fetch template failed: {e}\n")
        sys.stderr.write(f"        → {e.user_hint()}\n")
        return 1
    if not template or "report_format" not in template:
        sys.stderr.write("[+test] template 缺 report_format，无法跑参数化检查\n")
        return 1

    payload = build_chat_payload(args.template_id, args.entity)
    conv_id = payload["conversation_id"]
    print(f"[+test] conv_id={conv_id}, posting chat...")
    t0 = time.time()
    events: list[tuple[str, str]] = []
    seen_reporter_end = False
    stream_exc: Exception | None = None
    try:
        for event, data in chat_stream(payload, max_seconds=args.timeout):
            events.append((event, data))
            if event == "end_of_agent":
                try:
                    if _agent_name(json.loads(data)) == "reporter":
                        seen_reporter_end = True
                        # Don't break — let the stream close itself so
                        # status flips to completed server-side
                except json.JSONDecodeError:
                    pass
            if time.time() - t0 > args.timeout:
                sys.stderr.write("[+test] timeout watching SSE\n")
                break
    except CueAPIError as e:
        # 4xx/5xx 含 auth/template_id 问题 — 这类错误 replay 也救不了,直接报。
        sys.stderr.write(f"[+test] chat_stream failed: {e}\n")
        sys.stderr.write(f"        → {e.user_hint()}\n")
        return 1
    except (OSError, ValueError) as e:
        # codex r5 finding: 网络抖动 / SSE 解析炸 / socket timeout 等非 CueAPIError
        # 之前 propagate 直接 return 1,绕过 replay fallback。现在记录异常,
        # 让后续 diagnose+replay 仍有机会救场 — events 部分捕获就够诊断方向。
        # OSError 涵盖 urllib.error.URLError, socket.timeout, ConnectionResetError 等;
        # ValueError 涵盖 SSE 行解析炸的 case。
        stream_exc = e
        sys.stderr.write(
            f"[+test] stream raised {type(e).__name__}: {e}\n"
            f"        events captured before raise: {len(events)}; "
            f"will try diagnose + replay fallback\n"
        )

    elapsed = time.time() - t0
    print(f"[+test] stream done in {elapsed:.1f}s, events={len(events)}")
    if not seen_reporter_end:
        print("[+test] WARNING: did not observe reporter end_of_agent — report may be partial")

    report = _extract_reporter_content(events)

    # L1 诊断分流 + L2 replay fallback (codex r4 finding):
    # +test stream 经常因长跑 (>5min deep research) / 网络抖动 / client timeout
    # 在 reporter agent 启动**之前**断连。server 仍跑完写 DB,但 client events
    # 拿不到 reporter 段,_extract 空 return。`GET /api/replay/<conv>?resume=0`
    # 是无 credit 的 DB-replay,可在断连后重拉完整 events 流。
    if not report:
        diag = _diagnose_empty_report(events, elapsed, args.timeout)
        print(
            f"[+test] empty report detected → diagnosis: kind={diag['kind']}, "
            f"last_agent={diag['last_agent']!r}, reporter_started={diag['reporter_started']}, "
            f"messages={diag['message_event_count']}, hit_timeout={diag['hit_timeout']}"
        )
        if diag["kind"] == "stream_cut_before_reporter":
            print(
                f"[+test] stream disconnected before reporter started "
                f"(last agent: {diag['last_agent']!r}). "
                f"Retrying via /api/replay/{conv_id}?resume=0 (no credit cost)…"
            )
            replay_events: list[tuple[str, str]] = []
            try:
                for event, data in replay(conv_id, max_seconds=args.timeout):
                    replay_events.append((event, data))
            except CueAPIError as e:
                sys.stderr.write(
                    f"[+test] replay failed: {e}\n"
                    f"        → server may not have finished yet; wait a few seconds "
                    f"and run: cue_api.py replay {conv_id}\n"
                )
                return 1
            report = _extract_reporter_content(replay_events)
            if report:
                print(
                    f"[+test] ✓ recovered via replay: events={len(replay_events)}, "
                    f"report={len(report)} chars"
                )
                events = replay_events  # so subsequent _render_run_md / tool_calls reflect full stream
            else:
                sys.stderr.write(
                    "[+test] replay also produced empty report — server-side reporter "
                    "may have failed. Check cuecue.cn web for this conversation_id.\n"
                )
                return 1
        elif diag["kind"] == "no_agent_events":
            sys.stderr.write(
                "[+test] no agent events received — likely API auth / workflow_id / "
                "template_id problem (not a long-stream issue). Check args + key.\n"
            )
            return 1
        else:  # reporter_started_no_text
            sys.stderr.write(
                "[+test] reporter started but emitted no text content. "
                "Server-side reporter agent likely failed; check cuecue.cn web replay.\n"
            )
            return 1

    checks = run_checks(template, args.entity, report)
    passed = sum(1 for c in checks if c.ok)
    print(f"\n[+test] checks: {passed}/{len(checks)} passed\n")
    for c in checks:
        print(c.render())
    print()

    md = _render_run_md(
        args.template_id,
        args.entity,
        template,
        report,
        checks,
        conv_id,
        elapsed,
        events=events,
    )
    if not args.no_save:
        save_path = (
            args.save
            or f"./buddy-run-{args.template_id[-8:]}-{time.strftime('%Y%m%d-%H%M%S')}.md"
        )
        Path(save_path).write_text(md, encoding="utf-8")
        print(f"[+test] saved run report → {save_path}")
    elif args.save:
        sys.stderr.write("[+test] --no-save overrides --save; nothing saved.\n")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
