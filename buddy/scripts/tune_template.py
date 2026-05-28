#!/usr/bin/env python3
"""+tune verb — use the seed: bypass on /api/generate_template to ask
the LLM to revise an existing template based on a list of issues, then
validate, diff-preview, and (on confirmation) PUT the update.

Usage:
    python3 tune_template.py <template_id> --issues <issues.txt>
    python3 tune_template.py <template_id> --message "把章节 4 拆成 4 和 5"
    cat issues.txt | python3 tune_template.py <template_id> --stdin

Flow:
    1. GET /api/templates/<id>             → current template
    2. Build user_requirement = current_template_json + issues
    3. POST /api/generate_template         → streamed JSON of 4 fields
    4. Local validate (validate_template.validate)
    5. Show diff of (input_form_spec / goal / search_plan / report_format)
    6. Ask confirmation
    7. PUT /api/templates/<id>             → persist

Notes:
    - Consumes Cue credits (typically 1-3 积分 per tune call).
    - The generated draft is **shown to user first**; no auto-PUT.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time
from pathlib import Path

# Make sibling modules importable when invoked directly
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from cue_api import (  # noqa: E402
    CueAPIError,
    generate_template,
    get_template,
    load_config,
    update_template,
)
from validate_template import validate  # noqa: E402


LLM_FIELDS = ("input_form_spec", "goal", "search_plan", "report_format")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def build_user_requirement(current: dict, issues: str) -> str:
    """Compose the message sent to /api/generate_template.

    Seed-bypass mode: backend uses ONLY user_requirement (no chat history).
    So we hand it the full current template + the desired fixes.
    """
    # cubemanus contract phase (2026-05-20) — backend `agents/types.py:Template`
    # 已 strict 输出 canonical `input_form_spec` 字段;`introduction` 字段已
    # 在 alembic 20260520c (cubemanus MR !446) drop column。tune script
    # 全量切到 canonical 命名。
    current_form_spec = current.get("input_form_spec") or ""
    return (
        "请基于以下现有模板，按问题清单做最小且必要的修改，"
        "重新生成 input_form_spec / goal / search_plan / report_format 4 个字段。"
        "保持业务语义不变，仅修复指出的问题；"
        "其余部分保持稳定，不要大幅改写。\n\n"
        "【当前模板】\n"
        f"标题: {current.get('title', '')}\n"
        f"分类: {current.get('primary_category', '')} / {current.get('secondary_category', '')}\n\n"
        f"input_form_spec (用户输入表单规范):\n{current_form_spec}\n\n"
        f"goal:\n{current.get('goal', '')}\n\n"
        f"search_plan:\n{current.get('search_plan', '')}\n\n"
        f"report_format:\n{current.get('report_format', '')}\n\n"
        "【问题清单】\n"
        f"{issues}\n\n"
        "【硬约束（违反将被本地校验拒绝）】\n"
        "1. input_form_spec 单行,含三段式变量 [属性_主体_类型],以 `需提供:` 开头\n"
        "2. goal 单段攻击力句式，无编号清单，无'建议进入/谨慎进入/暂缓进入'决策语\n"
        "3. search_plan 按数据源聚类（**[[标签] 维度]** 形式），每维度含 数据路由/执行动作/验证策略\n"
        "4. report_format 主标题含三段式变量，章节连续递增，每章 `> **[执行蓝图]**` 含 4 件套\n"
        "5. 所有字段不出现工具名（get_*/list_*/find_*/search_tool*/crawl_tool*）\n"
    )


# ---------------------------------------------------------------------------
# Streaming + parse
# ---------------------------------------------------------------------------


def call_generate(current: dict, issues: str) -> dict:
    """Returns dict with the 4 LLM fields parsed from the stream."""
    conv_id = f"seed:tune:{int(time.time())}"
    req = build_user_requirement(current, issues)
    print("[+tune] streaming generate_template …", file=sys.stderr)
    raw = generate_template(conv_id, req)
    # The server emits raw JSON one chunk per SSE data line; reassemble:
    text = raw.strip()
    # Try to find the outermost {...} JSON block
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError(f"could not locate JSON in stream output (head={text[:200]!r})")
    blob = text[start : end + 1]
    return json.loads(blob)


# ---------------------------------------------------------------------------
# Diff rendering
# ---------------------------------------------------------------------------


def render_diff(field: str, old: str, new: str) -> str:
    diff = difflib.unified_diff(
        (old or "").splitlines(keepends=False),
        (new or "").splitlines(keepends=False),
        fromfile=f"{field} (current)",
        tofile=f"{field} (proposed)",
        lineterm="",
        n=2,
    )
    return "\n".join(diff)


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("template_id")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--issues", help="path to issues.txt (one bullet per line)")
    g.add_argument("--message", help="single-line issue description")
    g.add_argument("--stdin", action="store_true", help="read issues from stdin")
    p.add_argument("--yes", "-y", action="store_true", help="跳过 credits 确认")
    args = p.parse_args(argv)

    try:
        load_config()
    except SystemExit:
        return 2

    if args.issues:
        issues = Path(args.issues).read_text(encoding="utf-8")
    elif args.message:
        issues = args.message
    else:
        issues = sys.stdin.read()
    if not issues.strip():
        sys.stderr.write("[+tune] no issues provided\n")
        return 2

    if not args.yes:
        sys.stderr.write(
            "\n[+tune] 将调用 /api/generate_template 重新生成 4 字段。\n"
            "        实际积分取决于现有模板和问题清单长度（粗略 1-3 起步），"
            "确切费用见 cuecue.cn 工作台。继续？[y/N]: "
        )
        sys.stderr.flush()
        if input().strip().lower() not in ("y", "yes"):
            print("[+tune] cancelled.")
            return 1

    try:
        current = get_template(args.template_id)
    except CueAPIError as e:
        sys.stderr.write(f"[+tune] fetch failed: {e}\n")
        sys.stderr.write(f"        → {e.user_hint()}\n")
        return 1

    try:
        proposed = call_generate(current, issues)
    except (CueAPIError, RuntimeError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[+tune] generate failed: {e}\n")
        return 1

    # Merge proposed into a full payload for validation.
    # Backend strict schema emits canonical `input_form_spec`. We keep a
    # short-term `introduction` parse fallback for any stale snapshot that
    # might still surface the old key in the wild, but we do NOT write
    # `introduction` back into merged — that column was dropped in
    # cubemanus alembic 20260520c (PR-7b contract phase).
    merged = {**current}
    # Strip any legacy key from inherited `current` so it never gets PUT back.
    merged.pop("introduction", None)
    for k in LLM_FIELDS:
        val = None
        if k == "input_form_spec":
            val = proposed.get("input_form_spec") or proposed.get("introduction")
        else:
            val = proposed.get(k)
        if isinstance(val, str):
            merged[k] = val

    findings = validate(merged)
    err = [f for f in findings if f.severity == "error"]
    warn = [f for f in findings if f.severity == "warning"]
    print(f"\n[+tune] validation: {len(err)} errors, {len(warn)} warnings")
    for f in findings:
        print(" ", f)

    print("\n[+tune] proposed changes (unified diff):")
    for field in LLM_FIELDS:
        old = current.get(field, "")
        new = merged.get(field, "")
        if old == new:
            continue
        print(f"\n--- {field} ---")
        print(render_diff(field, old, new) or "(structurally identical)")

    if err:
        # Save proposal to /tmp so user can inspect & manually fix without
        # the JSON cluttering the terminal.
        proposal_path = Path(
            f"/tmp/cue-buddy-proposal-{args.template_id[-8:]}-"
            f"{time.strftime('%Y%m%d-%H%M%S')}.json"
        )
        proposal_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            "\n[+tune] 提案有 errors,不建议直接 +update。"
            "请按上面 ❌ 列表修改 issues 描述后重跑,"
            "或手工编辑后用 cue_api.py update 提交。"
        )
        print(f"[+tune] 提案已保存 → {proposal_path}")
        print("[+tune] 手工修法: ")
        print(
            f"  1) 编辑 {proposal_path} 修复 errors\n"
            f"  2) python3 scripts/validate_template.py {proposal_path}  "
            f"# 验证修复后是否过\n"
            f"  3) python3 scripts/cue_api.py update {args.template_id} "
            f"{proposal_path}  # 提交"
        )
        return 1

    if not args.yes:
        sys.stderr.write("\n[+tune] 接受此提案并 PUT 更新模板？[y/N]: ")
        sys.stderr.flush()
        if input().strip().lower() not in ("y", "yes"):
            print("[+tune] cancelled — no PUT performed. Draft saved in memory only.")
            return 1

    backup_path = _backup_before_put(args.template_id, current)
    print(f"[+tune] backed up current version → {backup_path}")

    try:
        result = update_template(args.template_id, {k: merged[k] for k in LLM_FIELDS})
    except CueAPIError as e:
        sys.stderr.write(f"[+tune] update failed: {e}\n")
        sys.stderr.write(f"        → {e.user_hint()}\n")
        sys.stderr.write(
            f"[+tune] previous version is preserved at {backup_path} — "
            "restore with `cue_api.py update <id> <backup>` if needed\n"
        )
        return 1
    print(f"[+tune] updated. Server returned: {result.get('template_id') or result.get('id')}")
    print(f"[+tune] rollback available: `cue_api.py update {args.template_id} {backup_path}`")
    return 0


def _backup_before_put(template_id: str, current: dict) -> Path:
    """Save current template snapshot to ~/.cue/backups/ — gives the user
    an undo path since PUT overwrites without server-side history."""
    backups_dir = Path.home() / ".cue" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in template_id)
    path = backups_dir / f"{safe_id}.{ts}.json"
    # Only keep the LLM-relevant fields + identity to keep the backup
    # restorable directly via `cue_api.py update`. Drop server-side
    # fields (timestamps, ids, etc) that PUT shouldn't see.
    snapshot = {k: current.get(k) for k in LLM_FIELDS if current.get(k) is not None}
    for meta in ("title", "primary_category", "secondary_category"):
        if current.get(meta) is not None:
            snapshot[meta] = current[meta]
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


if __name__ == "__main__":
    raise SystemExit(main())
