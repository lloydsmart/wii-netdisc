# ADR 0002: Use GPL-3.0-only and develop/main

- Status: Accepted
- Date: 2026-11-17
- Decision owner: Lloyd Smart
- Basis: Explicit answers during repository setup.

## Context

The inspected disc utilities use develop/main, while the certificate renewers
use main with topic branches. At initial setup, the Wii NetDisc repository had
no commits and was on unborn main. GPL version 3 needed an explicit only/or-later choice.

## Decision

License original project contributions under GPL-3.0-only. Use develop for
integration, main for stable promotion, and short-lived topic branches.

Bootstrap with an explicitly approved initial commit on main, then create develop
from the same commit. Until that approval, leave Git refs and configuration alone.

Prepare a small CI baseline that checks the files present now. Do not introduce
build/release jobs or application manifests before there is real source to validate.

## Alternatives

A single main branch would reduce ceremony during research. The owner chose
develop/main for consistency with the disc utilities. GPL-3.0-or-later was offered;
the owner chose GPL-3.0-only.

## Consequences

The branch strategy is agreed, but branches, remotes, protection and the first
commit are not created by this decision. Release mechanics, merge method,
review requirements and private security reporting need separate decisions before
publication. No code has been copied from the reference repositories.

## Evidence

Explicit user selections on 17 November 2026 and
[the conventions review](../repository-review.md).

## Follow-up: GPG signing and bootstrap authorisation

On 17 November 2026, the owner required every commit to be signed with their GPG
key and explicitly authorised the initial commit on main, excluding the historical
JSON, followed by creation of and switching to develop. Pushing was explicitly
excluded. Verify each created commit's signature; never use an unsigned fallback.
Remote enforcement of signing remains a separate settings decision.
