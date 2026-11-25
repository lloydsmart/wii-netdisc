# Feasibility plan

Status: **in progress**.

See the [disc-read and IOS networking note](r0-01-r0-02-source-investigation.md)
for the R0-01 read path. The [IOS57 v5918 wired TCP lifecycle note](r0-02-r0-03-ios57-v5918-network-lifecycle.md)
traces the GX cleanup helper and game-side cleanup and compares both R0-02/R0-03 connection owners.
Neither owner's access after handoff is verified. The original IOS encrypted-read
internals, the transport placement decision and the R0 exit criteria remain open.

## Objective

Determine whether a reusable Wii runtime could provide read-only disc access over
wired Ethernet using NBD and d2x. Preserve the historical preference for standard
protocols, existing frontends and ISO-first scope, while allowing an evidence-based
no-go result or a different architecture.

## Milestone R0: Source-level feasibility

| ID | Question | Required evidence |
| --- | --- | --- |
| R0-01 | Where can disc reads use an alternative backing store? | Pinned d2x revision; traced call path, offsets, alignment and errors |
| R0-02 | Is networking available in the relevant IOS context? | Source dependencies, lifecycle, privilege and concurrent-use constraints |
| R0-03 | Where could the transport live? | Compare DIP integration and a separate module against memory, IPC and scheduling evidence |
| R0-04 | Can a bounded read-only NBD client interoperate? | Current primary protocol specification and server source; negotiation, read semantics and failure handling |
| R0-05 | What are the legal/provenance and toolchain prerequisites? | Upstream licence inventory, source provenance and build requirements, without installing tools |
| R0-06 | What would a safe experiment measure? | Proposed synthetic-data read test, failure cases, resources and success criteria |

Read the historical archive first for intent, then independently inspect primary
sources. Pin exact revisions and record links; old chat citations are leads only.
Upstream build scripts remain outside R0 except for the two PC-only stock DIP
builds scoped by [ADR 0003](../docs/decisions/0003-stock-dip-build-strategy.md).
That task may supply measurements for R0-03 and R0-05 after review and merge
of the decision and separate approval for runner execution.

### Exit criteria

- A written source map and claim ledger covering R0-01 through R0-06.
- Explicit supported findings, unknowns and contradictions.
- A proposed ADR comparing viable approaches, or explaining a no-go conclusion.
- An implementation estimate expressed as uncertainty and dependencies, not a promise.
- An owner review before any implementation or toolchain/hardware task begins.

## Candidate later proof of concept

This is a proposal, **not current authorisation or a demonstrated capability**:

1. Validate bounded, read-only byte-range requests against synthetic server data,
   including truncation, disconnects, invalid offsets and timeouts.
2. After a separate hardware plan and explicit approval, assess one authorised raw
   ISO over wired Ethernet from a standard, unmodified NBD server.
3. Record the exact environment, observed behaviour and limitations.

Direct WBFS support, game/export discovery, GUI work, RetroMount integration and
advanced caching are outside that first proposed experiment. Do not set performance
or compatibility promises before measurements.
