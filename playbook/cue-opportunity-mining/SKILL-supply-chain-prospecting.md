---
name: cue-supply-chain-prospecting
description: >
  用 Cue 跑「产业链上下游拓客」深度研究：从一家核心企业出发，顺着客户、供应商与招投标关系，
  挖出上下游可拓展名单，给出每家切入点和可能的金融需求。
  Run Cue deep research for supply-chain upstream/downstream B2B lead generation.
  触发 Triggers: 产业链拓客、上下游拓客、供应链获客、对公拓客 / supply chain leads, B2B prospecting
license: MIT
metadata:
  source: cuecue.cn/template
  scene: "产业链上下游拓客"
  template_id: template_AKRtET
  category: "银行/商机挖掘"
---

# Cue「产业链上下游拓客」研究 skill

加载本 skill 后，你可以用 Cue 从一家核心企业（链主）出发，顺着客户、供应商与招投标关系，挖出上下游可拓展对公名单。

## 何时用
产业链上下游拓客：供应链获客、对公拓客。

## 当前可用搭子（仅供理解；运行时以 live 为准）
  - 产业链上下游拓客：从一家核心企业出发，顺着客户、供应商与招投标关系，挖出上下游可拓展名单，给出每家切入点和可能的金融需求。输入: [链主主体名称]，可选: [关注的产业链环节]。信源: 年报前五大客户/供应商、招投标公示、合作公告、产业链数据。边界: 仅覆盖公开可见的上下游关系，非链主完整名单。

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
1. **确认 credits（强制）**：跑深度研究消耗 credits。运行前显式问用户「将用「产业链上下游拓客」跑【链主主体】，耗 credits，是否继续？」并等确认。
2. **跑**：直接指定本搭子 `template_AKRtET`，无需拉场景选搭子：
   ```bash
   python3 ~/.cue/cue-skills/cue-research/scripts/research_run.py \
     --query "<链主主体名称>" \
     --template-id template_AKRtET
   ```
   （用上一节就绪的 runner 路径；已装 cue-skills 则用你本地的 `cue-research/scripts/research_run.py`）。深度研究 3–15 分钟；长跑 live 流常不带报告段，用 replay 取最终报告。 读 runner 末行 `RESULT ok|empty`：`empty` → 告知用户本次未取到内容、可换主体重试，**不要编造**。
3. **回报**：把带来源链接的报告交给用户，不去掉来源、不杜撰。

## 前置
- Cue 账号 API key（cue CLI 登录后在 `~/.cue/config.json`，runner 自动读）；新账号送免费积分（注册 50 + 每天 10），可先免费试。
- `git` + `python3`（自举 runner 用；runner 仅标准库）。
- 跑深度研究**消耗 credits**；只覆盖公开数据，不替代尽调/法律/核保。
