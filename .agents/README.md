# Local Agent Assets

`.agents/` stores repo-local Agent assets that are part of the current
development handoff. Historical Agent plans and retired local workflow drafts
belong under `archive/` or retired `.scratch/` areas, not here.

当前 `.agents/` 顶层目录精确清单（工作树门禁读取）：`skills`。

## Current Areas

| Area | Current use |
| --- | --- |
| [`skills/`](skills/) | Repo-local skills used by Agents working in this checkout. |

## Rules

- New repo-local Agent asset areas must be listed in the exact list above.
- Retired local Agent asset areas must be moved to `archive/` or retired `.scratch/` areas and removed from this list.
- Current collaboration rules live in `AGENTS.md` and `docs/agents/`.
