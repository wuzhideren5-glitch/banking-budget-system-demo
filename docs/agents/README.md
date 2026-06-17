# Agent Docs Index

本目录只放当前 Agent 协作规则、issue tracker 约定和 domain 文档读取方式。历史 skill 配置、旧 agent 规划和已退休协作方案不放在这里；需要追溯时去 `archive/` 或 `.scratch/architecture-deep-clean/`。

当前 `docs/agents/` 协作文档精确清单（工作树门禁读取）：`domain.md`, `issue-tracker.md`, `triage-labels.md`。

## Reading Order

1. [`../../AGENTS.md`](../../AGENTS.md): 当前 Agent 总入口，说明 issue tracker、triage labels 和 domain docs 的位置。
2. [`domain.md`](domain.md): Agent 探索代码前如何读取 `CONTEXT.md` 和 ADR。
3. [`issue-tracker.md`](issue-tracker.md): `.scratch/<feature-slug>/` 本地 issue/PRD 约定。
4. [`triage-labels.md`](triage-labels.md): 本仓库 issue triage label vocabulary。

## Rules

- 新增或修改 Agent 协作文档时，同步更新本文精确清单；`apps/api/scripts/verify_worktree_organization.py` 会检查漏登记和过期登记。
- 当前协作事实以 `AGENTS.md`、本文和这里登记的文件为准。
- 旧 Hermes、旧团队提交流程、旧本地 issue 方案和历史 Agent 规划不得恢复成当前协作入口。
