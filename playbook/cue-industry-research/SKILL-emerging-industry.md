---
name: cue-emerging-industry
description: >
  用 Cue 跑「新兴产业研究」深度研究：面对陌生赛道一键梳理行业天花板、竞争格局与核心商业模式，
  映射IPO/并购中常见的合规风险与法律争议点。
  Run Cue deep research for emerging industry analysis.
  触发 Triggers: 新兴产业、赛道研究、商业模式、IPO合规 / emerging industry, sector analysis, business model
license: MIT
metadata:
  source: cuecue.cn/template
  scene: "新兴产业研究"
  template_id: template_BbE7-1
  category: "前沿产业研究/行业研究"
---

# Cue「新兴产业研究」研究 skill

加载本 skill 后，你可以用 Cue 一键梳理陌生赛道的行业天花板、竞争格局与核心商业模式，同时映射 IPO/并购中常见的合规风险与法律争议点。

## 何时用
新兴产业研究：赛道扫描、商业模式分析、IPO/并购合规预判。

## 当前可用搭子（仅供理解；运行时以 live 为准）
  - 新兴产业研究：面对陌生赛道一键梳理行业天花板、竞争格局与核心商业模式，映射IPO/并购中常见的合规风险与法律争议点。输入：行业/赛道名称。

## 准备 Cue runner（首次用时，幂等）
本 skill 不自带脚本，靠 Cue 开源 runner 跑研究。先确认 runner 是否就绪：
- 若你已安装 `cue-skills`（或本 skill 来自整包发布）→ 直接用其中的 `cue-research/scripts/research_run.py`，**跳过本节**。
- 否则克隆开源仓（含 cue-research + cue-buddy 全套依赖），**有则更新、无则克隆**（GitHub 不通走镜像）：
  ```bash
  if [ -d ~/.cue/cue-skills/.git ]; then
    git -C ~/.cue/cue-skills pull --ff-only
  else
    git clone https://github.com/sensedeal/cue-skills ~/.cue/cue-skills \
      || git clone https://gitee.com/sensedeal/cue-skills ~/.cue/cue-skills
  fi
  ```
  之后 runner = `~/.cue/cue-skills/cue-research/scripts/research_run.py`。需 `git` + `python3`（runner 仅用标准库）。

## 怎么跑
1. **确认 credits（强制）**：跑深度研究消耗 credits。运行前显式问用户「将用「新兴产业研究」跑【赛道/行业名称】，耗 credits，是否继续？」并等确认。
2. **跑**：直接指定本搭子 `template_BbE7-1`：
   ```bash
   python3 ~/.cue/cue-skills/cue-research/scripts/research_run.py \
     --query "<赛道/行业名称>" \
     --template-id template_BbE7-1
   ```
   深度研究 3–15 分钟；长跑 live 流常不带报告段，用 replay 取最终报告。读 runner 末行 `RESULT ok|empty`：`empty` → 告知用户本次未取到内容、可换主体重试，**不要编造**。
3. **回报**：把带来源链接的报告交给用户，不去掉来源、不杜撰。

## 前置
- Cue 账号 API key（cue CLI 登录后在 `~/.cue/config.json`，runner 自动读）；新账号送免费积分（注册 50 + 每天 10），可先免费试。
- `git` + `python3`（自举 runner 用；runner 仅标准库）。
- 跑深度研究**消耗 credits**；只覆盖公开数据，不替代专业投行/法律意见。
