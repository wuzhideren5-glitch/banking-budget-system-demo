Status: ready-for-agent
Category: enhancement

# 统一 AI / Agent / 智能报告 / PPT 的审核与质量反馈体验

## What to build

Unify the AI-adjacent UI surfaces so they feel calm, explainable, and enterprise-grade rather than showy. Agent suggestions, smart report inspection, smart PPT generation, AI configuration suggestions, unresolved items, and generation quality reports should share one visual language.

This slice should make AI assistance feel like a trusted part of the financial workflow.

## Acceptance criteria

- [ ] AI suggestion and recommendation surfaces use a shared calm AI card style.
- [ ] Low-confidence or unresolved items are displayed as reviewable items, not as final results.
- [ ] Quality reports for generated report/PPT outputs are visually consistent and actionable.
- [ ] Agent pivot suggestions remain distinct from regular chat text and provide clear next actions.
- [ ] AI surfaces do not expose raw SQL, raw JSON, or prompt internals to users.
- [ ] Existing generation and chat workflows remain functional.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/01-lock-global-ui-style-and-governance.md`
- `.scratch/ui-system-governance/issues/10-unify-global-shell-and-standard-pages.md`

