# Experimental DIP adapter sizing

This configuration measures the DIP caller for the separate-service experiment.
The deliverable is source for independent review. The historical stock control
left 1,484 executable bytes and 15,232 static RAM bytes available. Adapter
occupancy and runtime stack margin await a separately approved link.
[Accepted ADR 0006](../../docs/decisions/0006-dip-adapter-sizing-link.md) ·
[Matched control and direct probe result](../experimental-dip-sizing-results.md)

## Entry and synthetic provision

The integration diff adds four objects and calls `nd_hook` at the start of
`DI_EmulateIoctl`. A zero hook result resumes the original switch with its
original arguments and initial return value of one. Before binding, only the
candidate arm selector 0xF7 enters the experiment. The fixture authority
owns the separate whole-line arm, read and output reservations. The first
arm checks the nonzero provisioned IOS, DIP, GX, slot, build, claim, epoch,
lease, fd generation and service identities before issuing a receipt. It
latches the checked extents, the original input address and all 96 arm bytes. DIP cleans the
correlated 32-byte receipt before publishing the binding. An identical
synchronised replay can preserve the unspent read only at the original
96-byte subextent, with the same fd and bound output. Identical bytes at
the second aligned half of a 192-byte reservation consume the read
opportunity as a malformed attempt. The ARMv5 word swap
selects the sole read writer before it interprets a candidate read. Foreign
input stays untouched even when a bound output makes the request recognisable.
A winning read publishes hook address, executing TID, observed fd, claim and
session before service IPC. [Admission](adapter.c) · [Integration](integration.patch)

**Synthetic fixture assumptions.** The fixture authority supplies
`nd_provision` independently of both DI calls. Its expected endpoint and
confirmed registration include the bounded path, selector, service build and
instance, worker TID/process, permitted opener and session. It also establishes
the generation of the exclusive fd namespace, readiness, the common epoch and
the actual extent and visibility of each mailbox. DIP checks the live
registration before open and control. The one-shot lifetime extends through
final handback or confirmed recovery. A fresh image starts with zero provision.
The test driver exercises two registrations with different paths, selectors,
sessions, worker builds, caller TIDs and acquired service fds. [Fixture declarations](adapter.h)

Before arm, the same authority provisions three immutable `nd_effects`
lines. Each specifies the IOS, session, claim, original open ordinal, fd
generation and unique completion address to which its guarantees apply.
A documented pre-admission failure can be represented by an explicit flag
and exact negative submission code for that operation. The default grants
no such interpretation to an error. Retirement requires the applicable
single-delivery and retirement guarantees and an observed, conflict-free
command-8 completion. Close release additionally requires zero result,
the original recorded open and fd, continuing generation and session, and
the separately established release convention. No runtime component writes
these lines for DIP. The independent journal reader owns only its lease line.
Before issue DIP takes a private snapshot for the proposed ordinal, slot and
original acquisition. It rechecks the bound flags, identities and fd generation
after submission and on completion. Only guarantees established before issue
can settle the loan. A changed or revoked contract leaves the corresponding
obligation unresolved. These synthetic facts require independent IOS57 evidence. [Transaction](transaction.c)

## Mailbox, waits and verification

The request occupies five aligned lines and the reply six. All mailbox and
journal scalars are encoded explicitly in big-endian order. Request reserves
are zero and only the observed DI fd and TID cross as caller information.
DIP reconstructs the expected prefix from private bindings when validating a
reply. The worker must check the request and own all transport, network loans
and peer evidence. The native fixture supplies response bytes through the
actual adapter input. The measured configuration calls the pinned open, ioctl,
close, queue, timer and cache interfaces. [Wire encoder and validator](mailbox.c)

One caller lends one permanent slot at a time. A slot belongs to its operation
even when a skipped control makes close the second actual submission. Capacity,
prepared buffers and INTENT precede the final ownership, lease and clock check.
NOT_ISSUED leaves the ledger and actual ordinal intact. A returned submission
and its eventual command/result have separate records. A missing open
acknowledgement can leave a service session with an unknown fd. A missing
control acknowledgement can leave the worker and mailbox live. An original
acquisition stays recorded across a blocked or ambiguous close.

DIP clips the 50-second interval to the remaining 55-second observer lease
using modular ticks and the nominal 243 MHz / 128 rate. It checks an acquired
lease snapshot twice and samples time before issue, on wake, after inspection
and at validation. One blocking receive supplies the first word while the
one-shot wake remains available. The fixture reserves a unique token for the
lease and epoch, clear of all completion addresses and the stale token.
DIP binds it to the successfully created queue and one-shot. The caller drains through nonblocking empty
and permits only an emptiness probe after eight words. A conflicting batch
cannot settle ownership. A distinct, previously identified stale timer can
prompt a fresh check. An early current wake consumes the sole timer and stops
further service issue. A lost wake can leave the caller blocked. Scheduling
can intervene after the final software sample. The independent observer owns
the 35-second checkpoint, 55-second cutoff and abandonment decision.

Only a uniquely retired control returning zero defines the 192-byte response.
DIP keeps the validation slot active through cache acquisition, private copy,
identity, time, failure and frame checks, and publication. Each tick has its
own presence and validity. Signed raw zero with the presence flag records an
observed result, including EOF. An absent result requires a zero wire word and
a clear flag. The validator checks causality, the 30/5/5/5-second worker
budgets, the original exchange deadline, terminal sequence, inner disposition
and all 28 frame bytes. A later worker cleanup failure can coexist with a
valid byte latch. A failed sole connection cannot also establish a connected
milestone. A trusted readiness or connection sample ends its phase. Each phase
completed before the first failure must admit an end strictly within its own
budget and the clipped outer deadline. Readiness and byte verification each
end one phase and start the next, so their surviving bounds apply to both.
For example, exchange starting at the outer cutoff already rules out a first
failure in cleanup, even if the verification tick is missing.

For a claimed deadline failure, DIP bounds the interval using the preceding
milestones and the earliest available completion, abandonment, publication or
trusted receipt. If the longest possible interval falls short of the phase
budget and ends before the outer cutoff, the claim is contradictory. A missing
endpoint can leave the interval indeterminate. Verification and cleanup start
coincide after the byte latch. Before the latch, first abandonment starts cleanup.

DIP samples each returned word immediately. Only after conflict-free inspection,
a command-8 match, retirement and a defined ioctl result can the matching
word's trusted observation bound worker publication. A timer observed first
bounds only its own delivery. Validation may run later or lose the lease. A
missing receipt clock leaves the acknowledgement time unknown. The separate
post-validation DIP sample supplies independent exchange and outer verdicts.
A prior trusted comparison at or beyond either deadline survives clock loss.
Clock continuity never resumes within a faulted one-shot instance.

## Journal and handback

The 48 immutable records each contain 32 wire bytes. Header bytes 6 and 7
identify the operation and proposed or issued ordinal. Each record
carries the run identity, claim, writer tick and three payload words. The
event enumeration and writes specify the payload mapping. The eight
reservation maxima, including contingency, are enforced through the bounded
one-shot path and the remaining-capacity check before each INTENT. The
reservations are eight admission, four setup, fifteen operation, eight
pre-close, three failure, eight terminal and two contingency records.
A reader acquires the contiguous commit, then verifies identity, sequence
and FNV-1a for each payload. Publication cleans payload and check before
advancing the disjoint writer commit line. [Writer](adapter.c) ·
[Exact evidence encodings](../../docs/decisions/0006-dip-adapter-sizing-link.md#bounded-dip-journal-and-static-budget)

The full decision records frame, ID, worker terminal and entry correlation,
worker samples and disposition, DIP sample and both verdicts. A shorter
decision identifies skipped, announced/unissued, pre-admission, undefined,
absent or rejected control output through its operation and loan references.
Only a validated worker failure contributes worker fields. The concluding
record commits the decision before any close INTENT. Outer loan retirement
and inner quarantine have separate dispositions. A later contradictory
delivery disputes earlier slot retirements and keeps the original acquisition
in the final ledger. The live PPC quarantine flag covers unresolved DIP
obligations and a quarantined or unaccounted-for worker after control issue.

Outer failures retain the raw tick observed at the failing event and separate
presence and validity bits. An observed zero is representable. A failed
initial lease leaves the tick present and untrusted. Failures before sampling
leave the tick absent. DIP observes a validation failure before the next lease
acquisition. That acquisition qualifies the event tick. Loss of the lease can
leave the tick untrusted and add an anomaly while the original failure and its
short decision remain correlated. The later decision sample still tests the
deadline. A journal writer's header tick dates publication.

Only DIP copies and cleans the 32-byte bound output. After preparing the status
line it reacquires ownership and checks the original IOS/DIP/GX identities and
builds, slot, claim, fd generation, session, caller, DI fd and live extent.
It rechecks the lease and time after this acquisition. The fixture assumes
the same allocation and executing context persist from these final checks
through clean, freeze and return. IOS57 scheduling or invisible reallocation
could break that assumption. Atomic handback remains unverified. The final record
references the handback sequence and freezes the writer. If output authority
or terminal capacity is lost, the caller stays pending. Safe diagnostic
failure retains any unresolved DIP loans in one-shot storage. Proof of actual
synchronous return requires independent final PPC IPC evidence and the GX
marker before cleanup. Peer correlation, safe worker termination and recovery
confirmation also require their own evidence.

## Source layout and executable economy

| Persistent declaration on the 32-bit source ABI | Bytes |
| --- | ---: |
| `nd_request`, `nd_reply` | 160 + 192 |
| Three `nd_completions`, `queue_words`, `nd_path` | 96 + 32 + 32 |
| `nd_trace`, `nd_checks`, `nd_commit`, `nd_reader` | 1,536 + 192 + 32 + 32 |
| **ADR-selected subtotal** | **2,304** |
| Fixture-owned `nd_provision` and three operation-specific `nd_effects` in DIP storage | 256 + 96 |
| Private `nd`, including the 256-byte latched provision, 96-byte arm, caller/loan/clock/journal state and internal padding | 468 |
| Three aligned word-sized admission flags | 12 |
| **Writable declaration subtotal** | **3,136** |

The selected objects, provision and effects pool each begin on a 32-byte
boundary. The three gates use ordinary word alignment. The validator also
declares a 28-byte zero frame and a read-only table of phase start, finish and
budget values.
Compiler-retained constants, literal pools, veneers, helper functions, gaps
and inter-object padding require the actual original ELF and map.

Automatic storage includes the 192-byte reply snapshot, 44-byte timing
structure, independent 64-byte prefix, 32-byte lease snapshot, 32-byte
per-operation guarantee snapshot, eight-byte candidate receipt observation,
32-byte arm receipt or status line, and
three extent pointers in allocation validation. Smaller scalars include the
received queue word, timer conversion, raw results, deadlines, checksum and
loop indices. Compiler frames, call overlap and the hooked DI thread's stack
margin remain open. Each operation uses the same submission, inspection and
retirement path. The adapter retains fixed buffers and stock memory functions
and has no heap, network client or formatting path.

## PC checks and future hosted sizing

Run the native and synthetic sizing checks with the host compiler and Python.

```sh
timeout 30s python3 -B -m unittest discover -s tests -p 'test_adapter_dip.py' -v
```

The native i386 driver supplies IOS interfaces around the three adapter C
translation units. Its cases cover foreign-page protection, split cache lines,
fd zero and reuse, conflicting deliveries, forged and undefined replies,
failure and clock masks, late handoff, terminal freeze, torn records and
capacity exhaustion. For blocked receives, blocked closure and lost final authority, the parent observes
the waiting child and ends that host fixture. The normal CI sizing test glob
includes this suite. To repeat the separate header check, use the pinned source
tar and the adapter policy with `experimental_dip_build.integrate` in a fresh
scratch tree. Run host GCC with `-m32 -std=gnu90 -ffreestanding -fno-builtin -Os
-Wall -Werror -fsyntax-only` over the three adapter C files and patched
`plugin.c`, with DIP and cios-lib include directories. A standalone
`string.h` declaring standard `memcpy`, `memset` and `memcmp` suffices on a
host lacking 32-bit libc headers. [Native fixture](../../tests/native_adapter/fixture.c) ·
[PC tests](../../tests/test_adapter_dip.py)

**Owner execution boundary.** The dedicated workflow accepts manual dispatch
only on the reviewed merged develop SHA. Both actor identities, repository
and owner, event, workflow path/ref/SHA, checkout HEAD, approved SHA and
first attempt must match. The future runner is ephemeral Ubuntu 24.04.
The approved job invokes `make experimental-adapter-sizing` unprivileged.
[Workflow](../../.github/workflows/experimental-adapter.yml) · [Input pins and evidence policy](../../scripts/experimental_adapter.py)

The paired procedure checks the selected d2x source archive and the r32 Buster
archive, verifies the patch and both postimages, and uses two fresh extractions.
The control must reproduce the historical original ELF and toolchain-prefix
normalised map hashes, 6,708 executable bytes and 246,912 RAM bytes. The
historical intermediate archive discrepancy remains recorded separately.
Executable and RAM retain the half-open regions `[0x13800000, 0x13802000)`
and `[0x13802000, 0x13842000)`. A failed link needs agreement between the
partial map, all range diagnostics and any overlap for a no-fit verdict. The
fresh patched tree must produce the complete stock and experimental object
inventory, archive and host tool. The make trace must show the pinned driver,
flags, ordered objects, libraries and output of the final link before the
range diagnostics and final-target failure summary. Assembly or object-target
failure takes precedence. Missing evidence preserves the attempted ranges.
[Historical comparison](../experimental-dip-sizing-results.md) · [Shared paired procedure](../../scripts/experimental_dip_build.py)

Only a revalidated, closed-schema JSONL journal is eligible for upload.
On a linked pair it records original ELF/map/LOAD reconciliation, section
gaps, fills, symbol deltas, recognised helper and veneer extents, locations
of annotated literal words and observations from traversal of the actual
outer hook. The inspector checks all nine selected static allocations for
size, BSS placement, alignment and overlap. Unresolved branches, compiler
inlining, indirect calls and call depth need independent review. A symbol
or branch witness alone leaves semantic acceptance open. The first run
is sizing-only. Raw maps, instructions, literal contents, binaries and
unrestricted logs stay in disposable scratch. The collector checks literal,
dependency and gap extents, stage-specific input identities, the matched
control, artifact inventories and the records supporting the outcome. Any
affirmative overflow row requires the complete-link evidence, all attempted
map extents and consistent diagnostics. An earlier object-target failure
precludes that claim. An interrupted measurement can retain raw range reports and attempted
extents. Once all reports have been corroborated, it can also retain the
affirmative rows written before interruption, even if the outcome and workflow
footer are still absent.

Independent reviewers must trace both predicates through linked instructions:

1. Follow the original open record, including fd zero, through the generation,
   session, close eligibility and pre-issue guarantee checks. Identify the
   one close submission, unique command-8 completion, signed zero convention,
   retirement and separate release decision. Trace ambiguous results to
   retained obligations and verify that every path rules out a second close.
2. Follow the claimed DI context through final output ownership, generation
   and caller validation, then through the final deadline and lease check.
   Trace both safe status handback (clean, journal, freeze and return) and
   the pending branch with untouched output and retained storage.

Mark any inlined, indirect or otherwise unresolved instruction path for
independent inspection. The two checklist entries remain manual even when
the branch traversal yields witnesses.

## Per-file provenance and publication

**Source-verified.** The reuse baseline for all original Wii NetDisc material
below is `972d7693e25f04c743017e8efccee33d3291ee99`, licensed GPL-3.0-only.

| New or shared material | Original Wii NetDisc inputs and use |
| --- | --- |
| `adapter.c`, `adapter.h` | `research/experimental_dip/netdisc.c` and `netdisc.h` for reservation classification, whole-line checks, one-use admission, receipt and publication order. This configuration implements its own journal and bindings. |
| `netdisc_gate.s` | Byte-identical original ARMv5 word swap from `research/experimental_dip/netdisc_gate.s`. |
| `mailbox.c`, `transaction.c` | New ADR 0006 C. `research/experimental_dip/netdisc_net.c` supplies precedent for the public trap argument order, command 8 and private queue/error convention. |
| `integration.patch` | Adapted from `research/experimental_dip/integration.patch`. Includes file names, hunk positions, one removed upstream declaration (`s32 ret = 1;`) and original insertions. |
| Native C and Python tests | `tests/native_dip/fixture.c`, `fixture.h` and `tests/test_native_dip.py` for the Linux process, memory routines, synthetic types and protected page. `tests/test_stock_dip.py` supplies the synthetic ELF. |
| Make, manual workflow and Python sizing | `Makefile`, `.github/workflows/experimental-dip.yml`, `scripts/experimental_dip_{build,evidence,flow,inspect}.py`, `stock_dip_build.py` and `dip_footprint.py`. Existing direct-DIP policy is the default for its callers. |

The upstream input is d2x `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`.
The selected tar SHA-256 is
`b6c8bd6cbe179a7155879fa3eace86af475fe80146b7bab9f2647f6f2303575c`.
The following assessment concerns the material in the source diff. The pinned
archive stays external. [DIP tree][dip] · [cios-lib tree][lib] · [GPL terms](../../LICENSE)

| Upstream path at the pin | Notice, use and publication assessment |
| --- | --- |
| `source/dip-plugin/plugin.c`, `plugin.h`, `ioctl.h` | Each states GPL-3.0-or-later. The single removed declaration comes from `DI_EmulateIoctl`. GPLv3 permits publication of that context with the GPL-3.0-only additions. The upstream attribution and notices stay in the original files. |
| `source/dip-plugin/Makefile`, `link.ld` | Neither has a standalone notice. The directory includes the GPLv3 text. The diff reproduces zero Makefile context and adds an original object-list line. The linker script stays solely in the pinned input. |
| `source/cios-lib/types.h`, `ipc.h`, `ios.h`, `isfs.h`, `mem.h`, `tools.h`, `syscalls.h`, `syscalls.s` | Each states GPL-2.0-or-later, allowing GPLv3. The adapter uses the declarations, full IPC record, ARM traps and cache interfaces in scratch. The diff reproduces none of their bodies. |
| `source/cios-lib/libc.c` | Stock memory functions with no file-level notice. Referenced through standard declarations. The upstream source and linked bytes stay in scratch. |
| `source/cios-lib/libwbfs/libwbfs.c`, `wiidisc.c`, `rijndael.c` | The first two specify GPLv2 and the third has conditional terms. Stock archive construction includes them. The direct result's historical map excluded these members. Actual adapter retention is a future measurement. |
| `stripios_src/main.cpp` | GPL-2.0-or-later. The host tool participates only in the existing disposable recipe. |

The publishable change consists of the original additions, the narrow
licensed diff and validated structured measurements. Binary redistribution
and retaining instruction excerpts require separate per-input review and an
owner decision. IOS57 selector collision, physical allocation identity and
permissions, receiver scheduling, timer delivery, cache ordering,
per-operation retirement, original fd release and PPC lifetime all require
independent evidence. R0 remains open. The hardware recovery gate is closed.

[dip]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin
[lib]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib
