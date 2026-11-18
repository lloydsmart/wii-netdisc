# Architecture boundaries

Status: **candidate boundaries for investigation, not an implemented design**.

The historical user direction is ISO-first streaming over wired Ethernet,
preferably using NBD and d2x, with support for multiple frontends. The precise
integration and feasibility remain open. See
[historical provenance](../../research/historical/README.md).

| Area | Candidate responsibility | Must not absorb |
| --- | --- | --- |
| Frontend | Game selection, endpoint/export configuration and launch request | Networking inside RetroMount; frontend-specific runtime policy |
| Wii runtime integration | Disc-read routing, image semantics and lifecycle/error translation | UI or server-side format conversion |
| Read-only transport | Bounded byte-range reads, protocol negotiation, timeouts and disconnect handling | Wii partition interpretation or game catalogue |
| Server/export layer | Publish authorised image representations through a standard protocol | Wii runtime patches or conversion logic embedded in the protocol |
| Optional RetroMount | Transform between supported image representations | Network service, Wii-aware game catalogue or orchestration |

These are conceptual separations, not a choice of processes, binaries, C APIs or
IOS modules. No API names or directory stubs are reserved yet.

## Questions that determine the design

- Where does the actual d2x disc-read path permit a backing-store change?
- Can the intended IOS execution context use networking throughout gameplay?
- What are the offset units, alignment requirements and decryption responsibilities?
- What code/data memory, buffer ownership, scheduling and lifecycle limits apply?
- How should failures, IOS reloads, reset and concurrent game networking behave?
- Which NBD negotiation mode and read-only subset can interoperate with a standard server?
- What latency and throughput are required, and how would they be measured?

The [initial R0-01/R0-02 source investigation](../../research/r0-01-r0-02-source-investigation.md)
maps candidate disc-read boundaries and IOS socket clients, with lifecycle and
privilege gaps still open. NBD has not been investigated. The
[research plan](../../research/feasibility-plan.md) defines the remaining evidence
needed before selecting DIP integration, a separate module or another approach.
