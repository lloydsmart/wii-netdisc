# Architecture decision records

Use numbered records for decisions with lasting consequences. Each record should
state status, date, context, decision, alternatives, evidence and consequences.

Statuses are **Proposed**, **Accepted**, **Rejected** or **Superseded**. Preserve old
records and link to replacements; never silently rewrite a historical decision.
Acceptance records an explicit owner decision, not an agent's confidence.

| Record | Status | Subject |
| --- | --- | --- |
| [0001](0001-research-first.md) | Accepted | Research scope and evidence gate |
| [0002](0002-repository-workflow.md) | Accepted | GPL-3.0-only and develop/main workflow |
| [0003](0003-stock-dip-build-strategy.md) | Accepted | Make interface and PC-only stock DIP measurement |
| [0004](0004-pc-only-fixture-simulation.md) | Accepted | Deterministic PC-only diagnostic fixture simulation |
| [0005](0005-experimental-dip-sizing-link.md) | Accepted | PC-only sizing of one complete experimental direct-DIP TCP probe |

Technical architecture is still proposed. Create a new ADR when the feasibility
research can support a concrete decision.
