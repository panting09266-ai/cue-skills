---
name: cue-research
description: "Use when the user asks a research question they want Cue to answer. Triggers: 帮我查/调研/研究 + 主体或话题; ask Cue about X; 用 Cue 跑一下 Y. Matches ≤2 candidate buddies from the user's library (or falls back to free-form deep research with backend rewrite), confirms credits, runs, and offers to distill a successful free-form run into a saved buddy. Public-data scope only — refuse for private-data scenarios (real AML / medical / internal accounting)."
license: MIT
metadata:
  version: "0.1.0"
  requires:
    bins: ["python3"]
    envOptional: ["CUE_API_KEY", "CUE_API_BASE"]
  endpoints:
    base: "https://cuecue.cn/api"
    apiKeyPage: "https://cuecue.cn/api-key"
---

# cue-research — 让 Cue 在你的 agent 里直接干活

让你在自己的 AI agent 里**用自然语言把一个调研问题交给 Cue**：自动从你的搭子库里匹配 ≤2 个候选(或无合适搭子时改走"带后端 rewrite 的自由式深研")，确认 credits 后执行，跑完满意可以一键沉淀为搭子。本 skill 是 [`cue-buddy`](../buddy) 的兄弟 skill——cue-buddy 负责**做**搭子，cue-research 负责**用**搭子。

## 范围边界(避免起调用前踩坑)

Cue 工具面仅含**公开数据源**(工商/司法/监管/财报/资金流/招投标等)。需要私有数据的场景(真·反洗钱看银行流水、医疗诊断、企业内账)agent **拒绝执行**，提示用户改写成公开数据形态或去 cuecue.cn 网页端。

## 准备

跟 cue-buddy 共用一套 API key 配置(`CUE_API_KEY` env 或 `~/.cue/config.json`)。详见 [`../buddy/SKILL.md`](../buddy/SKILL.md) 的"准备"段。

## 调用约定(verbs)

| Verb | 做什么 | 耗 credits |
|---|---|---|
| `+ask <问题>` | 主入口：解析 → 匹配 ≤2 个搭子 → 用户选 1/2/0/n → 跑 → 交付 → 可选沉淀。**也接受隐式自然语言触发** | 跑前显式确认；不跑不收 |
| `+match <问题>` | 只匹配候选搭子，不跑 | 否 |
| `+rewrite <问题>` | 只调 /api/rewrite 看 user_confirmation + rewritten_mandate，不跑 | 否 |
| `+save <conversation_id>` | 把一次成功的 free-form 跑沉淀为搭子(handoff 给 cue-buddy 的 +author/+create) | 否(模板生成本身不消耗，跑测试才会) |

## 决策树

```
用户说什么(中/英文/口语)                                              → 走哪条
─────────────────────────────────────────────────────────────────────────
"帮我查/调研/研究 <主体或话题>"                                       → +ask
"ask Cue about X" / "用 Cue 跑一下 Y"                                  → +ask
"看看哪个搭子能查 X"(只匹配不跑)                                       → +match
"先帮我把这个问题改写成结构化的(不跑)"                                 → +rewrite
"把刚才那次调研存成搭子" / "save this run as a buddy"                  → +save
─────────────────────────────────────────────────────────────────────────
```

## 主流程 `+ask`(最常用)

### Stage 1: 解析 + 轻澄清

agent 从用户提问里抽：
- **核心实体**(公司/人物/产品/行业)
- **时间窗口**(若用户没说，问 1 句确认)
- **角度**(投资/合规/竞品/舆情；若明显歧义，问 1 句)

只问 ≤1 个澄清问题。**不重写深研逻辑**——那是后端 rewrite_prompt 的活，留给 Stage 4。

### Stage 2: 匹配候选搭子

`search_templates(keyword, include_system=True)`，agent 用 2-3 个 keyword 变体(实体名 / 类目词 / 角度词)分别搜，合并去重，按相关性 rerank，**最多取 2 个**。

⚠️ 后端 search 只匹配 title + primary/secondary category(不查 goal/input)，所以匹配是**关键词级、低置信**——不要 confidently 替用户选定；总是把"0 不用搭子直跑"作为合法选项。

### Stage 3: 呈现 + 用户确认

向用户展示，例如：

```
找到这些可能合适的搭子(关键词匹配，仅供参考)：
  1. <搭子A 标题> — <一句价值>
  2. <搭子B 标题> — <一句价值>
  0. 都不合适 → 走自由式深度调研(会先经过 /api/rewrite 做隐私脱敏 + 公开信源约束)
  n. 取消

确切 credits 跑完才知道(后端不提供 pre-run 估算，前几次主要用于校准；可在 cuecue.cn 工作台核对)。
请输入: 
```

### Stage 4a: 用户选 1/2 — 跑搭子

调 `chat_stream(template_id=<选中>, messages=[{role:user, content:<原问题或澄清后问题>}], need_analysis=False, need_confirm=False, need_underlying=False, need_recommend=False)`。复用 `sse_report.extract_reporter_content` + `diagnose_empty_report` + replay 兜底。

### Stage 4b: 用户选 0 — 自由式深度调研(经过 /api/rewrite)

1. 先调 `rewrite(input=<用户问题>)`，拿到 `user_confirmation` + `rewritten_mandate`。
2. 展示 `user_confirmation` 给用户(它会说明：要从什么视角调研、脱敏了哪些隐私)，并允许用户微调或确认。
3. 用户确认后，把 `rewritten_mandate` 作为 user message 发给 `chat_stream`(**无 template_id**，need_analysis=False)。

**为什么必须先 rewrite？** chat_stream 本身不调用 rewrite_prompt(只有 /api/rewrite 这个独立端点会)。跳过会丢掉隐私脱敏 + 公开信源约束 + 意图增强。

### Stage 5: 交付 + 满意度

展示报告(reporter content)。问：
- ✅ 满意 → 若是 4b 自由式跑，提示"是否把这次调研沉淀成搭子模板？(走 cue-buddy +save 流)"
- ❌ 不满意 → 提供下一步：换另一个候选搭子重跑 / 补充澄清后重跑 / 改用自由式

### Stage 6: 沉淀为搭子(可选 handoff 给 cue-buddy)

用户确认沉淀后：
- 把成功跑的 `conversation_id` + 原问题 + reporter 报告交给 cue-buddy。
- 触发 cue-buddy 的 `+author` 流(generate_template 用 `template_history_by_conversation_id(conversation_id)` 真的能拿到本次跑的历史，详见 cubemanus template.py:226-259)。
- 走 cue-buddy 的 `+validate` → `+create` 落库。
- 这是**显式的、用户确认的**一步，不自动。

## Hard rules(铁律)

1. **不自动选搭子**。永远让用户从 ≤2 候选 + "0 直跑" + "n 取消" 中选。
2. **每次真跑都显式确认 credits**。哪怕是用户选了"0 直跑"作为 fallback，也要再确认一次("自由式深研可能比有模板的更费 credits，确认继续？")。
3. **free-form 路径**(Stage 4b)**必须先调 /api/rewrite**。不要直接把用户原问题塞进 chat_stream。
4. **不在 agent 侧重写后端的 rewrite 逻辑**。要 rewrite 就调 /api/rewrite，要澄清 ≤1 句就好。
5. **不实现 `+delete`**(防误删；删搭子去网页工作台)。

## 安全规则

跟 cue-buddy 同源：API key 不出现在输出/日志/提交；用户粘了 key → 提醒去 cuecue.cn/api-key 立即轮换；本地材料不上传。

## 脚本到 verb 映射

| Verb | 走哪条路径 | 用到的脚本/函数 |
|---|---|---|
| `+ask` (主入口) | Stage 1-5 编排 | 复用：`cue_api.search_templates / rewrite / chat_stream / replay`；`sse_report.extract_reporter_content / diagnose_empty_report` |
| `+match` | 只跑 Stage 2-3 | `cue_api.search_templates` |
| `+rewrite` | 只跑 /api/rewrite | `cue_api.rewrite` |
| `+save` | Stage 6 handoff | 交给 cue-buddy 的 `generate_template` + `validate_template` + `cue_api.create_template` |

本 skill 自己**没有专用脚本**——所有原语都在 `../buddy/scripts/` 里(共享)。`cue-research/scripts/test_skill_regression.py` 只做结构/import 自检。

## 兼容性

| Platform | 状态 |
|---|---|
| Claude Code | 同 cue-buddy(SKILL.md 自动加载) |
| Codex CLI / Gemini CLI | 同 cue-buddy 加载约定，未独立验证 |
