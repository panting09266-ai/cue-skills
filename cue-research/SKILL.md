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

# cue-research — placeholder

Full orchestration content lands in the next commit (Task 6).
