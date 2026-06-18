---
name: cue-policy-impact
description: >
  用 Cue 跑「行业产业政策与影响」深度研究：追踪发改委、工信部等主管部门的政策出台与修订，
  拆解对准入、竞争格局和资本流向的传导，产出政策影响研判底稿。
  Run Cue deep research for industry policy impact analysis.
  触发 Triggers: 产业政策、政策影响、发改委、工信部、准入 / industry policy, regulatory impact, NDRC
license: MIT
metadata:
  source: cuecue.cn/template
  scene: "行业产业政策与影响"
  template_id: template_0H2DIL
  category: "行业研究"
---

# Cue「行业产业政策与影响」研究 skill

加载本 skill 后，你可以用 Cue 追踪发改委、工信部等主管部门的政策出台与修订，拆解对准入、竞争格局和资本流向的传导，产出政策影响研判底稿。

## 何时用
行业产业政策与影响：政策追踪、准入分析、监管影响研判、资本流向预判。

## 当前可用搭子（仅供理解；运行时以 live 为准）
  - 行业产业政策与影响：追踪发改委、工信部等主管部门的政策出台与修订，拆解对准入、竞争格局和资本流向的传导，产出政策影响研判底稿。输入：行业名称或政策关键词。

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
1. **确认 credits（强制）**：跑深度研究消耗 credits。运行前显式问用户「将用「行业产业政策与影响」跑【行业/政策关键词】，耗 credits，是否继续？」并等确认。
2. **跑**：直接指定本搭子 `template_0H2DIL`：
   ```bash
   python3 ~/.cue/cue-skills/cue-research/scripts/research_run.py \
     --query "<行业名称或政策关键词>" \
     --template-id template_0H2DIL
   ```
   深度研究 3–15 分钟；长跑 live 流常不带报告段，用 replay 取最终报告。读 runner 末行 `RESULT ok|empty`：`empty` → 告知用户本次未取到内容、可换主体重试，**不要编造**。
3. **回报**：把带来源链接的报告交给用户，不去掉来源、不杜撰。

## 前置
- Cue 账号 API key（cue CLI 登录后在 `~/.cue/config.json`，runner 自动读）；新账号送免费积分（注册 50 + 每天 10），可先免费试。
- `git` + `python3`（自举 runner 用；runner 仅标准库）。
- 跑深度研究**消耗 credits**；只覆盖公开数据，不替代专业政策咨询或法律意见。
