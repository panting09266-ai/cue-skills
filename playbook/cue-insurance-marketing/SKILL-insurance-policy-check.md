---
name: cue-insurance-policy-check
description: >
  用 Cue 跑「保险产品条款核查」深度研究：逐条核验保险产品的保障责任、责任免除、等待期、费率与退保损失，
  并与同类产品客观对比，产出一份可向客户如实说明的条款理解底稿。
  Run Cue deep research for insurance policy clause verification.
  触发 Triggers: 保险条款、条款核查、保单审查、免责条款 / insurance policy, clause check
license: MIT
metadata:
  source: cuecue.cn/template
  scene: "保险产品条款核查"
  template_id: template_-P8x-f
  category: "保险/保险营销"
---

# Cue「保险产品条款核查」研究 skill

加载本 skill 后，你可以用 Cue 逐条核验保险产品的保障责任、责任免除、等待期、费率与退保损失，产出可向客户如实说明的条款理解底稿。

## 何时用
保险产品条款核查：保单审查、条款解读、合规核验、客户如实告知。

## 当前可用搭子（仅供理解；运行时以 live 为准）
  - 保险产品条款核查：逐条核验保险产品的保障责任、责任免除、等待期、费率与退保损失，并与同类产品客观对比，产出一份可向客户如实说明的条款理解底稿。示例输入：增额终身寿险。

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
1. **确认 credits（强制）**：跑深度研究消耗 credits。运行前显式问用户「将用「保险产品条款核查」跑【产品名称】，耗 credits，是否继续？」并等确认。
2. **跑**：直接指定本搭子 `template_-P8x-f`：
   ```bash
   python3 ~/.cue/cue-skills/cue-research/scripts/research_run.py \
     --query "<保险产品名称>" \
     --template-id template_-P8x-f
   ```
   深度研究 3–15 分钟；长跑 live 流常不带报告段，用 replay 取最终报告。读 runner 末行 `RESULT ok|empty`：`empty` → 告知用户本次未取到内容、可换主体重试，**不要编造**。
3. **回报**：把带来源链接的报告交给用户，不去掉来源、不杜撰。

## 前置
- Cue 账号 API key（cue CLI 登录后在 `~/.cue/config.json`，runner 自动读）；新账号送免费积分（注册 50 + 每天 10），可先免费试。
- `git` + `python3`（自举 runner 用；runner 仅标准库）。
- 跑深度研究**消耗 credits**；只覆盖公开数据，不替代专业投保建议或法律意见。
