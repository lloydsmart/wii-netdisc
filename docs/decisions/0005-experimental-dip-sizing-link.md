# ADR 0005: Authorise an experimental direct-DIP sizing link

- Status: Accepted by the owner. Implementation authority takes effect after independent review and merge of this ADR.
- Date: 2026-11-27
- Decision owner: Lloyd Smart

## Decision and evidence

Authorise one PC-only experiment to answer whether a complete direct-DIP TCP
diagnostic fits in the existing stock linker regions. This task records the
decision. A separate implementation task follows review and merge. Compiling
either the matched stock control or the modified DIP requires separate owner
execution approval for the exact reviewed implementation commit.

**Experimentally verified on PC.** Both stock links occupied 6,708 of 8,192
executable bytes, leaving 1,484 contiguous bytes. Static RAM occupied 246,912
bytes, leaving 15,232 bytes. The two original ELFs and maps matched. The stock
run reported a repeatability failure for one archive. The independently reviewed
fixture simulation merged in [PR #17](https://github.com/lloydsmart/wii-netdisc/pull/17)
with 69 simulation tests and 98 total local tests passing. Its evidence covers
the injected events and model assumptions. IOS57 v5918 behaviour remains open.
[Stock measurement](../../research/d2x-build-baseline.md) · [Fixture results](../../research/fixture_sim/README.md)

## Entry and one-use admission

Select the outer `DI_EmulateIoctl` hook. It receives the typed input and output
extents and the DI fd before forwarding to base DI. The earlier fit study
proposed the inner `DI_EmulateCmd` site. A future hardware observation at the
outer hook applies only to that hook and its recorded caller context. The
intervening base implementation and equivalence of the callers remain unknown.
[Hook declarations][hooks] · [Outer dispatch][outer] · [Earlier fit study](../../research/direct-dip-tcp-probe-fit.md)

**Source-verified collision review.** The outer switch handles cover and status
requests and forwards its default to base DI. Its five cases alone cannot
identify a free command. GX uses 0x8D for the unencrypted read itself. The
pinned d2x command table assigns 0xF0–0xF6 to offset, crypt, WBFS and reset
controls, 0xF9 to the fragment list, 0xFA to mode, 0xFE to saving configuration
and 0xFF to a custom DVD command. GX also defines 0xFE for Hermes WBFS mode.
The fragment and custom handlers have side effects. Exclude those encodings
from arm admission. The proposed local arm request has no assigned target
opcode. Review any concrete fixture selector against the pinned client, both
dispatch paths and their fallthrough before integrating it. An unlisted value
does not establish a private IOS57 ABI. [d2x commands][commands] ·
[Inner dispatch][inner] · [Outer dispatch][outer] · [GX command definitions][gxcmd]

1. Stage a fresh eight-byte tag and 16-byte challenge through a separate local
   arm request. Validate its version, instance, slot, builds, DI-side fd,
   intended unencrypted read command, byte length, word offset and aligned
   exclusive output allocation and extent. Copy the inputs and return a
   correlated arm receipt. Retain the observed output identity between calls.
   Use only the validated live buffer for writes. Target address translation
   and preservation of the discriminators require evidence.
2. Dispatch depends on a matching receipt, safe arm handback and evidence that
   at least one discriminator (tag or exclusive output identity) survives.
   An uncertain receipt ends dispatch. At the outer hook, ordinary traffic takes
   the stock path and preserves the arm. For a recognisable attempt, check the
   complete 32-byte read input and bound tuple and spend the arm in one
   serialised decision. A valid match enters once. A malformed match rejects
   terminally before any media or network access. Retain the spent binding and
   reject subsequent recognisable duplicates after either outcome.
3. Publish separate arm, rejection and caller-entry evidence. Record the actual
   executing TID, hook, tag, instance, slot and build identity before the first
   network submission. [GX read][gxread] · [Fixture ownership and admission](../../research/ios-ipc-ownership-and-fixture.md)

## IPC ownership and the measured network path

Use one outstanding operation and at most **64 network IPC submissions in
total**, counting setup, retries, every fragment and cleanup. Allocate a
different completion address on each submission, including a failed attempt.
Before issuing work, reserve submissions for each applicable close, including
obligations the new acquisition could create. Stop before another submission
would spend that reserve. Keep every used slot reserved through confirmed
producer retirement and the applicable safe termination boundary.

**Source-verified sizing basis.** The pinned 32-bit ARM packed `ipcmessage`
has three four-byte header words and a union reaching byte 32. HAI explicitly
aligns its full async callback object to 32 bytes and compares the dequeued
address with that object. d2x USB uses the smaller two-word `areply` view.
Reserve one complete 32-byte record per submission, each on its own 32-byte
cache line. The pool alone costs **64 × 32 = 2,048 static RAM bytes**, leaving
13,184 of the measured trailing bytes before other additions and padding.
Verify record size, pool alignment, stride and total extent in the selected
build and map. The packed type alone supplies no cache-line alignment.
[d2x layouts][ipc] · [HAI layout][haiipc] · [HAI allocation][haicb] · [HAI wait][haiwait] · [USB completion dispatch][usb]

**Target assumption.** A delivered completion must identify the caller storage
for that submission. Address uniqueness cannot prove that IOS57 returns it.
Match the queue word to the active slot, validate the reply command and read
the operation-specific result. An internal ledger index supplies no returned
serial. Inspect the bounded private queue before consuming a result or changing
bindings. Classify an old slot separately from an unknown address or timer.
Never apply an old result to the active acquisition. Multiple or conflicting
results for one loan leave the loan unresolved. Preserve evidence and
quarantine on ambiguity. Account for queue capacity, timer provenance, lost
delivery and the ordering required between inspection and consumption.

Include the actual NCD wired-link check, SO open, KD open/startup and close,
SO startup and host-address readiness, socket creation, one connect, fragmented
send/receive and eligible closes. Distinguish submission status, completion
result and service output. Record unresolved acquisition, known ownership and
confirmed release. Zero can be a valid descriptor. Keep the SO process fd and
socket in their own namespaces. Close the socket before its SO fd and associate
each close with the original acquisition. [Operation and control layouts](../../research/direct-dip-tcp-probe-fit.md#ios-operations-and-their-evidence)

Use terminal one-shot quarantine for blocked, ambiguous or unresolved work.
A submission can block inside the trap, preventing DI return and local timer
handling. Publish intent before the trap. A bare error can leave an acquisition
unresolved. Never guess a descriptor, retry an ambiguous close or rearm.
Preserve paths, buffers, vectors, message storage, queues, timer backing and
dependent resources while a producer might use them. A late result may refine
the ledger while the first failure stays latched.

## Receive handoff and deadlines

Send exactly the tag followed by the challenge (24 bytes). Accumulate short
sends and receives against the remaining length. Reject over-counts and
premature EOF. After each matching receive completion, require retirement of
producer access to the returned range. Use dedicated 32-byte-aligned,
whole-line-owned controls, vectors, reply storage and transfer scratch. Clean
ARM-written inputs and vectors with `os_sync_after_write` before submission
and relinquish output lines without dirty private data. After retirement use
`os_sync_before_read` on the completion and output ranges before consuming
them. Validate the positive count against the remaining extent and copy exactly
that many fresh bytes from synchronised scratch, even for a one-byte fragment.
Include these calls and copies in the link. Verify all 28 reply bytes before
expiry: the echoed 24 bytes followed by the peer-assigned nonzero unsigned
big-endian 32-bit connection ID. Latch the bytes and ID before cleanup for
correlation with the selected peer's accept, endpoints and frame. Physical
visibility and completion-implied retirement remain target assumptions.
[WBFS_Read cache calls][wbfs] · [Wire format](../../research/tcp_peer/README.md#experimental-wire-format)

| Interval | Sizing policy |
| --- | --- |
| Bring-up | 30 seconds from before the first NCD open through checked SO readiness, including retries. |
| Connection | Five seconds from readiness through socket creation and one connection. No reconnection. |
| Exchange | One absolute five-second deadline from before the first send through complete caller verification. Partial progress cannot extend it. |
| Cleanup | Five seconds starting once at verification or abandonment, including all eligible closes. |
| Independent observer | Start observation before arming. Use a 35-second progress checkpoint and a 55-second hard watchdog cutoff outside the blocked DI caller. |

Timer words prompt a fresh phase and clock check. Check matching completions
and final verification against elapsed time, with equality late. Preserve the
first failure across late arrivals and cleanup. Use unsigned wrap-safe deltas
from a single epoch with a justified observation gap below half the counter
range. A missing gap bound makes timeliness unknown. Clock ABI, units, rate
and maximum observation gaps require target evidence. Publish DIP progress,
last known ownership and recovery state for an external observer. Recovery
initiation leaves the old instance and I/O outstanding until their end is
independently confirmed. A blocked caller cannot publish a subsequent return.

## Evidence and verdicts

Measure the ARM writer for a bounded compact binary trace. Give each record an
instance, run identity and increasing sequence. Publish caller entry and gate
result, operation intent before submission, raw submission and completion,
phase/ticks, accepted byte ranges, acquisition and release, deadline and first
failure, exact verified reply and ID, cleanup or quarantine, and the terminal
return status and sequence. Preserve enough records for fragmented transfers
and cleanup. Budget intent, submission and completion for every admitted
operation, with capacity reserved for failure, verification and terminal state.
Record trace exhaustion and stop before starting work that cannot be recorded.

Write payload first, clean its lines and order/drain writes before publishing
and cleaning the aligned commit sequence. Account for the bytes and alignment
of commit and payload storage, including any fixture-provided extent. Keep
reader-owned lines disjoint. The reader must be able to detect torn, stale,
missing and conflicting records. Freeze publication at terminal return.
Formatting, independent capture and full transcript evaluation belong outside
DIP. The measured writer and gate must remain reachable under varying fixture
inputs. A successful-return stub or a constant synthetic result cannot stand
in for any required ARM path.

Preserve the three independent [ADR 0004 verdicts](0004-pc-only-fixture-simulation.md#verdicts).

- **Exchange verification** requires timely full caller verification and matching
  peer evidence. Later cleanup failure preserves the latched exchange.
- **Baseline verdict** additionally needs caller and instance identity, timely
  readiness, both safe PPC handbacks and synchronous DI return ordered before
  the independently captured actual GX pre-helper marker for a pass. Preserve
  the separate attributable failure, positive skip/rejection and indeterminate
  outcomes when applying the baseline evidence rules.
- **Safe termination** requires accounting for every live loan and acquisition
  through confirmed cleanup or independent confirmation that the old IOS
  instance and its relevant I/O ended. A watchdog decision cannot release them.

GX request lifetime for arm and read, final PPC IPC completion instrumentation,
independent capture and the actual pre-helper marker are future hardware fixture
dependencies. Their interface inputs may be explicitly synthetic for sizing.
This authority covers only DIP-side publication and recovery-state contracts.

## Implementation and execution boundaries

After independent review and merge, a separate task may write original probe
code, a narrow integration patch, minimal Make targets and scripts, focused
PC-side validation, a dedicated manual hosted sizing workflow and documentation
of inputs, provenance, assumptions and measurement procedures. Apply the
reviewed patch only to disposable extractions of public d2x revision
`33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`. Review per-file licences and
compatibility with GPL-3.0-only contributions before copying code or publishing
the patch. Prefer original code using reviewed interfaces. Stop and report
unresolved provenance restrictions.

Reuse the established Make measurement infrastructure, verified devkitARM r32
Buster archive (SHA-256
`7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6`)
and stock dependency procedure. Keep the stock workflow intact. The separate
sizing workflow may compile only after owner approval of the exact reviewed
commit, by manual dispatch on an ephemeral hosted runner. Follow the stock
checks for repository, owner and triggering actor, develop ref, workflow path,
event/workflow/checkout SHAs and first run attempt. A rerun needs a fresh
approved dispatch. Pushes, PRs and merges must never trigger compilation.
Public dependencies may be provisioned on the runner. Compile unprivileged
in fresh PC scratch. [Stock approval and build procedure](../../research/d2x-build-baseline.md#hosted-initiation-and-evidence)

The scope excludes GX or libogc implementation or compilation, the external GX
observer, local dependency or toolchain installation, proprietary IOS firmware
or console data access, hardware execution, cIOS packaging or installation,
production NBD, upstream repository changes and repository settings or execution
approval changes. Preserve the stock flags, linker regions and ordinary DIP
functionality. The completed Python simulation stays outside this task.

## Measurement, acceptance and stop conditions

1. Build an unmodified control and one complete modified DIP in separate fresh
   extractions using the same inputs, toolchain, flags and environment. Record
   revisions, patch and input hashes, resolved dependencies and commands.
   Compare the control's original ELF, map and LOAD spans with the recorded
   stock baseline. Report and stop on unexplained material differences.
2. Inspect the modified original ELF, map, LOAD file and memory ranges and
   retained call sites. Measure each occupied span from its region origin to
   its highest allocated exclusive end, including gaps and memory-only BSS.
   Report trailing space and deltas against the control. The executable starts
   at `0x13800000` and must end at or below `0x13802000`. Static RAM starts at
   `0x13802000` and must end at or below `0x13842000`.
3. Reconcile both spans across ELF, map and LOAD evidence. Identify changed
   and newly retained functions, compiler helpers, literals, interworking
   veneers and padding. Inventory the entire completion pool, other static
   buffers, data and trace storage. Report compiler-visible stack frames and
   unresolved call depth. Trace all required paths from the hook through the
   real calls, including rejection, failure, cleanup, quarantine and return.
   Account for every material dependency and verify ordinary stock paths survive.
4. Accept static fit only with a matched control and all of the above evidence.
   Stop and document compilation failure, overflow, elimination of a required
   path, an unjustifiable necessary ABI assumption, or any need to remove
   functionality, change flags or enlarge a region. Retain validated text
   evidence including failure diagnostics. Publication of binaries or raw
   upstream material requires separate provenance approval.

A documented no-fit is a valid outcome and may warrant investigating a
separate IOS service. A successful link establishes static fit only. Runtime
stack margin, permissions, IPC behaviour, cache coherency, networking and
recovery still need target evidence. R0 remains open. The hardware recovery
gate remains closed.

[hooks]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.h#L103-L116
[outer]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L675-L763
[inner]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L221-L673
[commands]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/ioctl.h#L23-L57
[gxcmd]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L9-L30
[gxread]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/usbloader/wdvd.c#L258-L277
[ipc]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/ipc.h#L47-L104
[haiipc]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/include/ipc.h#L33-L103
[haicb]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L268
[haiwait]: https://github.com/ymweiss/HAI-Riivolution/blob/e67de6991ec24252acadd2c4b0918f21e83c2528/libios/source/network_wii.c#L452-L480
[usb]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/main.c#L162-L249
[wbfs]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/wbfs.c#L69-L98
