# Experimental direct-DIP sizing

**PC-only sizing implementation, awaiting independent verification and separate execution approval.**
This is the PC-only link experiment selected by [ADR 0005](../../docs/decisions/0005-experimental-dip-sizing-link.md).
Its control is the [measured stock DIP](../d2x-build-baseline.md). R0 remains
open. The hardware recovery gate is closed.

## Entry and fixture contract

The [patch](integration.patch) adds three objects and calls `nd_hook` at the
start of the outer ioctl dispatch. Zero resumes the original switch with its
original default status of one. The hook returns one on success or a negative
diagnostic status for a handled failure. It never forwards a claimed read.
[Gate, receipt and trace writer](netdisc.c) · [Fixture layouts and event IDs](netdisc.h)

**Source-verified collision review.** GX uses 0x8D for unencrypted reads. Its
WDVD controls include 0xF4–0xF6, 0xF9, 0xFA and the Hermes 0xFE. The pinned
d2x header assigns 0xF0–0xF6, 0xF9, 0xFA, 0xFE and 0xFF. The outer switch
forwards its default to base DI. The inner switch derives its selector from
the high input byte, handles commands including fragment-list installation
and custom DVD commands, and forwards its default to the base handler.
**Sizing choice.** Neither switch nor the WDVD definitions assigns **0xF7**.
Use it only as the local fixture arm selector. The opaque base command space
and whether both live envelopes reach this hook on IOS57 v5918 remain unknown.
[GX definitions and read][gx] · [d2x command table][commands] · [Both dispatch paths][dispatch]

The synthetic fixture below is a design input. All multibyte fields are
big-endian. Its instance 1, slot 249 and two build IDs identify this fixture
profile. The gate and journal require freshly initialized static storage.
An actual run would need independently established instance, slot
and linked build identities. There is one opportunity to arm per loaded image.

| Call | Input | Live output |
| --- | --- | --- |
| Arm | Exactly 96 aligned bytes. Twelve u32s specify version 1, instance, slot, DIP and GX build IDs, expected IOS-side fd, command 0x8D, length 32, word offset, local IPv4, peer IPv4 and port. Follow with eight tag bytes, sixteen challenge bytes and six zero words. | Exactly one exclusively reserved, aligned 32-byte line. The receipt contains the tag, instance, slot, both build IDs, observed fd and observed output address. Correlate the arm trace with the intended read tuple and endpoint. |
| Read | Exactly eight words. The first three are 0x8D000000, 32 and the bound word offset. Words 3 and 4 contain the tag. Words 5–7 are zero. | The same live line. After a valid entry, handback contains the tag, instance, terminal sequence, raw status, first failure, quarantine flag and TID. |
| Observer | Start before arm. Supply the reader-owned line described below. Correlate the external peer accept, endpoints, 24-byte frame and connection ID. | Independent capture also needs both final PPC IPC completions and the actual pre-cleanup marker. |

### Input reservations and admission

Before the first ioctl, the native driver supplies the base and exclusive
end of two separate, whole-line-owned allocations in the DIP-local
`nd_input_provision` descriptor. It obtains their bounds from the storage it
owns. In the native tests each allocation is 96 bytes. The probe requires at
least 96 bytes for arm and 32 for read. A fresh image has a zero provision
and cannot accept an arm. No request field sets the provision. A successful
arm latches a private copy of the checked bounds for the life of the instance.
[Provision layout](netdisc.h) · [Native driver](../../tests/native_dip/fixture.c) · [Pinned MEM1 bounds][mem1]

1. Before binding, the first 0xF7 spends the arm opportunity. Check both
   reservations for nonzero, line-aligned MEM1 bounds and sufficient length,
   and for separation from one another, the live output and the ioctl
   envelope. Check that all 96 arm bytes lie in the arm reservation.
   Synchronize the full lines, validate the private snapshot and bind the
   tuple, tag, input reservations and exclusive output. A malformed arm
   produces a terminal rejection without binding.
2. After binding, examine only the input start and output identity to classify
   the request. An input starting in either reserved range or an output at the
   bound address identifies a candidate. Every call with neither identity
   returns to stock with its input cache untouched and the claim preserved.
   Foreign bytes, including a copy of the exact tag, have no authority.
3. A 0xF7 replay from the arm reservation with the bound fd and output, valid
   extents and byte-identical synchronized contents preserves an unspent read.
   Every other candidate claims the read once. Bound output with foreign input
   rejects terminally without reading or synchronizing any of the foreign bytes.
4. To enter an exchange, require a 32-byte read from the read reservation,
   alignment, separate live buffers, the bound output and fd, and all eight
   expected words, including the tag. For each input synchronization, check the
   declared length against the bytes remaining to the trusted exclusive end.
   Round the original start down and the original end up. Check that this
   entire interval remains owned and clear of the live envelope before issuing
   the cache call. Malformed candidates reject before media or network access.
   Recognisable duplicates cannot enter again. The one-use ARMv5 `swp`
   claims return immediately and no gate is held across blocking work.
   [Admission and range checks](netdisc.c) · [One-use primitive](netdisc_gate.s)

**Fixture precondition.** GX must withhold the synthetic read unless its receipt
and arm handback are verified and at least one reserved allocation identity
will reach the outer hook. The native descriptor represents independently
established ownership in the sizing experiment. Actual GX allocation, physical
identity after PPC-to-IOS translation, alias exclusion, coherent handoff and
exclusive lifetime through completion or confirmed recovery remain target
dependencies. The observer also needs an independently established mapping of
the trace and its own line. [Fixture lifetime and mapping investigation](../ios-ipc-ownership-and-fixture.md)

**Source-verified.** Libogc's `IOS_Ioctl` flushes its PPC input. StarStruck's
`IpcHandler` validates the address and invokes `DCInvalidateRange` before
delivering a PPC ioctl. For small ranges that function rounds the base down
before adding the byte count. For a 32-byte input at line offset 16, this
calculation covers only the first line. A tag at input offsets 12–19 spans
both. The d2x outer ioctl descriptor supplies an address and length. These
sources do not establish coherent delivery of every candidate tag to the
IOS57 outer hook. [PPC handoff][ppchandoff] · [Public IOS dispatch][ppcdispatch] ·
[ARM invalidation][invalidate] · [Outer envelope][envelope]

**Experimentally verified on PC.** A malformed read starting at offset 16
refreshes both owned lines containing its split tag and spends the claim.
The next valid-looking read makes zero submissions. The native driver also
makes an ordinary input page inaccessible during the hook call. Its preceding
dirty byte survives stock forwarding and bound-output rejection. The hook
leaves that page untouched in both cases. The completed Python simulation
remains evidence of the admission contract it modelled before this refinement.
[Native regressions](../../tests/test_native_dip.py) · [Owner decision](../../docs/decisions/0005-experimental-dip-sizing-link.md#entry-and-one-use-admission)

## Network path and ownership

[The measured network module](netdisc_net.c) submits directly from the
recorded outer-hook TID. INTENT announces a candidate after argument and
buffer preparation. Its header carries the number of actual attempts already
issued. Its payload carries the proposed completion address and, in bits
16–23, 8–15 and 0–7, the next attempt, resource and acquisition respectively.
After publishing INTENT, DIP synchronizes the lease and samples the clock.
A failed final check produces NOT_ISSUED with the same payload. The attempt
count, active loan, close history and resource disposition stay as they were.
A later eligible cleanup can use the unissued slot. On a passing check only
local accounting and trap selection precede the call. SUBMITTED records the
issued ordinal and the trap's raw return. An INTENT with no later record
leaves issuance uncertain for the external observer. Arguments and frame buffers have
static lifetime. None of the async calls borrows GX or stack storage.

| Sequence | Operation-specific evidence |
| --- | --- |
| Bring-up | Open NCD mode 0. Ioctlv 7 uses zero inputs and one 32-byte output. Require IPC success, service word zero and status 3 for wired. Busy status 1 may retry. Close NCD. Open SO and KD mode 0. KD ioctl 6 has an empty input and 32-byte output. Retry service −29, accept zero or −15, then close KD. SO ioctls 31 and 16 start the service and poll the host address. Accept only the bound unicast IPv4, including high-bit addresses. |
| Connection | SO ioctl 15 uses three words for IPv4, stream and protocol zero. Record the returned socket in the SO namespace. Ioctl 4 makes one connect with a 36-byte control containing an eight-byte IPv4 address. |
| Exchange | Ioctlv 13 sends two inputs, the outstanding bytes and a 40-byte connected-send control. Ioctlv 12 takes the eight-byte socket/flags input and two outputs, scratch and a null, zero-length address. Positive counts must fit the remaining frame. Raw SO −6 and −27 may retry within the same exchange. Zero receive is premature EOF. Compare all 24 echoed bytes and decode the final nonzero u32 on the big-endian target. |
| Cleanup | Socket ioctl 3 carries four bytes on the originating SO handle. Close eligible KD, SO and NCD process descriptors once. Ambiguous closes retain their original acquisition and dependencies. |

**Source-verified interface evidence.** HAI supplies ARM argument layouts.
Libogc supplies KD service semantics and startup ordering. Both NCD clients
submit the 32-byte output without decoding the wired field. Dolphin's
`NetNCDManageDevice::IOCtlV` writes common status at byte 0 and link type at
byte 4. Its `ConnectionSettings::LINK_WIRED` equals 3. This public emulator
behaviour is the basis for the decoder. IOS57 semantics still need observation.
[ARM client][hai] · [PPC startup][ogc] · [NCD ioctlv][ncd] · [Link statuses][linkstatus]

The pool has 64 distinct 32-byte `ipcmessage` objects. Compile-time assertions
check a 32-bit record layout, pool alignment, stride through element size and
the 2,048-byte extent. Each attempted trap permanently spends one slot. One
active operation owns all transfer storage until handoff. Before admission the
remaining network budget must cover this submission and one close per known
resource, adjusted for the resource the operation can acquire or close. Across
24 single-byte sends and 28 single-byte receives, required setup and cleanup
would exceed 64. Budget exhaustion therefore has a reachable failure path.

A private eight-word queue receives slot addresses and four disjoint phase
timer words. A nonblocking bounded scan through empty precedes each submission
and each result handoff. Detect a current word, old slot, unknown address,
multiple arrivals and never-armed timer. A valid old wake prompts a clock
check. Check command 8 and synchronize the completion before using its signed
result. SO host ID uses the same bits as an unsigned IPv4 address. Socket and
process fd zero are valid. HAI and libogc's pinned `net_socket` clients
interpret the returned SO_SOCKET result as a socket only on nonnegative
success. Under the fixture's retirement assumption, a uniquely matched,
command-8 negative result for ioctl 15 records failed acquisition, retires
that loan and permits the already-owned SO fd to close. A bare trap failure, a possibly live acquisition,
a duplicate process fd, an uncertain close or an untrusted queue pins the
resources. A matched late result can establish a known fd or confirmed release
before the deadline failure is reported. Terminal quarantine leaves all
potentially live producers, handles, backing and control lines in place.
[HAI net_socket][haisocket] · [libogc net_socket][ogcsocket] · [ARM declarations and reply layout][ipc] · [Open and queue caveats](../ios-ipc-ownership-and-fixture.md#ipc-01--what-an-arm-caller-can-infer-from-a-return)

For each submission the caller cleans the prepared message, path if used,
vectors, controls and whole-line-owned scratch/output. Following a matched
receive, `receive_handoff` synchronizes the returned range and copies exactly
the positive count into the private frame before releasing the active slot.
A one-byte completion takes the same path. The target must deliver the exact
caller address, retire access before consumption and make producer writes
visible. An empty queue after inspection also needs single-consumer ordering,
no later conflicting producer, and reliable timer retirement before queue
destruction. The public reimplementation can drop delivery. An empty queue
alone cannot prove retirement. [Stock cache calls][wbfs] · [Queue and release evidence][ownership]

## Phase clock and publication

One 30-second bring-up, one five-second connection, one absolute five-second
exchange and one five-second cleanup use trap 0x15 and unsigned subtraction.
DIP latches the cleanup epoch on the first verification or abandonment.
A matching late completion may settle ownership while the same five-second
window continues to elapse. Cleanup arms its wake for the remaining interval
and checks the original epoch before each eligible operation. At expiry DIP
quarantines remaining obligations. Equality is late. The calculation uses a nominal 243 MHz / 128 counter and
rounds fractional tick budgets down. The d2x prototype takes a timer argument.
The probe passes zero. HAI and StarStruck support the interpretation that the
trap reads the global raw counter independent of that argument. Timer creation
uses microseconds. A timer word alone never changes the verdict. Polling yields
when there is no completion. A blocked submission can stall before any return
or timer processing. The final sample establishes the observed time. Scheduling,
trap entry and the duration of a blocked call remain outside that guarantee.
[Clock source comparison and hardware-rate assumption](../ios-ipc-ownership-and-fixture.md#ipc-02--clocks-and-the-four-different-end-times)

For sizing, the observer can supply an aligned, reader-owned `nd_reader`
line. Words 0–4 contain a live flag of one, instance, two tag words and the
55-second absolute cutoff in seconds. Prepare the identity before setting
live. The independently clocked observer must clear live by the cutoff and
never republish it in this instance. DIP synchronizes and checks the line on
clock samples. An absent or invalid lease or a modular gap at least half the
counter range leads to quarantine. This bounds possible missed wraps only if
the observer runs, enforces the bound and the line stays coherent across a
stall. A stale live flag would invalidate timeliness. The observer's 35-second
progress checkpoint, hard cutoff, external capture and recovery are outside DIP.

| Static allocation | Bytes before linker padding |
| --- | ---: |
| 64 full completions | 2,048 |
| 320 immutable trace records | 10,240 |
| One FNV-1a check word per record | 1,280 |
| Writer commit line and reader-owned line | 32 each |
| Three open paths | 96 |
| Control, vector line, service output, transfer scratch, assembled frame, queue backing | 64 + 32 + 32 + 32 + 32 + 32 |
| Input provision and latched input bounds | 16 + 16 |
| Other state | Copied 96-byte arm, run state, bindings, timer IDs and masks, gate claims, counters and constants. Inventory their linked symbols and padding. |

The pool, records, check words and two publication lines total 13,632 bytes
in the source layout. Independent review counted another 572 bytes of
declarations before the input reservation change, for a subtotal of 14,204.
The four-word input provision and its four-word latched copy add **32 bytes**,
bringing nominal DIP static declarations to **14,236 bytes** before padding
and retention changes. The fixture owns the input payload allocations outside
DIP. Temporary validation snapshots use automatic storage. Only a separately
approved link can establish static spans and compiler-visible frames.

Each 32-byte trace record starts with sequence, instance, eight-byte tag and
clock sample. Four bytes identify event, phase, operation and attempt. Two
u32 payload words follow. The unique attempt selects the pool element and
the acquisition serial selects the ledger entry. Transfer events encode
1–8 bytes in the event code and keep them in wire order. Concatenate chunks
by attempt and sequence with the accepted counts. Verification emits all
28 bytes and the unsigned ID before cleanup. There are separate records for
arm, rejection, TID, phase start/budget, raw submission, completion command
and result, service output, ledger, first failure, outstanding resources and
terminal sequence. Enumeration values are in the two C modules and header.

Admission reserves eight ordinary records plus five per outstanding close
and 28 for verification, phase changes, failure and termination. A cleanup
operation reserves five records, five per remaining close and 14 for terminal
work. The writer appends payload, computes the 32-bit FNV-1a over its 32 wire
bytes, cleans both the payload and check word, applies a compiler memory barrier and publishes and cleans the aligned commit sequence. The cache
syscall must order and drain physical writes before return. StarStruck's
`DCFlushRange` calls `FlushMemory` and flushes the AHB. This gives a public
ordering model for the two calls. The actual target remains unverified.
The reader must acquire the commit then the announced immutable records,
verify each check word, sequence and identity, and compare repeated captures.
DIP freezes publication at terminal return. External evaluation preserves
exchange verification, baseline attribution and safe termination independently.
[Trace writer](netdisc.c) · [Cache syscall][cache] · [Write-buffer drain][drain]

## Build and interpretation

`make experimental-dip-sizing` requires separate owner approval for the exact
reviewed commit. It takes the stock procedure's `D2X_REPO`, `R32_ARCHIVE`,
fresh `WORK_DIR` and optional matching `DEVKITARM`. Use the same unprivileged
Linux environment, native dependencies, pinned source tar and verified Buster
r32 archive as the [stock measurement](../d2x-build-baseline.md#run-the-stock-measurement).
The separate [hosted workflow](../../.github/workflows/experimental-dip.yml)
checks repository, owner, both actors, workflow path, develop ref, attempt
one, full SHA and matching event, workflow and checkout before provisioning.
Normal CI runs synthetic and native PC fixtures.

1. Verify upstream commit/tree/epoch, source tar, toolchain archive and all
   four original source files plus the patch. Both builds share the verified
   compiler, flags, source epoch and linker script.
2. Build and inventory a fresh stock control. Require the historical original
   ELF hash, map hash and reconciled spans. Canonicalize only the toolchain
   directory prefix in the comparison copy of the map, because GNU ld prints
   its absolute libgcc path. Preserve the raw map hash. Record the archive
   hash separately. The historical `cios-lib.a` mismatch remains unexplained.
3. In a second fresh extraction, apply the reviewed patch and install the
   verified sources. Check the two patched upstream file hashes. Run the same
   recipes once. On failure retain bounded compiler, assembler and linker
   causes, artifact hashes and available relocatable section sizes.
4. For a no-fit verdict, reconcile **every** ld overflow report with the
   unchanged memory configuration and the attempted allocated outputs in
   linker-script order. For a named section use its own exclusive end. For a
   region byte count use the highest exclusive end assigned to that region.
   Check both inclusive load ranges for an accompanying overlap report.
   The excess is the distance past the region limit. A fitting named section,
   inconsistent byte count, unsupported companion error or insufficient map
   yields `overflow-evidence-unresolved`. The journal keeps observed reports
   and available ranges separately from corroborated overflow rows. For an
   explicit-address diagnostic, `overflow-report` retains ld's numeric exclusive
   end. The independent map start, exclusive end and excess are in `attempted`.
   [GNU ld range diagnostics][ldrange]
5. After successful recipes record the original link before instruction
   inspection. Reconcile the original ELF, map, LOAD file and memory ends,
   origin-to-end spans, trailing bytes, deltas, fill, BSS and completion pool.
   Compare stock and modified symbol addresses, sizes and file-backed hashes.
   BSS and unsized assembly labels have no per-symbol file hash.
6. Starting at the outer hook address, follow individual instructions,
   direct calls and returns, conditional and tail branches, and supported
   constant interworking veneers. A branch to an interior address starts at
   that instruction. A literal word supplies a destination only for a
   supported load. Sequential advancement and a returning call's continuation
   require the caller's instruction mode. Cross-mode returns require explicit
   interworking evidence in the supported traversal. The traversal records gaps, indirect transfers, mode
   mismatches and unsupported forms at their addresses. The parser uses the
   ARM and Thumb zero-operand comment forms in the pinned GNU disassembler.
   [GNU 2.20.1 ARM disassembler][binutils]

### Independent linked-path review

The journal records individual source and destination addresses for resolved
edges, selected call-site witnesses, missing entries, and addresses where
traversal stopped. Witnesses identify places to inspect. Each checklist item
still requires independent instruction review, including reachable inlined
code and both outcomes of the controlling predicate where applicable.

| Path | What to establish in the matched original ELFs and modified control flow |
| --- | --- |
| Stock forwarding | Follow the hook's zero result through the original switch cases and default to their stock calls and return values. Compare the stock control. |
| Arm admission | Trace selector 0xF7, first claim, independently provisioned input bounds, complete owned-line synchronization and full validation through binding and receipt publication. |
| Malformed attempt | Follow reserved-input and bound-output candidates, including the 96-byte 0xF7 overlap, through the read claim to terminal rejection. Check that foreign input is untouched on both rejection and stock forwarding. |
| Duplicate rejection | Check the full synchronized arm replay and the already-spent read return, with no second exchange or trace write. |
| Network selectors | Follow open/close and the NCD 7, KD 6, SO 31/16/15/4/13/12/3 cases through the appropriate ioctl or ioctlv, handle namespace, vector counts and control lengths in the operation table above. |
| Receive handoff | Follow the unique completion, command 8, signed count and remaining length, synchronize that count, copy exactly those bytes, then release the slot. Include a final one-byte return. |
| Deadline and quarantine | Check equality, the first abandonment or verification epoch, late reconciliation, ambiguous ownership and the frozen terminal path with outstanding storage retained. |
| Eligible cleanup | Trace negative completed socket creation, original parent SO, reserve, remaining cleanup time, socket-before-parent order and a single close per acquisition. |
| Trace and return | Verify payload/check clean before commit, first failure and verified bytes preserved, terminal sequence, raw hook return and writer freeze. |

Visible stack observations give entry saves and constant local adjustments.
Dynamic writeback, indirect transfers, deeper calls and target runtime stack
remain open. Conditional edges describe possible paths. Return traversal
assumes the linked code follows its calling convention. Opaque IOS traps can
stop automated traversal before a caller continuation. Accept static fit only after the matched spans, retained material
dependencies and every applicable path above are independently accounted for.
An inspection failure after the initial link is recorded as
`linked-inspection-unresolved`. A completed report calls for review. Successful reconciliation can establish executable and RAM spans while
retained-path acceptance remains open.

### Publication and scratch evidence

Only `sizing.jsonl` is eligible for upload. The collector parses every row
before writing the first byte. It checks the reviewed input identities,
closed relative artifact and symbol lists, tool and runner fields, diagnostic
categories and causes, bounded JSON integers, and fixed-format hashes.
Public measurements include regions, sections, stack adjustments and numeric
control-flow findings. Unreviewed symbol and section names are represented
by `other` and their numeric extents. Full command lines and resolved
packages are recorded privately in build and preparation logs whose SHA-256
digests are public. Failure evidence goes through the same collector.

The original ELF, map, complete nm and objdump listings (including literal
words), object files and unrestricted logs stay in disposable runner scratch.
To review a material open path after the runner disappears, a reviewer would
need the relevant basic blocks from hook entry or its already witnessed
predecessor, their branch destinations, any veneer and associated literal,
and the blocks establishing the predicate, call arguments, handoff or return.
Identify offsets against the original ELF and raw listing hashes. Those
excerpts may derive from d2x, linked archive members or compiler helpers.
Their per-input provenance and redistribution terms need a separate owner
decision **before an execution intended to retain or publish excerpts**.
The first hosted experiment is sizing-only. If reviewers need linked
instructions, a separately authorised follow-up measurement can address
provenance and retention. Ephemeral
scratch and a hash alone cannot reconstruct instructions for later acceptance.

The historical control used 6,708 of 8,192 executable bytes and 246,912 of
262,144 static RAM bytes.
[Orchestration](../../scripts/experimental_dip_build.py) · [ELF and map checks](../../scripts/experimental_dip_inspect.py) · [Traversal](../../scripts/experimental_dip_flow.py) · [Evidence schema](../../scripts/experimental_dip_evidence.py)

## Provenance for this integration

| File or source input | Assessed use |
| --- | --- |
| `netdisc.c`, `netdisc.h`, `netdisc_net.c`, `netdisc_gate.s` | Original GPL-3.0-only contributions. No networking implementation copied. |
| d2x `source/dip-plugin/plugin.c`, `plugin.h`, `ioctl.h` | GPL-3.0-or-later file notices permit GPLv3. The patch changes the outer function only. The command table is a reference. |
| d2x `source/dip-plugin/Makefile`, `link.ld` | No standalone notices. The object-list insertion is original and the zero-context patch reproduces no Makefile body. Use the original linker file in scratch. The DIP directory contains the GPLv3 text. |
| d2x `source/cios-lib/types.h`, `ipc.h`, `ios.h`, `isfs.h`, `mem.h`, `tools.h`, `syscalls.h`, `syscalls.s` | Each carries GPL-2.0-or-later, permitting selection of GPLv3. Use upstream declarations and trap symbols in the disposable build. |
| d2x `source/cios-lib/libc.c` | Stock member implementing memory functions, with no file-level licence notice. No source copied or separately published. |
| Other stock archive inputs | The archive also compiles GPLv2-specific `libwbfs.c` and `wiidisc.c` and conditionally licensed `rijndael.c`. The historical map extracts none of those members. Keep the full stock archive procedure and examine actual retention. Binary redistribution needs a separate complete provenance review. |
| HAI and libogc `network_wii.c`, GX `wdvd.c`, Dolphin NCD, StarStruck kernel | Behavioural references only. The networking source header credits bushing with a three-restriction permissive notice. Dolphin NCD carries GPL-2.0-or-later. StarStruck files specify GPL version 2. No third-party client, emulator or kernel bodies enter the patch. |

The pinned archive stays external throughout. Publication is limited to
original additions, the narrow integration diff and validated research text.
[Upstream DIP tree][dip] · [Upstream library tree][cios] · [Historical retained members](../direct-dip-tcp-probe-fit.md) · [Primary reference inventory](../r0-01-r0-02-source-investigation.md)

[gx]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L9-L36
[commands]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/ioctl.h#L23-L57
[dispatch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L221-L763
[envelope]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.h#L103-L116
[mem1]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/mem.h#L25-L34
[hai]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c
[ogc]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L273-L474
[ncd]: https://github.com/dolphin-emu/dolphin/blob/f0519d4f6cfa650846674d0b15849035b4c27e74/Source/Core/Core/IOS/Network/NCD/Manage.cpp
[linkstatus]: https://github.com/dolphin-emu/dolphin/blob/f0519d4f6cfa650846674d0b15849035b4c27e74/Source/Core/Core/IOS/Network/NCD/WiiNetConfig.h
[ipc]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/syscalls.h#L75-L81
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L69-L98
[ownership]: ../ios-ipc-ownership-and-fixture.md
[cache]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/memory/memory.c#L123-L142
[drain]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/memory/memory_asm.S#L135-L141
[dip]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin
[cios]: https://github.com/wiidev/d2x-cios/tree/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib

[haisocket]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L697-L720
[ogcsocket]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L701-L726
[binutils]: https://gnu.googlesource.com/binutils-gdb/+/7f56ba6d9c7a2c4b27f54b3cabcb2524611937d3/opcodes/arm-dis.c
[ldrange]: https://gnu.googlesource.com/binutils-gdb/+/7f56ba6d9c7a2c4b27f54b3cabcb2524611937d3/ld/ldlang.c#4587
[ppchandoff]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/ipc.c#L1051-L1077
[ppcdispatch]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/ipc.c#L289-L313
[invalidate]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/memory/memory.c#L152-L177
