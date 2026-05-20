# cue-skills

Open-source agent skills published by [Cue](https://cuecue.cn) (sensedeal).

A **skill** is a portable instruction bundle that any AI agent ([Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills), Codex CLI, Gemini CLI, …) can load to gain a new capability — without modifying the agent itself. This repo collects the skills Cue maintains for public use.

## Skills in this repo

| Skill | Purpose | Status |
|---|---|---|
| [`buddy/`](./buddy) — **cue-buddy** | Lets business experts author, validate, test, tune, and publish [Cue](https://cuecue.cn) "buddy" research templates via natural conversation. No Python / API knowledge needed; the agent talks to the Cue production API on the user's behalf. | v0.1.0 |

More skills will be added here as Cue's surface grows.

## What is Cue / What is a buddy

[Cue](https://cuecue.cn) is a **Deep Research Agent + Intelligence Sentinel** platform for high-precision finance and business workflows. It picks tools from 300+ professional data sources (A-share / HK / US equity disclosures, fund AMAC registries, business registries, court records, regulatory feeds, sell-side research, capital flow data), cross-validates findings across sources, and produces structured, source-cited reports in minutes instead of hours.

A **"buddy" (搭子)** is a research playbook for a specific scenario — corporate-credit pre-diligence, KYC screening, quarterly earnings review, etc. — defined once and reused by supplying the subject. The `cue-buddy` skill in this repo is what business experts use to author these playbooks conversationally.

See [`buddy/README.md`](./buddy/README.md) for the full skill walkthrough.

## Using a skill

Each skill folder is self-contained: an entrypoint `SKILL.md`, supporting `references/`, and scripts where applicable.

**Claude Code**: copy the skill folder into `~/.claude/skills/` or reference it via `/use-skill <path>`. See per-skill README for exact installation.

**Other agents**: load `<skill>/SKILL.md` as a system instruction. The skill's scripts are stdlib-only Python where possible.

## Contributing

Bug reports and skill suggestions: [open an issue](https://github.com/sensedeal/cue-skills/issues).

Pull requests welcome. Each skill has its own hard-rules / validator; see the skill's README for contribution guidelines.

## License

MIT — see [LICENSE](./LICENSE). Skill content is free to use, modify, and redistribute.
