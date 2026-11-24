# Wii NetDisc

[![CI (develop)](https://github.com/lloydsmart/wii-netdisc/actions/workflows/ci.yml/badge.svg?branch=develop&event=push)](https://github.com/lloydsmart/wii-netdisc/actions/workflows/ci.yml)
[![Licence: GPL-3.0-only](https://img.shields.io/badge/Licence-GPL--3.0--only-blue.svg)](LICENSE)
[![Status: research](https://img.shields.io/badge/status-research-yellow.svg)](research/feasibility-plan.md)

Wii NetDisc is a research-stage project exploring read-only streaming of Wii disc
images over a wired network, with a runtime that could serve multiple frontends.

**There is no Wii runtime implementation, supported build or verified hardware compatibility.**
The [PC-only TCP experiment](research/tcp_peer/README.md) exercises the test
peer and a simulated client using synthetic data on loopback.
The historical discussion favours NBD and d2x, but their suitability and integration
points still need source-level verification.

## Start here

- [Research plan and first milestone](research/feasibility-plan.md)
- [Architecture boundaries](docs/architecture/README.md)
- [Decision records](docs/decisions/README.md)
- [Contributing and local checks](CONTRIBUTING.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Security policy and private reporting](SECURITY.md)
- [Instructions for coding agents](AGENTS.md)
- [Repository conventions review and setup decisions](docs/repository-review.md)
- [Historical archive provenance](research/historical/README.md)

## Scope

Investigate ISO-backed reads first, using an existing network protocol and suitable
existing Wii frontends where practical. Direct WBFS support, discovery, caching and
RetroMount integration are later possibilities, subject to evidence.

RetroMount remains a network-independent format converter. Export publication and
game selection belong outside it.

The immediate deliverable is a feasibility report and a proposed architecture
decision, not a loader, cIOS build or console installation.

## Repository layout

| Path | Purpose |
| --- | --- |
| `docs/architecture/` | Proposed boundaries and open design questions |
| `docs/decisions/` | Decisions with explicit status and rationale |
| `research/` | Research method, plan and future evidence-backed findings |
| `research/historical/` | Provenance note; original conversation retained locally |
| `research/tcp_peer/` | PC-only diagnostic peer and simulated client |
| `tests/` | Automated PC loopback experiments |
| `scripts/` | Repository validation only |
| `.github/` | Documentation/workflow checks and pull-request guidance |

Application directories and build manifests will be introduced when an implementation
task and its architecture have been approved.

## Development workflow

Use `develop` for integration and `main` for stable promotion, with short-lived topic
branches. Bootstrap uses an approved, GPG-signed initial commit on main, with
develop created from that commit. Locally created commits must use the owner's
GPG key; GitHub-generated merge commits and Dependabot commits may use their own
verified signatures. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Copyright (C) 2026 Lloyd Smart and contributors.

Original Wii NetDisc contributions are licensed under the GNU General Public
License, version 3 only: **SPDX-License-Identifier: GPL-3.0-only**.
See [LICENSE](LICENSE) for the complete terms, including the warranty disclaimer.

The historical conversation and any third-party material retain their own rights
and notices. Their presence does not relicense them as Wii NetDisc code.
