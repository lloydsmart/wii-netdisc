# ADR 0004: Authorise deterministic PC-only diagnostic fixture simulation

- Status: Accepted
- Date: 2026-11-26
- Decision owner: Lloyd Smart
- Basis: Explicit owner approval under [ADR 0001](0001-research-first.md). Implementation authority takes effect after review and merge of this record.

## Context

Direct DIP remains the candidate caller. The stock executable has **1,484 bytes
of experimentally verified trailing headroom**. The fit and IPC investigations
leave request ownership, deadline enforcement, one-shot arming and independent
observation unresolved. A modified link remains deferred. [Stock measurement](../../research/d2x-build-baseline.md) ·
[Direct-DIP fit study](../../research/direct-dip-tcp-probe-fit.md)

## Decision

This task records the decision in documentation only. After review and merge,
a subsequent PC-only task may create a small deterministic Python reference
model, focused standard-library unit tests, minimal supporting documentation
and integration of those tests into existing CI. Reuse the existing Python and
`unittest` infrastructure where practical. Drive events and time explicitly.
Exclude external dependencies, real concurrency, a general-purpose event
framework, IOS emulation, sockets, sleeping, wall-clock timing, toolchains and
hardware from the simulation. Existing repository validation remains permitted.

### Model and evidence boundaries

Model one armed diagnostic attempt, one outstanding network request slot, one
acquisition ledger, one independent observer and an external recovery decision.
The test driver controls the injected ground truth. DI can act on submission
returns and delivered replies. GX can act on receipts, wrapper returns and
independently correlated IPC completion evidence. The observer sees its own
clock and the committed records it actually captures. For example, when a
resource manager opens a resource and the completion is lost, only the driver
knows acquisition succeeded. The ledger must distinguish unresolved ownership,
known ownership and confirmed release for each acquisition.

### Required scenarios and invariants

- **Ownership.** Inject blocked submission, successful acquisition with lost
  completion delivery, and descriptor allocation failure after resource-manager
  success. Exercise late open, receive and close completions, operations that
  never complete, and ambiguous close disposition followed by handle-number
  reuse. Retain every resource and buffer while it may be in use. Match close
  and release evidence to the original acquisition. Forbid guessed, conflicting
  and duplicate closes.
- **Deadlines.** Exercise both delivery orders for completion and expiry, early,
  stale and duplicate timer events, completion exactly at the deadline, queue
  exhaustion, bounded clock wrap and an unbounded observation gap. A timer
  notification prompts a phase and elapsed-time check. It cannot establish
  expiry by itself. Equality misses the deadline. An unbounded gap cannot
  establish timeliness. Preserve the 30-second bring-up budget and the single
  absolute five-second exchange deadline across partial sends and receives.
  Reconnection is forbidden.
- **Arming.** Exercise lost and ambiguous arm receipts. Withhold dispatch if
  receipt is uncertain or preservation of at least one of the two request
  discriminators (tag and reserved output identity) cannot be established.
  Ordinary reads follow their normal path and preserve the arm. A valid claim
  spends it once. A recognisable malformed read also spends it and is rejected
  before media access. Reject recognisable duplicates after either claim,
  including a valid read following a malformed one.
- **PPC handback.** Inject premature wrapper return during both arm and read,
  including an outstanding internal IPC request and its associated storage
  loans. Ambiguous handback retains those loans and blocks further unsafe
  dispatch, progression to the pre-cleanup marker, rearming and normal game launch.
- **Observation and recovery.** Interrupt trace publication, present stale or
  incomplete records, omit the pre-cleanup marker, and freeze observation or
  the display. Exercise an independent watchdog decision. Model recovery
  initiation separately from confirmation that the old IOS instance and its
  relevant I/O have ended. Initiation alone cannot establish safe termination.

### Verdicts

Preserve the first failure. Score exchange verification, the baseline verdict
and safe termination separately, using only the evidence available for each.

| Result | Required evidence in the model |
| --- | --- |
| Exchange verified | Caller verifies the complete reply before expiry and the peer record agrees. Latch the result before cleanup and retain it through any later cleanup failure. |
| Baseline pass | Verified exchange, matching instance/build/tag, bring-up within budget, safe handback for both PPC calls and matching synchronous DI return before the independently captured GX pre-cleanup marker. |
| Attributable baseline failure | Independent evidence of intended caller entry before cleanup, a demonstrated network error, deadline miss or bad reply, and independently checked listener and wired controls. |
| Probe never ran | GX positively records skipped dispatch or matching rejection before network entry. An arm receipt or silent peer cannot establish this verdict. |
| Indeterminate | Missing entry without positive rejection, missing required evidence, wrong instance, failed controls or uncertain return/marker ordering leaves the affected claim indeterminate. |
| Safe termination | Account for all outstanding I/O and loans through confirmed cleanup or independently confirmed end of the old instance and relevant I/O. Record cleanup failures separately. A hang, watchdog cutoff or recovery request alone cannot establish release. |

### Acceptance criteria

Require deterministic tests for every material scenario above. Tests must drive
the reference model and assert observable transitions and outcomes without
duplicating its decision logic. Check participant access to evidence and all
ownership, timing, arming, handback and observation invariants, including at
most one intended claim. Existing repository checks must continue to pass.
Require independent review of the implementation and its assumptions.

## Alternatives

The model may compare outer and inner DI hooks, terminal quarantine policies,
independent watchdog cutoffs, trace publication and capture mechanisms, and
recovery initiation and confirmation events. Separate five-second connection
and cleanup bounds are provisional. Document each choice as an assumption or
parameter. Adopting any of these choices on Wii requires a separate decision.

## Consequences

Passing tests establish consistency of project-owned transitions only for the
modelled event sequences. IOS57 ABI, permissions, asynchronous submission,
scheduling, cache coherency, physical memory mapping, executable fit and safe
hardware recovery all require independent evidence. R0 remains open.

This exception excludes experimental DIP or GX implementation, modified ARM or
PPC compilation, upstream source changes, toolchain or dependency installation,
proprietary firmware or console data access, cIOS packaging or installation,
Wii hardware access, NBD client or server implementation, a production
asynchronous IPC subsystem and repository settings changes. [ADR 0003](0003-stock-dip-build-strategy.md)
governs stock compilation exclusively. The hardware recovery gate remains closed.

## Evidence

Owner decision of 26 November 2026, the [baseline verdict definitions](../../research/ios57-baseline-plan.md)
and the [IPC ownership and fixture investigation](../../research/ios-ipc-ownership-and-fixture.md).
