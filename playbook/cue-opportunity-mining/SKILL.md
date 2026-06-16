---
name: cue-opportunity-mining
description: >
  用 Cue 跑「商机挖掘」场景的深度研究：多源公开数据交叉、结论带来源。
  Run Cue deep research for the "Opportunity Mining" scenario. 
  触发 Triggers: 商机挖掘、企业尽调、产业链与研报 / business opportunity mining, lead generation
license: MIT
metadata:
  source: cuecue.cn/playbook
  scene: "商机挖掘"
  generated_from: /api/playbook
---

# Cue「商机挖掘」研究 skill

加载本 skill 后，你可以用 Cue 跑这个场景的深度研究（多源公开数据交叉、结论带来源链接）。

## 何时用
商机挖掘：企业尽调、产业链与研报、全网检索。

## 当前可用搭子（仅供理解；运行时以 live 为准）
  - 股权激励解禁日历：跟着解禁日历做业务。提前预测哪些上市公司高管即将获得股票解禁，为理财师提供精准的资金周转介入时机，抢占流动性窗口。
  - 区域优质企业名录：全量采集指定区域的优质企业名录（专精特新、高新、独角兽等资质），消除「待核实」空白，产出可用于招商与营销的名录及产业分析
  - 对公揽储商机线索：扫描区域内大额资金流动的前置信号（辅导备案、首发过会、分红预案等），锁定募资户、派息户与代发源头，产出可派单的揽储商机清
  - 对公拜访简报：扫描目标企业的工商、招投标、经营事件与司法舆情，推断潜在金融需求，产出出门前可用的拜访简报。
  - 对公客户动态雷达：扫一遍存量对公客户名单，捕捉中标、扩产、融资、被执行与舆情等公开动态，挑出今天有变化的、值得优先跟进。
  - 上市公司大额减持与大宗交易服务：穿透标的限售解禁与减持预案，测算股东持股成本与套现动力；基于大宗交易历史数据设计低冲击撮合方案，并定制合规的私行财富承接
  - 分红商机查询：筛选指定市场的现金分红事件，回溯历史分红连续性与趋势，产出覆盖名单、特征与趋势的分红商机底稿。
  - 企业跨境业务线索：锁定区域内符合境外设厂条件的 ODI 备案企业、匹配跨境融资需求，产出可落地的分层拜访策略，抢占跨境业务先机。

## 怎么跑（搭子是动态的，运行时查 live）
1. **拉本场景当前搭子**：`GET https://cuecue.cn/api/playbook`，找 `secondary_category == "商机挖掘"` 的 scene，读 `buddies[]`（每个有 `template_id`/`title`/`goal`）。若该场景当前不在返回里（临时未达展示门槛）→ 告知用户暂不可用。
2. **选一个搭子**：**委托 cue-research 的匹配逻辑**（其 `+match`/Stage-2：对 `goal` 做语义匹配、把用户的具体主体从匹配中剥离、弱命中先列 ≤2 候选确认）——不要只按字面 title 关键词裸选。取选中搭子的 `template_id`。
3. **确认 credits（强制）**：跑深度研究消耗 credits。运行前显式问用户「将用搭子 X 跑【主体】，耗 credits，是否继续？」并等确认。
4. **跑**：`python3 <cue-research>/scripts/research_run.py --query "<用户主体/问题>" --template-id <template_id>`。深度研究 3–15 分钟；长跑 live 流常不带报告段，用 replay 取最终报告。 读 runner 末行 `RESULT ok|empty`：`empty` → 告知用户本次未取到内容、可换主体/搭子重试，**不要编造**。
5. **回报**：把带来源链接的报告交给用户，不去掉来源、不杜撰。

## 前置
- Cue 账号 API key（cue CLI 登录后在 `~/.cue/config.json`，runner 自动读）。
- 跑深度研究**消耗 credits**；只覆盖公开数据，不替代尽调/法律/核保。
