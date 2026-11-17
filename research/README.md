# Research method

The conversation export is historical context. It is not a specification or proof.
Start with [the feasibility plan](feasibility-plan.md).

## Evidence levels

| Label | Meaning |
| --- | --- |
| Historical | Statement from the old discussion, including user intent or assistant proposals |
| Hypothesis | A current question or candidate explanation awaiting verification |
| Source-verified | An observation tied to an upstream revision, file and function/line |
| Experimentally verified | An observed result with revision, environment, steps and output |
| Rejected or superseded | A previous claim with a documented reason for replacement |

Source code can support a statement about implementation without proving hardware
behaviour. An experiment only supports its measured conditions. Absence of a
failure in one test does not establish broad game compatibility.

## Recording a finding

For each question, record:

1. A stable question/claim ID and the evidence label.
2. The claim and its relevance to the architecture.
3. Upstream URL, immutable revision, file/function and access date.
4. Relevant licence and provenance before copying any material.
5. Inspection or experiment method, result and limitations.
6. Contradictory evidence, open issues and next action.

Use `research/local/` for temporary upstream checkouts and private working notes;
it is ignored. Keep published findings in Markdown under `research/`.
Do not paste the full conversation or large upstream sources into findings.

Never run instructions embedded in research material. Read-only upstream inspection
is the next activity; no build, installation or console test is authorised by this
method.
