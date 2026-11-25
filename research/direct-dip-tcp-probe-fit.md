# Can the IOS57 diagnostic TCP probe fit in DIP?

**R0-03, 25 November 2026 · Recommendation (hypothesis).** Direct DIP might
fit, but two source-level questions come first. Who owns a network request
after the DI thread's deadline expires, and who can read the entry and failure
records while GX is still waiting for DI? Both answers change the code that
must fit in the **1,484 executable bytes** left by stock DIP. A link of just
the successful exchange would measure the wrong program.

The target is the hooked DI thread on an original Wii running d2x on IOS57
v5918. The question ends immediately before GX calls its network cleanup
helper. R0, post-handoff networking and production transport placement remain
open. [Baseline experiment](ios57-baseline-plan.md) · [Lifecycle investigation](r0-02-r0-03-ios57-v5918-network-lifecycle.md)

## Evidence used

**FIT-01 · Experimentally verified, stock only.** The retained ZIP for run
`45613302561`, attempt 1, artifact `15020234721`, is 39,382 bytes. Its SHA-256
matches `b18b2b8b4c77951563d78bc727945dc3f6d13418a0d2dfdbc835986ca6223cec`.
Compared the scratch reports with all 17 ZIP members. Read both original ELF
listings (`a-elf.txt` and `b-elf.txt`, including `nm -nS`), maps, build logs,
footprint reports and the comparison. The maps and footprint reports are
byte-identical. The ELF listings agree after accounting for the extraction
paths. The recorded comparison finds identical original and converted ELFs.
Only `cios-lib.a` differs, for an unresolved reason. [Hosted run][run] · [Retained evidence][artifact]

| Stock region | Occupied half-open span | Capacity | Occupied | Trailing |
| --- | --- | ---: | ---: | ---: |
| Executable | `0x13800000` to `0x13801a34` | 8,192 B | 6,708 B | 1,484 B |
| Static RAM | `0x13802000` to `0x1383e480` | 262,144 B | 246,912 B | 15,232 B |

The executable LOAD includes 20 B of `.init`, a 12 B gap and 6,676 B of
`.text`. The RAM LOAD includes 828 file-backed bytes, a 4 B gap and 246,080 B
of memory-only BSS. These are the starting spans for a future comparison.
[Stock footprint and input hashes](d2x-build-baseline.md)

**Source-verified scope.** The study uses Wii NetDisc
`96de177f632d4b4183b23e286fe33e6e0cc2a4c8`, d2x
`33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7` and the same HAI-Riivolution,
libogc and GX revisions as the baseline. The source links below pin the full
revisions. Inspected public source as text and checked the client sources
against the pinned Git trees in scratch. The stock run used devkitARM r32,
GCC 4.5.1 and binutils 2.20.1.20100303. This study made no modified link or
hardware observation. The per-file provenance review for reuse is still open.
[Build baseline](d2x-build-baseline.md) · [Source and licence inventory](r0-01-r0-02-source-investigation.md)

## What one successful run must establish

**FIT-02 · Hypothesis, minimum design.** Use one locally booted GX fixture,
one tagged synthetic unencrypted DI read and one TCP connection to a fixed
IPv4 peer on the wired interface. Only the hooked DI thread submits the
network operations. A terminal failure ends the attempt. Reconnection
invalidates the run. The experiment needs three independently attributable records.

1. **GX dispatch.** Record the fresh 8-byte run tag, slot, IOS instance and
   build identity. Issue the read immediately before `BootGame` calls
   `AppCleanUp`. Match only the armed synthetic request in `DI_EmulateCmd`
   before it reaches `__DI_ReadUnencrypted`. Stock GX sends eight aligned
   words, with the command, length and word offset in the first three. Only
   20 bytes remain, and forwarding of spare words through original DI is
   unverified. A candidate fixture could stage the fresh 16-byte challenge in
   a one-use local record keyed by the run tag. How GX arms exactly one read
   and delivers the challenge to the intended caller remains unresolved. [GX buffer][gxbuf] · [GX read][gxread] · [DI dispatch][dipread] · [GX boot order][gxboot]
2. **IOS entry and completion.** Before the first network call, publish the
   tag and actual thread ID to a local observer that can still run if the
   cable is unplugged and the synchronous read never returns. Record the
   current operation before submission, then its result, elapsed time, handles,
   byte counts, exact reply and first error or deadline. Keep cleanup results
   alongside the original failure. One candidate is a sequence-numbered trace
   area and a second PPC thread that captures it locally without issuing DI
   requests. Visibility, cache ownership and capture while DI is stalled are
   unresolved. [DI thread ID][dithread] · [Baseline evidence contract](ios57-baseline-plan.md)
3. **Peer and GX agreement.** The request contains the 8-byte run tag followed
   by the fresh 16-byte challenge. The peer assigns a connection ID when it
   accepts the socket and logs both endpoints and the bytes received and sent.
   DI receives and records the complete 28-byte reply, compares all 24 echoed
   bytes with its request, decodes the final four bytes as an unsigned
   big-endian ID and rejects zero. During evidence review, match that reply
   and ID to the endpoints and byte records for the corresponding accept in
   the same peer run. A baseline pass also requires the matching synchronous
   DI return before the GX marker immediately preceding `net_wc24cleanup`. Capture raw IPC status
   as well as GX's result and the returned record. The stock GX
   wrapper can report zero for both a raw 1 and a raw 0. A peer reply alone
   cannot establish which caller completed before cleanup. The existing PC
   peer binds loopback. A later wired fixture must preserve its framing and
   logging on the chosen interface. [Wire format](tcp_peer/README.md) · [Peer ID assignment](tcp_peer/peer.py) · [GX return][gxread] · [AppCleanUp][gxapp] · [DeinitNetwork][gxnet]

**Work that can stay outside DIP.** The fixture can generate fresh inputs
and the PC can format the binary records. DNS, discovery, TCP window tuning,
GPIO activity indicators, repeat challenges and backing-file access add
no evidence to this one exchange. Readiness and the KD service reply remain
part of the cold-start baseline. Skipping startup would require an independently
established ready state for this owner and IOS instance and a separately
labelled warm-start observation. GX's network state or HAI's cached SO handle
cannot supply that evidence. [ARM init][hinit] · [ARM socket creation][hsocket]

## IOS operations and their evidence

**FIT-03 · Source-verified client operations.** HAI supplies an ARM client.
Libogc supplies a PPC cross-check on IOS request ordering and KD reply handling.
Neither supplies the target resource managers. The order below starts with
no descriptors. Preserve zero as a possible valid handle or socket number.

| Operation | What the source actually does | What the probe must add or establish |
| --- | --- | --- |
| NCD link | Open `/dev/net/ncd/manage` mode 0. `NCDGetLinkStatus` submits `GETLINKSTATUS` with zero input vectors and one 32-byte output, then closes NCD. HAI returns IPC status without interpreting the output. [ARM NCD][hinit] | Record status and coherent reply separately. A game client distinguishes working, in-progress and no link. Raw NCD IPC success alone cannot identify a wired link. Retain the raw result and corroborate readiness with the wired interface and peer. [Game-side link check][mkw] |
| SO handle and KD startup | Open `/dev/net/ip/top` mode 0. Separately open `/dev/net/kd/request` and issue `NWC24_STARTUP` with no input and a 32-byte output. HAI returns ioctl status. Libogc reads the first signed word on IPC success, retries service result −29 and treats −15 as already started. Close KD. [ARM init][hinit] · [Libogc state machine][ppcinit] | Record both statuses and any retry in the original bring-up interval. Check submission, completion and close, including failures. Keep raw values and distinguish KD results from socket errors. |
| SO readiness | On the SO handle, `SO_STARTUP` and `SO_GETHOSTID` are ioctls with empty buffers. Host ID is returned as the result. Both clients poll for a nonzero address. [ARM init][hinit] · [Libogc state machine][ppcinit] | Record the raw host ID and validate it against the wired fixture. Zero is still waiting. Account for error returns and valid IPv4 values with the high bit set. Keep one bring-up deadline across all calls and retries. |
| Create and connect | `SO_SOCKET` takes three 32-bit words (IPv4, stream, protocol 0) and returns the socket number. `SO_CONNECT` takes a 36-byte structure with socket, address-present word and 28-byte address field. The Wii IPv4 address uses 8 bytes including length, family, network-order port and IPv4 address. Both commands go to the SO handle. [Socket][hsocket] · [Connect][hconnect] · [PPC address layout][ppcaddr] | Track one socket. If using nonblocking mode, check the get/set-flags operations and distinguish in-progress, already connected and failure on that socket. A pending connect never authorises a second connection. [ARM fcntl/poll][hpoll] · [Mount][mount] |
| Send 24 | `net_sendto` passes `SO_SENDTO` two inputs (payload, 40-byte socket/flags/destination control), zero outputs. Connected send has no destination. [ARM send][hsend] | Send exactly the remaining bytes. Advance only on a positive count at most equal to the remaining length. Treat zero as no progress, handle a supported transient status within the deadline and fail on other errors. |
| Receive 28 | `net_recvfrom` passes `SO_RECVFROM` one 8-byte socket/flags input and two outputs (payload and unused source-address slot with null pointer and zero length). The result counts bytes. [ARM receive][hrecv] | Reassemble positive short reads, reject over-counts and premature EOF, then verify the entire frame before expiry. Neither a partial transfer nor a transient error restarts the clock. |
| Release | `SO_CLOSE` is an ioctl on SO with a 4-byte socket argument. `net_deinit` closes the SO resource-manager handle. Global KD cleanup is a separate GX action. [Socket close][hclose] · [SO close][hinit] · [GX helper implementation][ppccleanup] | Close each acquired resource once when safe, including NCD/KD on partial setup. Report individual close results and any still-outstanding operation. Leave the global cleanup marker to GX. |

**FIT-04 · Source-verified difference, target cache contract unresolved.**
DIP's `WBFS_Read` aligns control storage and vectors to 32 bytes, flushes
both before submission and invalidates the destination after completion.
HAI flushes send bytes and parameters. Its receive path calls
`os_sync_after_write` on the output, leaves `os_sync_before_read` commented
out, and rounds its unaligned bounce copy to four bytes. For example, after a
one-byte receive the next destination is already unaligned. HAI also bounces
receive buffers below `0x10000000`. DIP's static RAM is above that threshold,
but the address alone cannot establish SO's access. Reuse a dedicated
cache-line-aligned scratch buffer for successive transfers, submit only the
remaining wire length, and copy exactly the returned count into private frame storage.
Keep vectors, inputs, outputs and completion storage valid until IOS releases
them. Check permitted addresses and the clean/invalidate direction at each
producer/consumer handoff, including KD, NCD and the local observer.
[WBFS_Read][wbfs] · [ARM send][hsend] · [ARM receive][hrecv] · [Vector definition][ipc]

## Deadline feasibility

**FIT-05 · Source-verified limitation.** HAI retries NCD open with sleeps,
polls host IP, and uses synchronous ioctl/ioctlv for the socket operations.
`RiiHandler::Mount` retries init on `EAGAIN`, tries nonblocking connect
and switches back to blocking for data. `net_poll` itself makes a synchronous
SO ioctl. A nonblocking socket or a finite poll bounds the wait requested of
a responsive SO service. It gives the DI thread no way to regain control
from a wedged open, KD request, poll, transfer or close. Even the PPC
`net_deinit` abort path waits for its init chain to finish. [ARM init][hinit] · [Mount][mount] · [ARM poll][hpoll] · [PPC teardown][ppccleanup]

**Hypothesis, smallest candidate worth sizing.** From the DI thread, submit
one asynchronous operation at a time, including opens, closes and transfers.
Use one private completion queue and a distinguishable one-shot expiry message.
Record each phase's start, deadline, completion time and result.

| Phase | Deadline and evidence |
| --- | --- |
| Bring-up (baseline) | Start before NCD open. Allow 30 seconds through SO readiness, including startup retries. |
| Connection (sizing proposal) | From readiness, allow five seconds in total for socket creation and a single connection attempt. This follows the PC client's separate five-second connect timeout. |
| Exchange (baseline) | On the connected socket, set one absolute five-second deadline before the first send. Every short send, partial receive and retryable operation uses the remaining time. Verify the complete reply before expiry. Partial progress never extends the deadline. |
| Cleanup (sizing proposal) | Start on verified reply or when abandoning an attempt. Allow five seconds total to release acquired resources and record the outcome. This gives the few local close requests an observable window and caps how long DI waits for them. Target close latency is unmeasured. Expiry transfers responsibility to recovery. |

The connection and cleanup bounds require owner acceptance. For each phase,
check elapsed time when its final operation completes. A completion at or
after expiry misses that phase's deadline even if dequeued before the timer
message. [Baseline budgets](ios57-baseline-plan.md) · [PC client](tcp_peer/client.py)

Record a timely exact reply as **exchange verified** even if close later stalls
or fails. Record the close status, elapsed time, outstanding resources and
whether the fixture terminated safely. If all baseline evidence is present,
including the matching synchronous DI return before the GX marker, report
the baseline pass alongside the cleanup outcome. If cleanup prevents evidence
of that return or its ordering, the exchange observation stands and the
baseline verdict is indeterminate. Requiring timely successful cleanup and
safe termination for overall fixture acceptance is a stricter proposal for
owner review. [Baseline verdicts](ios57-baseline-plan.md)

Clock units, wrap-safe elapsed arithmetic and worst-case
delivery/scheduling latency need evidence on this caller. The d2x header
declares `os_timer_now(time_id)` while HAI declares a no-argument clock at the
same syscall number. Timer creation takes microseconds in the d2x header.
[d2x declarations][sysdecl] · [HAI declarations][hdecl] · [PC client](tcp_peer/client.py)

**Unresolved at the timeout boundary.** HAI types async open, close, ioctl and
ioctlv with a queue ID and an IPC message pointer. d2x declares the final
arguments of open/close as pointers and those of ioctl/ioctlv as variadic.
Submission status and the result written on completion are distinct. d2x USB
submits asynchronous ioctls to a queue with persistent completion objects.
HAI's DNS path waits for an async reply or a timer, then destroys the timer
and queue and can free an input on timeout. The example shows no cancellation
or drain after expiry.
With either example, an outstanding open can later return a live descriptor,
or receive can still write the destination. A thread-cancel entry point is
no evidence of request cancellation. The PPC callback ABI is also distinct
from HAI's ARM queue/message convention. [d2x declarations][sysdecl] · [d2x USB submission][usbasync] · [d2x completion dispatch][usbcb] · [HAI async wait][hasync] · [ARM syscall signatures][hdecl]

On expiry, publish the affected phase, elapsed time and last submission.
End the attempt and preserve any verified exchange result. A bounded return would need
acknowledged cancellation **or** persistent quarantine of the queue, message,
vectors, payload and handles until a separately scheduled owner drains the
late reply and completes cleanup. Never leave IOS holding a DI stack or GX
return buffer. Reject a second run while the first owns anything. Queue
capacity must allow an expiry and completion arriving together. If submission,
timer delivery, cleanup, or the trace sink itself stalls, an independently
scheduled watchdog with a local observer and a defined recovery action is
required. A hang or reset records an operationally unsuccessful fixture and
the recovery action. The experimental verdict depends on the surviving
evidence. The pinned sources leave bounded recovery on 57/5918 unresolved.

- **Failed baseline.** The trace attributes entry to the intended caller
  before GX cleanup and demonstrates a failed network attempt, timeout or
  mismatched reply. Independent checks confirm the peer and wired controls.
- **Probe never ran.** GX records skipped dispatch or rejection before caller entry.
- **Indeterminate.** Without evidence of a skip or pre-entry rejection,
  missing caller entry leaves the run indeterminate. Lost trace, uncertain
  ordering, the wrong IOS instance or failed controls also leave it
  indeterminate. A hang or reset alone supplies no attribution.
  [Baseline evidence and outcome definitions](ios57-baseline-plan.md)

## What the stock executable already pays for

**FIT-06 · Experimentally verified retention, source-verified dependencies.**
The stock linker extracted `syscalls.o` for `os_get_thread_id`. Its single
ARM `.text` occupies `0x1b8` (440 B) at `0x1380167c`. Assembly emits the IOS
traps together, so section GC retains even the unused async entries. The
stock build commands specify big-endian ARM926EJ-S, Thumb/interworking,
`-Os -ffreestanding -fno-builtin -ffunction-sections -fomit-frame-pointer`.
The static link uses `--gc-sections`, `cios-lib.a` and `-lgcc`, with no
standard libraries or startup files. An archive member selected at link time
can still have individual input sections discarded. [Maps, nm and build logs][artifact] · [Assembly entries][sysasm] · [Library build][libbuild] · [DIP build][dipbuild]

The linker extracted `ios.o`, `isfs.o`, `libc.o`, `stealth.o`, `swi_mload.o`,
`syscalls.o`, `tools.o` and `usbstorage.o` from cios-lib.
For example, the contiguous trap entries for `os_ioctl` and `os_ioctlv` are
at `0x13801784` and `0x1380178c`. The two direct range functions in `tools.o`
step by 32 bytes per loop iteration. The IOS sync calls used by `WBFS_Read`
take byte lengths. Reuse requires preserving those distinct contracts.
[Original map and symbols][artifact] · [Direct range functions][ranges] · [WBFS_Read][wbfs]

| Work | Already in the original ELF | Incremental dependencies or equivalent new work |
| --- | --- | --- |
| Dispatch and report | `DI_EmulateCmd` (1,096 B), `__DI_ReadUnencrypted` (104 B), `os_get_thread_id`, `svc_write`. `DI_Printf` is a 4-byte BSS pointer. | Tagged gate, one-use fixture access, publish entry/progress/result, correlate synchronous return. Stock `DI_Printf` call sites compile away. MLOAD defaults to debug off and compiles out its RAM log buffer. Its Gecko mode depends on a physical sink and includes hardware waits. A callable print entry supplies no guaranteed independent trace. [DIP debug macro][dipdebug] · [MLOAD default][mlmain] · [Buffer configuration][mlhdr] · [Gecko writes][gecko] |
| Bring-up, stream I/O and release | `os_open`, `os_close`, `os_ioctl`, `os_ioctlv` and their async counterparts. `WBFS_Open/Read/Close` are storage-specific comparators. | No NCD/KD/SO or TCP wrapper in stock DIP. Supply aligned parameters, vector construction, status interpretation, finite phase transitions and error cleanup. Importing HAI wrappers would add its allocation/free, errno conversion table, timer/sleep, socket tuning and GPIO dependencies along the inspected paths. [ARM client][hinit] · [Socket][hsocket] · [Vector I/O][hrecv] |
| Coherency and exact compare | `__os_sync_after_write`, `__os_sync_before_read`, `DCFlushRange`, `DCInvalidateRange`, `memcpy` (304 B), `memset` (102 B plus 80 B inner). | Call-site and cache-range work still costs bytes. Stock `.text.memcmp` is **discarded**, measured 30 B of input text. Referencing it adds that body before padding. `InvalidateVector/FlushVector` from `ipc.o` are absent and have different input/output roles. [Cache aliases][sysdecl] · [Vector helpers][vectors] · [Byte comparison][cmp] |
| Timers and completion | `os_timer_now`, create/restart/stop/destroy timer, queue create/receive/destroy/ack and thread primitives all lie in the retained assembly block. | Supply deadline and submission checks, event matching, lifetime and late-reply handling. d2x `Timer_Init/Timer_Sleep` were archived but unlinked. They depend on a 64-byte queue allocation via `Mem_Alloc/Free`, a configured heap and relative timer/queue waits. They cannot interrupt a synchronous IOS call. [Timer implementation][timer] · [Heap wrappers][mem] |
| Optional formatted logs | Existing literal-string `svc_write` and specialised `Stealth_Log`. | `LOG_Write` would bring in `itoa`, `strrev`, `strlen` and possibly division helpers. `svc_printf` would add `vsprintf` and a 512-byte static buffer. None of these formatters is present in stock DIP. The estimate assumes a compact binary writer. [Log wrapper][log] · [Integer formatting][itoa] · [svc_printf][fmt] |

## Incremental footprint

**FIT-07 · Estimate, conditional on one outstanding operation and a fixed
binary trace.** Existing retained function bodies add zero incremental text
when reused. Their callers, literals and control flow still grow. The table
uses same-compiler stock function sizes as units of comparison. Multipliers
are engineering judgements about groups of work, with no instruction counts
for the proposed probe. Rows cover different work and charge the shared wait
path only once. [Original ELF sizes and map][artifact]

| New DIP work | Stock comparison and assumed work | Estimated text |
| --- | --- | ---: |
| Recognise request, publish local records and return result | Two to three bodies the size of `WBFS_Open` (80 B), assuming an already accessible trace area | 160–240 B |
| Bring-up and resource ownership | Three to five `WBFS_Read`-sized bodies (100 B) for NCD, KD reply/retry, SO readiness and handle cleanup | 300–500 B |
| Socket/connect, two short-I/O loops and frame verification | One to two 80 B setup bodies plus two to three 100 B vector paths, using shared copy and compare helpers | 280–460 B |
| Shared async submission, timer/queue dispatch, first failure and expiry | Two to four bodies comparable to `__usbstorage_Read_Write` (156 B). Assumes a single persistent slot and an external owner for recovery | about 310–625 B |

The **probe-specific subtotal is roughly 1,050–1,825 B**. With the 30 B
`memcmp` body, the low case leaves about **400 B** of the stock 1,484 B,
and the high case already exceeds capacity by about **370 B**. Neither end
bounds the complete implementation. Any additional on-DIP trace backend,
watchdog, late-reply drainer or recovery code must be charged to the design.
Their costs depend on the missing ownership contracts.

**Linker and compiler costs, unresolved.** The map shows a discarded
88 B `_muldi3.o` text section even though `__aeabi_lmul` caused archive
extraction. Variable division, wide tick conversion or formatting may retain
libgcc bodies. Thumb-1 caller to ARM syscall transitions may use direct
interworking calls, veneers or literal pools depending on relocation and
layout. Stock `.glue_7` and `.glue_7t` contribute zero bytes. There are
already 2 B and 12 B input fills in `.text`, and output ends align to four
bytes. A modified link can change padding in either direction. Charge all
these costs by comparing mapped spans, sections and LOAD extents. Interior
holes, discarded inputs and the separate IOS table are unavailable as
additional trailing budget. [Stock map][artifact] · [DIP linker script][layout]

**Static RAM estimate.** A single-slot layout could use three 32-byte slots
for the original request, the assembled reply and aligned transfer scratch,
64 B for the largest control structure, 32 B for up to three vectors, and
32 B each for service output, completion message and a small queue. That is
about 288 B before the run record. Sixteen to twenty-four compact 16-byte
stage records would add 256–384 B, plus the 56 B of NUL-terminated device
names, handles, elapsed times, reply evidence and alignment. Roughly
**0.6–1 KiB** of static growth is plausible for this example. Keep the first
failure and final state even if progress repeats. Any observer, extra pending
slot or worker stack needs its own budget. [ARM control layouts][hstruct] · [ARM async record][hipc] · [Stock RAM](d2x-build-baseline.md)

**Heap and DI stack, unresolved.** Fixed-lifetime aligned storage could
eliminate probe-side dynamic buffer allocations. IOS service allocations
remain unknown. The retained `DI_Alloc/DI_Free` symbols are pointers into
base DI, with no measured heap capacity. Stack frames, spills, call depth
and remaining DI caller stack are unmeasured. DIP's 4,096 B startup stack is
already in BSS and belongs to module startup. Neither it nor the 15,232 B of
trailing static RAM gives the probe a caller-stack or runtime heap allowance.
[DI function pointers][patch] · [Startup stack][start]

## Connection owner and next decision

**FIT-08 · Hypothesis.** Direct DIP remains the first caller to investigate.
A separate service changes who could finish a late operation, but adds a
second ownership boundary to every synthetic DI request.

| Question | Direct DIP | DIP-invoked IOS service |
| --- | --- | --- |
| Executable and RAM | All new ARM logic competes for the same 1,484 B. Aligned static buffers appear less constrained than code. | DIP still needs a measured dispatch, deadline and return path. Network code, queue, buffers and stack move to a separately mapped executable with unknown capacity and total footprint. |
| Caller and lifecycle | Hooked DI must open NCD/KD/SO, own the socket and release it before GX cleanup. Its FAT thread right demonstrates storage-specific access. | DIP must be allowed to open the service, which must independently be allowed to open NCD/KD/SO. The service owns its descriptors. Both owners still share the IOS network lifecycle. [DI rights][dithread] · [Lifecycle investigation](r0-02-r0-03-ios57-v5918-network-lifecycle.md) |
| Deadline and visibility | A stalled synchronous call stalls the read. Require local entry and progress observable independently of DI return. | A scheduled service could drain late replies using its own storage. DIP still needs a bounded wait and safe handback. Record both the tagged DIP dispatch and service-thread entry, then join service, DI and peer results. |
| Startup and packaging | Uses an existing hook and startup record. | Requires an available identity, region, stack, startup/registration, queue, request/reply ABI and packaging path for this base. HAI has ID 18, an 8 KiB stack, a registered service loop and a DI-to-file path in its own environment. The d2x 57/5918 map identifies no such network probe service. [HAI startup][hstart] · [Registered loop][hloop] · [DI client][hdi] · [d2x base map][basemap] |

**Recommended next task, source only.** Investigate a statically allocated
one-shot IPC request context. Trace late open, receive and close completions
through expiry and recovery. Identify who owns the queue, message, buffers
and handles at each step, including who releases a handle returned after
timeout and when it is safe to reuse the context. Establish the ABI, clock
units and privileges. Specify how the fixture delivers fresh data to DI and
how an independent local reader captures entry and progress while DI is stuck
and networking is unavailable. If the timelines rely on unbounded waits or
premature reuse, investigate the service alternative against the same cases
before seeking a direct-DIP build.

**Conditional future PC-only measurement.** Once the owner accepts those
contracts and the per-file provenance, a separately authorised experiment
could link one complete synthetic probe into the pinned stock DIP in disposable
PC scratch. Use the public d2x source and hash-identified r32 inputs from the
baseline, the same flags, stock objects and linker regions, plus the reviewed
probe diff and test vectors. Keep the real hook, trace writer, deadline and
cleanup paths reachable. GX/peer records can be fixture inputs to a size
study. It requires no GX build, proprietary firmware, packaging or console.

1. Compare a matched stock control to the retained original-ELF footprint.
   Stop on a baseline mismatch. Retain build logs and identify the inputs.
2. For the modified original ELF, reconcile the map with sections, symbol
   sizes and all LOAD ranges. Attribute the delta to changed stock functions,
   new wrappers, library bodies, veneers/literals, padding and static data.
   Inspect the actual call paths and stack frames. Record any unknown depth
   or target-only service allocation.
3. Accept **link fit only** if all required paths survive GC, stock functionality
   is present, executable end is at most `0x13802000` and RAM end is at most
   `0x13842000`, with every load byte accounted for. Stop on overflow, missing
   evidence paths, unowned late buffers or a need to change flags or regions.
   A complete link would measure static fit. Permissions, actual deadline
   behaviour, stack margin and a peer-confirmed exchange still need separate evidence.

[ADR 0003](../docs/decisions/0003-stock-dip-build-strategy.md) authorises
stock compilation only. A modified-source prototype and link require an
explicit owner decision under [ADR 0001](../docs/decisions/0001-research-first.md),
a reviewed scope change to the stock-only [agent instructions](../AGENTS.md)
and [research plan](feasibility-plan.md), and separate runner execution
approval. A service build or hardware experiment would need its own scope.
This diagnostic leaves NBD interoperability, frontend selection and RetroMount's
format-conversion role as recorded in the [architecture boundaries](../docs/architecture/README.md).

[run]: https://github.com/lloydsmart/wii-netdisc/actions/runs/45613302561
[artifact]: https://github.com/lloydsmart/wii-netdisc/actions/runs/45613302561/artifacts/15020234721
[gxbuf]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L29-L36
[gxread]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L258-L277
[gxboot]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/GameBooter.cpp#L555-L579
[gxapp]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/sys.cpp#L86-L123
[gxnet]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/network/networkops.cpp#L79-L87
[dipread]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L307-L323
[dithread]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L775-L789
[hinit]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L267-L410
[hsocket]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L697-L720
[hstruct]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L100-L125
[hconnect]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L802-L824
[hsend]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L826-L894
[hrecv]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L896-L973
[hclose]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L980-L993
[hpoll]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L1019-L1101
[hasync]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L452-L485
[hdecl]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/syscalls.h#L46-L86
[hipc]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/ipc.h#L49-L103
[mount]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/file_riifs.cpp#L20-L115
[ppcinit]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L273-L474
[ppcaddr]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L123-L130
[ppccleanup]: https://github.com/devkitPro/libogc/blob/ef718e2d7df5e5b1750a9e1a67c17350bdd30d3e/libogc/network_wii.c#L588-L611
[mkw]: https://github.com/doldecomp/mkw/blob/8b9b5ee653da28663e498039e52f5d19f929a011/lib/rvl/so/soCommon.c#L124-L149
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L36-L96
[ipc]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/ipc.h#L47-L57
[sysdecl]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.h#L29-L92
[sysasm]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.s#L28-L105
[ranges]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/tools.s#L25-L47
[usbasync]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/usb2.c#L195-L235
[usbcb]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/main.c#L162-L177
[dipbuild]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/Makefile#L22-L59
[libbuild]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/Makefile#L10-L62
[dipdebug]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/dip_calls.h#L24-L37
[mlmain]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c#L40-L45
[mlhdr]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/debug.h#L29-L40
[gecko]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/gecko.c#L35-L66
[vectors]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/ipc.c#L29-L54
[cmp]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/libc.c#L147-L158
[timer]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/timer.c#L33-L103
[mem]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/mem.c#L32-L76
[log]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/log.c#L32-L43
[itoa]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/str_utils.c#L29-L60
[fmt]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/vsprintf.c#L295-L320
[layout]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/link.ld#L6-L59
[patch]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/patches.c#L42-L76
[start]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/start.s#L20-L71
[hstart]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/filemodule/source/crt0.s#L7-L39
[hloop]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/proxiios.cpp#L12-L63
[hdi]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/dipmodule/source/dip.cpp#L551-L596
[basemap]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/data/ciosmaps.xml#L250-L302
