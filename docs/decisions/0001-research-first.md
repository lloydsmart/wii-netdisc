# ADR 0001: Establish evidence before implementation

- Status: Accepted
- Date: 2026-11-17
- Decision owner: Lloyd Smart
- Basis: Current setup request explicitly limits work to repository scaffolding and research.

## Context

The project begins with an uncommitted conversation export. It contains useful
intent, corrections and candidate designs alongside unverified technical claims.

## Decision

Retain the original export locally and unchanged. Treat it as historical material.
Prepare documentation and meaningful repository checks without application code,
dummy builds, devkitPro installation or cIOS installation.

The next milestone is a source-level feasibility report with pinned upstream
references and a proposed technical ADR. Implementation, toolchain setup and
hardware experiments require a later authorised task.

## Alternatives

Starting directly from the historical implementation sketch would make technical
assumptions before tracing the relevant code. Discarding the archive would lose
user intent and the explicit correction to RetroMount's role.

## Consequences

Feasibility may be rejected or the design may change. Source observations and
experimental results must be labelled separately. Passing documentation CI does
not validate architecture, performance or compatibility.

## Evidence

Current user instructions in the setup conversation, and
[archive provenance](../../research/historical/README.md). No upstream technical
claim is accepted by this record.
