# ADR 0006: Authorise an experimental DIP adapter sizing link

- Status: Accepted by the owner. Implementation authority takes effect after independent review and merge of this ADR.
- Date: 2026-11-27
- Decision owner: Lloyd Smart

## Decision and rationale

Measure whether one complete DIP-to-service diagnostic adapter fits the
unchanged stock DIP linker regions. This is a PC-only sizing decision. It
authorises documentation now, a separate implementation task after review
and merge, and compilation only upon a fresh owner approval of the exact
reviewed, merged implementation revision.

**Experimentally verified on PC.** The stock executable occupied 6,708 of
8,192 bytes, leaving 1,484 bytes. Static RAM occupied 246,912 of 262,144
bytes, leaving 15,232. The complete ADR 0005 direct probe attempted 12,128
executable bytes. The map corroborated a 3,936-byte overflow. There was no
modified original ELF from which to measure final RAM occupancy. Its
non-network object and assembly gate contributed 1,774 + 16 = 1,790
relocatable executable bytes. [Matched control and failed link][result]

**Hypothesis.** The placement study estimated 2,150–2,460 adapter bytes
using the old local objects and analogies to stock client functions. Only a
matched link can resolve the effect of replacing the writer, retaining new
helpers, alignment and interworking. An installed module, a FAT-hosted worker
and a separately linked MLOAD-started worker all need this same adapter.
Measuring a service alone leaves the common 1,484-byte constraint unanswered.
A combined experiment would also require a placement decision. MLOAD remains
the preferred worker research candidate. Its declared loading area still
requires evidence of exclusive backing, permissions, process identity,
bootstrap, readiness, coexistence and reload behaviour. Runtime architecture
and worker implementation remain separate decisions. [Placement comparison and estimates][study]

**Source-verified.** MLOAD declares 512 KiB for loading. Its
`MLOAD_GET_LOAD_BASE` handler advertises that extent to clients. Neither
`Elf_Load` nor `Elf_Run` reserves a private share for this worker. This is
why an apparently available loading address cannot serve as an allocation
in the sizing contract. [Storage declaration][mlstart] · [MLOAD dispatch][mload] · [Loader functions][elf]

## Admission stays at the outer DI hook

Use the refined ADR 0005 outer `DI_EmulateIoctl` admission and live output
formats. Keep ordinary classification, the one-use claim and an independent
writer in DIP so that an external reader can identify the actual caller even
if the first service trap blocks. Candidate arm selector 0xF7 is unassigned
in the inspected GX definitions and d2x dispatch tables. Collision in opaque
base DI, live delivery of both envelopes and identity of the executing caller
on IOS57 v5918 are unresolved. [Pinned outer dispatch][hook] · [Selector review and fixture layouts][gate]

1. Before arm, independently provision the separate arm and read reservations,
   the exclusive 32-byte output and their physical extents, whole-line
   ownership, translation and lifetime through final IPC handback or confirmed
   recovery. Check alignment, non-wrapping bounds and disjointness from one
   another, the live ioctl envelope and other users. Synchronise only checked,
   fully owned lines, rounding the original start down and end up.
2. The first 0xF7 spends the arm opportunity. Validate the complete private
   96-byte snapshot including version, instance, slot, builds, fd, read
   selector 0x8D, length 32, word offset, endpoint, tag, challenge and zero
   reserves. Bind it to the provisioned allocations and output. Malformed arm
   is terminal. Return the correlated ADR 0005 receipt. GX may issue the read
   only after checking the receipt, safe arm handback and preservation of at
   least one allocation identity at this hook.
3. After binding, identify candidates by input start in either reservation or
   the bound output address. With neither identity resume the original switch,
   arguments, default and return behaviour. Leave foreign input, cache lines
   and claim untouched. An exact synchronized arm replay from the arm
   reservation with the bound fd, output and extents preserves an unspent
   read. It grants no new arm. Publish the validated binding once. Replay
   checks use the immutable binding and observe the spent state atomically.
   All other candidates compete for the same atomic claim before read
   validation. Keep cache calls, service IPC and waits outside any admission
   lock. Only the winning caller writes the read journal.
4. For the winning candidate, require the
   bound fd, exclusive live output and complete eight-word read from its own
   reservation, including the selector word, length, offset, tag and three
   zero words. A malformed candidate rejects terminally, including bound
   output with foreign input, without touching that input. A spent binding
   rejects duplicates without publication or renewed work. A claimed read
   never falls back to media. On a valid claim, commit hook entry, actual
   executing DI TID and observed DI fd, build/instance, claim and tag before
   attempting service IPC.

## Service provision and fixed mailbox

**Sizing assumptions.** A variable synthetic fixture supplies checked registration
of one exclusive path and ioctl selector, worker readiness for this build and
instance, authorised opener and one-use session, a common clock epoch, and
disjoint ARM-visible whole-line allocations. Bind the intended DI context,
service, claim, session and mailbox through independently established credentials
or exclusive mapped access. Exclude competing openers, prefix collisions and
aliases. A matching tag, path, fd or asserted TID only correlates records.
On reload invalidate the entire provision. IOS57 service name, PID, mapping,
rights, free queue slots and registration order remain unresolved. Stop if
a required binding cannot be represented independently. [Placement study][study]

Use one fixed-size ioctl with separate persistent, 32-byte-aligned request
and reply allocations. Version 1 defines **160 request bytes and 192 reply
bytes**, five and six whole lines respectively. Offsets are decimal bytes
from each base. Integers are unsigned big-endian unless marked signed.
Adjacent fields listed in one row follow the stated order. Zero all reserved
bytes and reject any nonzero reserve, unknown field value or inexact extent.
Treat the wire format as bytes, independent of compiler struct padding. The
operation value below belongs to this synthetic envelope. The outer ioctl
selector and open path come from the provision.

| Offset | Width (bytes) | Common prefix in both messages |
| ---: | ---: | --- |
| 0 | 2 + 2 | Version 1, operation 1 (one diagnostic exchange) |
| 4 | 4 | Total length of this message |
| 8 | 4 × 2 | IOS instance, IOS build |
| 16 | 4 × 2 | DIP instance, DIP build |
| 24 | 4 × 2 | Service instance, service build |
| 32 | 4 × 2 | One-use claim serial, provisioned one-use open session serial |
| 40 | 4 × 2 | IOS slot, GX build |
| 48 | 8 | Opaque arm tag in wire order |
| 56 | 4 × 2 | Common clock epoch identity, GX instance |

| Offset | Width (bytes) | Request after common prefix |
| ---: | ---: | --- |
| 64 | 4 × 2 | Actual caller TID, observed DI fd (signed words) |
| 72 | 4 × 4 | Bound read selector 0x8D, byte count 32, word offset, exclusive output length 32 |
| 88 | 4 × 2 | Bound local and peer IPv4, network byte order |
| 96 | 2 + 2 | Nonzero peer TCP port, reserved zero |
| 100 | 16 | Opaque arm challenge in wire order |
| 116 | 4 × 2 | Observer start tick, immutable observer cutoff tick |
| 124 | 4 × 2 | Outer start tick, effective outer deadline tick |
| 132 | 4 | Observer lease identity |
| 136 | 24 | Reserved zero |

| Offset | Width (bytes) | Reply after common prefix |
| ---: | ---: | --- |
| 64 | 4 × 2 | Actual worker TID, independently provisioned and checked worker process identity |
| 72 | 4 | Tick presence, bits 0–7 for offsets 76 through 104 in word order, bit 8 for first failure at 112 |
| 76 | 4 × 3 | Bring-up start, checked readiness, connected tick |
| 88 | 4 × 3 | Original exchange start, its absolute deadline, worker verification tick |
| 100 | 4 × 2 | Cleanup start (verification or first abandonment), worker terminal tick |
| 108 | 4 × 2 | First failure class, first failure tick |
| 116 | 4 × 2 | Worker outcome (0 complete success, 1 failure), verified byte length (0 or 28) |
| 124 | 28 | Exact verified frame, including peer connection ID at 148, or all zeros when absent |
| 152 | 4 × 2 | Worker terminal journal sequence, inner disposition (1 safely ended, 2 quarantined) |
| 160 | 4 × 2 | Effective outer deadline echo, lease identity echo |
| 168 | 4 × 2 | DI TID and fd echoes from the accepted request |
| 176 | 4 × 2 | First failure raw signed result, first failing phase |
| 184 | 4 | Tick validity, same nine bit positions as presence at 72 |
| 188 | 4 | Flags: bit 0 first failure raw result present, bit 1 clock/lease fault observed |

Serials, epoch, lease and build/instance identifiers are nonzero fixture
values checked against independent provision. The DI fd identifies the
observed DI caller locally. Only its numeric observation crosses the mailbox.
Service or transport handles, PPC addresses and DI stack pointers have no wire
fields. DIP keeps the live allocation identity privately. The request uses
the last two lines for the challenge, observer lease and outer interval.
The reply accommodates separate phase samples, failure and disposition
alongside exact bytes, even on cleanup failure.

The future worker must bind the actual open session to its own readiness,
permitted opener and mailbox. Validate operation, buffer domains, aligned
extents, exclusivity, no overlap and one-use state before cache access. Acquire
the input lines, copy a private snapshot, check every common field, expected
read tuple, endpoint, tag/challenge and deadline against provision or the
authorised session. Atomically consume the request once. Reject stale,
malformed or replayed input before network work. Its own TID and process
context need independent evidence. DIP checks the same identities against
its snapshot and the worker provision on reply.

The worker owns the existing TCP workload. Send exactly tag + challenge
(24 bytes), accumulate fragments and verify the echoed 24 bytes plus the
peer-assigned nonzero big-endian u32 connection ID (28 bytes). Latch all 28
bytes and time before cleanup. Preserve the worker journal and peer accept,
endpoints, frame and ID for independent correlation. Only the future worker
owns its network queue, up to 64 unique network submissions, handles, socket,
transfer scratch, first failure and cleanup ledger. [Wire format][wire] · [Network ownership][adr5]

For a defined response, the worker publishes the final mailbox after cleanup
or quarantine, cleans the lines, relinquishes all mailbox access and acknowledges
the original inbound message exactly once. A completed ioctl with command 8
and signed result zero defines a reply, including a structured failure.
Any other ioctl result, missing completion or undefined output supplies no
response evidence. A rejected unauthenticated session returns an IPC failure.
A structured failure is possible only on an attributable session with safe
mailbox handoff. A blocked worker may never acknowledge.

DIP requires the exact lengths, expected common prefix (apart from length),
echoes, worker identity and nonzero terminal sequence. At offsets 72 and
184, bits 9–31 are zero. At 188, bits 2–31 are zero. Validate each tick
using its own presence and validity bits.

| Present | Valid | Meaning and validation |
| ---: | ---: | --- |
| 0 | 0 | No value available. The wire word must be zero. |
| 1 | 0 | Preserve the observed or derived word. Epoch, continuity, rate or lease evidence is insufficient to use it for timing. Require the clock-fault flag. |
| 1 | 1 | Value justified in the common epoch. Zero is a possible tick. Check causal order, bounded gap and phase budget for each comparison. |
| 0 | 1 | Malformed reply. |

After checked readiness and connection, the worker latches byte verification
when all 28 bytes pass the echo and ID checks. Every safely issued final
reply after that latch **must** contain length 28, those exact bytes
including the nonzero ID, the original exchange
start and derived deadline evidence, and the original verification sample
with its presence and validity. A later cleanup failure adds its first-failure
evidence and actual cleanup or quarantine disposition. It cannot clear the
latch or replace its samples with cleanup or reply time. Abandonment before
the latch requires length zero, 28 zero frame bytes and both verification
bits clear, even if the remaining bytes arrive later. Retain any exchange
start/deadline already established.

Exchange start and its derived five-second deadline have matching presence
and validity. Recompute the deadline when valid. Sample verification at
the latch, cleanup start at verification or first abandonment, terminal at
publication and first failure when it occurs. A missing sample for an event
known to have occurred requires the clock-fault flag. With a clock fault
preserve previously justified samples and qualify each affected sample
individually. Require causal ordering from outer issue through worker entry,
completed phases and terminal publication to DIP consumption wherever their
times are comparable. Reject a tick marked present for an unreached event.
A verdict requiring a missing or untrusted endpoint or an
unproven interval is indeterminate. Byte verification can still be recorded.
Evaluate surviving intervals, including cleanup start to terminal, against
their original budgets. A justified late sample remains late.

Failure classes are 0 none, 1 session/request validation, 2 network operation,
3 bad peer frame, 4 deadline, 5 ownership/cleanup and 6 clock/lease. Failing
phase codes are 0 none, 1 admission, 2 bring-up, 3 connection, 4 exchange and
5 cleanup. Outcome 0 requires presence and validity masks both 0xFF,
timely phases, verified bytes, safe cleanup and zero failure fields and
flags. Outcome 1 requires a first failure class and phase. Set flag 1 for
any clock/lease fault, including a later fault after another first failure.
Class 6 requires flag 1. Preserve the original first failure in either case.
Set flag 0 if a raw operation result was observed for that failure and
retain the signed word at 176. A premature receive EOF has flag 0 set and
result zero. When no operation result was observed, clear flag 0 and zero
that word. Quarantine, a missed applicable deadline or a clock fault requires
outcome 1. Reject inconsistencies among class, phase, flags, samples,
frame and disposition. A coherent late reply may corroborate worker evidence
or settle ownership. It cannot restore a missed DIP deadline.

## Outer transaction and deadlines

DIP is the sole submitter and queue consumer. One admitted attempt has one
async open, one fixed-size async ioctl on the acquired fd and at most one
eligible async close. A failure can end this sequence early. Reserve the
close slot from entry. At most three actual submissions, one outstanding,
use distinct, never-reused full completion objects, each 32-byte aligned
and 32 bytes long (96 bytes). There is no retry, reopen or reconnect.
Keep path, both mailbox buffers, queue, timer and completion objects alive
in DIP storage. No async operation borrows a PPC buffer or caller stack.

1. Prepare the operation, clean its path/input/completion and relinquish
   whole output lines free of dirty private bytes. Reserve journal capacity
   and commit INTENT with operation, proposed ordinal, completion address
   and acquisition identity. **After publishing intent**, acquire the lease
   and sample time again. On exhaustion publish NOT_ISSUED. This consumes
   neither a submission nor a live loan or close attempt. If eligible,
   mark the loan and any close in flight and enter the real trap. INTENT
   alone leaves issue uncertain to the observer if DIP stalls.
2. Record the raw trap return and issued ordinal whenever the call returns.
   Distinguish documented pre-admission rejection from ambiguous effects.
   Even a negative open can leave a service-side session. Only a uniquely
   matched open completion with command 8 and a nonnegative signed result
   establishes the process fd, including zero. Bind it to the original
   acquisition (IOS instance, session, claim and open ordinal). Never guess
   an fd. An ambiguous or negative result cannot authorise a guessed close.
3. Before open, create the exclusive eight-word queue and arm a one-shot
   timer for the remaining effective interval, with zero repeat and a token
   bound to this queue, epoch and lease, disjoint from completion addresses.
   Check both setup results. On failure record it, stop before submission
   and retain anything whose teardown is uncertain. After an admitted
   submission returns, recheck clock and lease. If already late or uncertain,
   inspect only available words and retain unresolved loans. Otherwise the
   sole consumer calls **blocking queue receive** for the first word.
   Classify it as part of the batch. Refresh clock and
   lease on wake, then drain already available words with nonblocking receives
   through empty. Count the first word toward the eight-word limit. After
   eight, allow one nonblocking emptiness probe. A ninth word, receive error
   or detected saturation is a queue fault. Check lease and time again after
   inspection, even when the first word matched or the timer arrived first.
   Retain any independently established late ownership evidence.

   Accept at most one match to the active completion address after inspecting
   the batch for conflicts. Synchronise its line and validate reply command 8
   and the signed result. An old, duplicate, conflicting or unknown completion
   word invalidates the batch and quarantines affected ownership. Never
   dereference an unrecognised word. A timer word prompts a clock check.
   An identifiable stale notification cannot expire this operation. An
   unprovisioned token or duplicate of the sole one-shot is a queue fault.
   If the current one-shot fires early, drain the batch and record a wake
   fault. Stop issuing and quarantine unresolved loans. Do not block again
   waiting for a consumed timer or grant another interval.
4. Require a justified single delivery, producer retirement and ordered
   visibility for the specific loan. An empty scan and non-reused storage
   identify observations but cannot prove there is no later writer. For a
   defined ioctl reply, keep the active slot **through final cache
   synchronisation, snapshot, full validation and DIP verification
   publication**. The worker can end its outer mailbox access while late
   network I/O still owns worker scratch. Keep the two ledgers independent.
5. Close only a positively held acquisition with the matching session, no
   conflicting loan, available evidence reserve and remaining outer time.
   Bind the sole close attempt before trap entry. Record successful submission,
   unique completion delivery, producer retirement and release of the original
   acquisition as distinct observations. **Synthetic close convention:** only
   the expected close completion address, reply command 8 and signed result
   **zero** report close success. Confirm release against this acquisition
   after retirement and conflict checks. Every unexpected positive or negative
   result leaves release unresolved unless the applicable interface separately
   establishes it. Timeout, fd-number reuse or an ambiguous close cannot
   authorise release, guessing an fd or retry. IOS57 needs independent evidence
   for this result convention, retirement and actual release.
   Quiesce the timer, check stop/destruction and
   drain boundedly. Retain queue identity and backing until all producers
   and deliveries retire. [IPC loan, timer and descriptor analysis][ipc]

**Source-verified public interfaces.** The pinned d2x queue and timer
declarations and USB dispatch support a blocking receive. In the StarStruck
comparator a waiting receiver sleeps on an empty queue, and timer expiry
sends its word nonblocking. Saturation can lose timer or completion
delivery. An empty observation ends one scan. A producer can enqueue again
immediately afterwards. [Queue and timer declarations][calls] ·
[USB receive loop][usb] · [Queue receive][queue] · [Timer delivery][timer]

**IOS57 assumptions.** Blocking gives the scheduler an opportunity to run
the worker. Worker scheduling, delivery and DIP resumption have no verified
bound. Recheck clock and lease before sleeping again after an irrelevant
wake, and only while the current wake source remains armed. If notification
is lost the caller can remain blocked, including past the outer deadline.
The independent observer can record the cutoff and abandon the experiment
while the loan remains live. The timer can wake a queue receiver only. It
cannot interrupt a blocked submission trap. Neither scheduling nor a bounded
drain proves that a producer has retired.

| Clock owner | Start and fixed limit |
| --- | --- |
| Independent observer | Start before arming. Check progress at 35 seconds, hard cutoff at 55 seconds from the same start. |
| DIP | Sample before the first service open. The effective absolute end is the earlier of start + 50 seconds and the existing observer cutoff. Open, waits, worker execution, reply handoff, validation and eligible close share it. |
| Worker bring-up | From before first NCD open through checked SO readiness, 30 seconds total. |
| Worker connection | From readiness through socket creation and one connect, five seconds. |
| Worker exchange | From before first send through verification of the complete frame, one absolute five-second deadline across fragments. |
| Worker cleanup | Start once on verification or first abandonment, five seconds for all eligible cleanup. |

Use one independently established continuous IOS clock epoch and stable
rate for comparable DIP and service samples. For the synthetic fixture use
the prior nominal 243 MHz / 128 counter and round each tick budget down.
On u32 ticks compare unsigned elapsed time modulo 2³² with the budget,
requiring every interpreted interval and observation gap to be independently
bounded below half the range. Derive the remaining lease at DIP start by
subtracting elapsed time since observer start from the checked 55-second
budget. Clip 50 seconds to that remainder before adding it to the start.
Verify the original exchange deadline from the worker's start in the same
epoch. At every final issue, consumption, verification and close decision
check lease and time. Equality is late. Progress, early timer delivery and
late completions renew neither boundary.

The separate reader-owned 32-byte lease line contains eight u32 words:
live, lease identity, IOS instance, clock epoch identity, two tag words,
observer start tick and hard cutoff tick. Publish identity and ticks before
live, keep them immutable, retire live by cutoff and never revive the lease.
DIP synchronises and checks a consistent snapshot on each time decision.
Missing, expired, incoherent or stale lease, epoch reset or an unbounded
sampling gap prevents a timely verdict and new submissions. Quarantine
outstanding obligations. A frozen live flag cannot establish freshness.
Mapping the independent observer clock to these ticks, enforcing the cutoff
during stalls and bounding scheduling gaps require future observation on
IOS57. A software timer cannot interrupt a blocked submission or force a
worker reply. Even the last clock sample leaves a scheduling and trap-entry
gap. [Clock and watchdog evidence][ipc]

## Independent evidence and PPC handback

| Observation | Evidence required |
| --- | --- |
| Worker verified the TCP exchange | Committed worker entry, original exchange epoch, timely full verification, and matching peer transcript for the same accept, endpoints, tag, challenge and connection ID. |
| DIP independently verified the service reply | Attributed hook entry and unique retired ioctl completion, checked response, exact frame and ID, and DIP's own timestamp and two deadline verdicts. |
| The synchronous DI read returned before GX cleanup | Safe handback of arm and read, independently correlated final PPC IPC completion and observed synchronous read return before the actual GX pre-cleanup marker. |
| Safe termination | Independent outer and inner disposition for every acquisition, producer, message and buffer loan, or confirmed end of the old IOS instance and relevant I/O. |

For a validated frame DIP commits its verification group **before any outer
close intent or submission**. Bind the actual hook and DI TID/fd, build, instances, session
and claim through immutable entry records. Include the verified 28-byte
frame and decoded ID, worker terminal sequence, original exchange deadline,
effective outer deadline, DIP's post-validation sample and its verdict
against each deadline. Preserve the evidence if the close blocks.

**Every eligible close needs a committed DIP decision before close INTENT.**
For a validated frame the concluding verdict of the full eight-record group
establishes DIP byte verification, including when timing is indeterminate.
Otherwise commit the shorter pre-close decision below. A checked worker
failure with zero length establishes absent byte evidence. A uniquely
retired ioctl with undefined output (including a nonzero result) establishes
no defined reply. A retired ioctl with malformed or unverifiable output
records unsuccessful validation and its specific rejection reason. Attribute
worker evidence only from a fully validated response. If failure prevented
ioctl issue after a known open, record why the ioctl was skipped, citing
NOT_ISSUED only if intent was announced. No ioctl loan arose in that case.
Close still requires a live original acquisition, trusted queue, remaining
deadline and no conflicting loan. Uncertain issuance or retirement bars it.

Commit applicable first failures and the final validation decision before
releasing the active validation slot or announcing close. A reader who sees
close INTENT can therefore distinguish absent or rejected evidence from a
validation still in progress. Latch the first failure on each side. Attribute
a network failure only with actual worker entry, specific failure evidence
and independently healthy listener and wired controls.

A worker that verified the frame and lost its acknowledgement can establish
only the first observation. A stalled close can leave the first two established
while DI handback and safe termination remain open. A reply delayed by worker
cleanup may preserve timely worker verification while DIP records a missed
exchange deadline even within its outer budget. An end-to-end pass needs
both timely verifications, timely readiness and outer transaction, the
matching peer and caller identities, and actual GX return ordering. Report
resource termination separately. Missing evidence leaves its own observation
indeterminate. [Fixture verdicts][adr4] · [Service handoff study][study]

Only DIP writes the validated live PPC output. After final checks, write and
clean the bound ADR 0005 status line (tag, instance, terminal sequence, raw
status, first failure, quarantine and TID), commit the corresponding terminal
record and freeze publication before returning in the original DI context.
If failure is safe to hand back, retain any unresolved DIP-owned storage in
one-shot quarantine. If a producer could still access PPC-owned memory or
safe evidence freeze is impossible, leave the caller pending. Do not write
to foreign or invalid output on rejection. Retain both PPC internal IPC
requests, wait identities and buffers through their respective final reply
handling. Terminal intent, an arm receipt and a wrapper return alone cannot
prove actual handback. GX final IPC instrumentation, independent capture and
the marker immediately before `DeinitNetwork` calls `net_wc24cleanup` are
future fixture responsibilities. An ambiguous arm or read handback stops GX
progression. [PPC lifetime and marker][ipc] · [GX cleanup site][gxnet]

## Bounded DIP journal and static budget

Select **48 immutable 32-byte records**. Each has u32 sequence at 0
(starting at 1), u16 event at 4, u8 operation at 6 (none/open/ioctl/close),
u8 actual or proposed ordinal at 7 (zero when inapplicable), u32 DIP
instance at 8, u32 claim at 12 (zero before claim), u32 writer tick at 16
and three event-specific u32 payload words at 20, 24 and 28. All fields
are big-endian. Frame fragments preserve raw wire order. Join sequences
to the immutable arm identity, caller and session within this instance.
Ignore uncommitted records. A verification group is evidence only through
its concluding verdict record, which references its first sequence.

| Maximum records reserved | Contents and bound per one-shot transaction |
| ---: | --- |
| 8 | Arm decision/receipt or rejection, tag and instance/build binding, endpoint and tuple, actual hook and caller TID/fd, session and claim. Pack correlated identities in payload triples. Only one arm and one claim can publish. |
| 4 | Lease/epoch, observer bounds, outer start/end and queue/timer setup. Publish each once. |
| 15 | Five per operation: INTENT, NOT_ISSUED or raw SUBMITTED, matched completion (address, command, raw result), loan disposition and acquisition/close disposition. No operation retries and no per-poll writes. Reserve five for an eligible close at entry. |
| 8 | One pre-close decision per claim. Use all eight for a verified frame or at most three for absent evidence, rejected output or an unissued ioctl. |
| 3 | First outer failure, first queue or lease anomaly and first validated worker failure. Pack class, phase, raw-result presence and failure-tick presence/validity in one word. Store raw signed result and failure tick in the other two. Each latches once. |
| 8 | Late ownership reconciliation up to once per operation, timer/queue retirement, remaining loans and acquisition, quarantine or safe disposition, output status and terminal return/pending decision. |
| 2 | Capacity fault and terminal contingency. Preserve these even on early admission failure. |

These maxima sum to 48. Ordinary forwards, replays, duplicates after spend,
wakeups and repeated faults consume no records. Summarise a conflict once and
stop issuing. Check the remaining worst case before each intent, preserving
the applicable close, verification, first-failure and terminal reserves.
If the required group cannot fit, record exhaustion and stop before lending
storage. A blocked trap leaves its already committed prefix readable.

The eight verification records have room for the following payload triples,
in order. The first three carry frame bytes 0–11, 12–23 and 24–27 (zero
padding). The fourth carries the decoded ID, worker terminal sequence and
entry sequence. The fifth carries worker exchange start, deadline and
verification tick. The sixth packs worker outcome and the two flags from
188 into its first word, inner disposition and the nine presence bits into
its second, and verified length and the nine validity bits into its third
(low byte for outcome, disposition or length, respective flags or mask
starting at bit 8). The seventh carries DIP's post-validation tick and the two
deadline ticks. The eighth carries the first sequence of this group, caller
entry sequence and packed verdicts (exchange in bits 0–1, outer in bits
2–3, each 0 indeterminate, 1 timely or 2 late). These verdicts describe
DIP's validation time. A timely worker exchange separately requires the
worker's own trustworthy interval and peer evidence.

The alternative uses the same eight-record reservation. Its first record
identifies the ioctl disposition (skipped, announced but unissued, proven
pre-admission rejection, retired with undefined output, validated failure
without bytes, or retired with rejected output). Its other two words
reference the decisive operation record and the loan disposition record.
For a skipped ioctl use the original open acquisition as the operation
reference. For a never-issued ioctl use zero for the loan reference.
The op records supply the actual submission result or completion address,
command and result when observed. For a validated byte-absent worker
failure only, add one record with worker terminal sequence, inner disposition
and its first-failure record sequence. A malformed or undefined reply
contributes no worker fields.

Commit the shorter group's final record last. Its three words carry the
first group sequence, the first outer failure sequence (zero if none),
and a packed decision. Use bits 0–1 for DIP verification (0 absent,
1 unsuccessful), bits 2–3 and 4–5 for the exchange and outer time verdicts
in the encoding above, and bits 6–31 for the specific skip, IPC failure
or validation reason. Its header tick is DIP's decision sample. Use an
indeterminate verdict wherever the clock or a trusted deadline is missing.
The verified and unverified paths are mutually exclusive. Even allowing
all 40 records outside this reservation, their bounds are 40 + 8 = 48
and 40 + 3 = 43. Both retain the five-record close reserve.

Store one u32 FNV-1a check over the 32 wire bytes of each record in a
separate array. DIP is the sole writer. Write and clean payload and check,
order and drain both writes, then advance and clean the separate aligned
commit line (instance, highest contiguous sequence and tag, remaining words
zero). The reader acquires commit before acquiring immutable records and
checks. Verify sequence, identity and check, compare repeated captures
and reject gaps, tears, stale or conflicting snapshots. The reader writes
only its disjoint lease line. Freeze on terminal publication, including
safe diagnostic return or terminal quarantine. Late evidence after freeze
belongs to independent observation. Physical ordering, visibility and
reader access are target assumptions. Detailed network operations and
ownership stay in the future worker journal. [Publication precedent][gate]

| Selected DIP storage | Bytes before placement |
| --- | ---: |
| Separate persistent request and reply, aligned to 32 | 160 + 192 |
| Three full completion lines | 96 |
| Eight-word queue backing and separate persistent path line (bounded NUL-terminated path) | 32 + 32 |
| Journal payload and check array, each aligned to 32 | 1,536 + 192 |
| DIP commit and reader-owned lease on separate lines | 32 + 32 |
| **Subtotal** | **2,304** |

Measure the remaining provision, copied arm, identity bindings, claim gate,
acquisition and loan ledger, timer/queue state, snapshots, constants,
stack and all alignment separately. The subtotal is a design allocation.
Fixture-owned PPC arm/read/output allocations and worker storage have their
own owners. Neither can supply space on the hooked caller's stack.

## Failure, quarantine and fixture coverage

| Event | Required disposition |
| --- | --- |
| Open acknowledgement lost, including after service acquisition | Pin path, completion, queue and session. Record possible open with unknown fd. Close needs a positively identified acquisition. |
| Worker never scheduled, or verified the peer but DIP received no reply | Preserve pending RM request, mailbox and any loans. Use worker and peer evidence independently if available. Silence alone cannot locate the failure. |
| Outer mailbox retired, inner network producer still live | Worker may return a checked failure/quarantine reply only after isolating all late writes to its own storage. DIP accounts for its fd/close. Worker retains scratch, network handles, queue and completion objects. |
| Malformed, conflicting or late response | Reject invalid data, latch first failure, retain unresolved loans. A uniquely attributable late result may refine ownership before freeze. Only a proven retired mailbox and known fd may proceed to eligible bounded close. |
| Close blocked or disposition ambiguous | Preserve the committed pre-close decision, original acquisition and every possible loan. No second close even on apparent fd-number reuse. |
| Budget exhausted before an operation | Publish NOT_ISSUED for announced intent, keep the prior ownership ledger and quarantine outstanding obligations. Never issue expired cleanup. |

The worker must make progress on its own stack with independent RM and
network completion queues. It cannot rely on a callback into the held DI
request, the occupied RM dispatch queue or GX launch progress. Neither an
outer timeout nor an inner timeout releases backing storage. A diagnostic
failure handback cannot rearm the instance or resume a claimed read on
media. The independent watchdog bounds abandonment decisions. Recovery
requires independent confirmation that the old IOS instance and relevant
I/O have ended. [Scheduling and late ownership][study]

Require focused native PC regressions for the table above, both queue
delivery orders, equality, stale leases, pre-issue expiry, bogus opener or
stale session/build, fd zero and reuse, full queue, torn publication and
the pre-close decision visible during a stalled close. Exercise both
journal forms, a known open followed by a skipped ioctl, zero EOF versus
no raw result, and exact zero versus unexpected signed close results. Drive
verified bytes followed by cleanup failure, clock loss before or after the
byte latch, missing timer delivery, malformed and timely-worker/late-DIP
replies. Preserve
ADR 0005 admission, untouched foreign-page, split-line and replay cases.
Assert independent verdicts, no borrowed PPC pointers, and immutability
across duplicates, timeout and late completion.

## Implementation, execution and interpretation

After independent review and merge of this record, a separate PC task may
write original adapter code, a narrow integration patch for disposable
pinned d2x extractions, the complete outer IPC client and DIP writer,
focused native fixtures, necessary Make targets, measurement scripts, a
dedicated manual sizing workflow and documentation of the synthetic
interface and target assumptions. Reuse the existing measurement and
validated publication infrastructure. Retain the completed direct-DIP probe,
ADR 0005 result, stock workflow and ADR 0004 simulation. Worker code,
MLOAD bootstrap, GX observer, upstream changes, proprietary firmware,
packaging, installation and hardware access are outside this decision.

**Implementation patch provenance.** Before copying any upstream code or
publishing the integration patch (including the implementation PR), review
provenance and licence per file. Identify reused original Wii NetDisc code
by path and revision. Inventory each upstream input, its notice and all
upstream context reproduced in the diff. Assess compatibility with the
project's GPL-3.0-only contributions and the right to publish those lines.
Report unresolved redistribution restrictions explicitly and withhold the
affected copy or patch publication until resolved. The implementation PR
must meet this requirement independently of any later sizing run. [ADR 0005][adr5] ·
[Direct probe per-file inventory][provenance]

The ARM client must retain reachable real open/ioctl/close traps, queue
wait and clock checks, cache handoff, full response checks, ownership,
rejection, failure, quarantine and publication. Vary external provision and
reply bytes in native fixtures. A mocked ARM operation or constant success
reply invalidates sizing. Stop if implementing the interface would require
weakening a predicate or asserting an unsupported necessary ABI.

1. **Execution gate.** Compiling either input requires a new owner-approved
   manual dispatch for the full reviewed merged implementation SHA. Use an
   ephemeral hosted Ubuntu 24.04 runner and the established unprivileged
   build procedure. Check event type, exact repository `lloydsmart/wii-netdisc`,
   owner, actor and triggering actor `lloydsmart`, ref `refs/heads/develop`,
   exact dedicated workflow path/ref, run attempt 1 and equality of approved
   40-hex SHA, event SHA, workflow SHA and checkout HEAD before provisioning.
   Pushes, PRs and merges cannot compile ARM. A rerun requires a fresh
   approved dispatch. [Hosted control procedure][stock]
2. **Matched control.** Build one fresh unmodified stock control and one
   complete modified adapter in separate disposable extractions of d2x
   `33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7`. Verify the devkitARM r32
   Buster archive SHA-256
   `7ca6fafef13876e2e565b4421e2d240c4532c7f0d15f4ffe1e2ed3c485748cd6`.
   Use identical stock recipes, flags, toolchain inputs, environment and
   linker regions. Record revision, input/patch hashes, tools and environment.
   Require the historical original ELF SHA-256
   `70623d5af228957d031691e32229b47e5bdc0b950e158d795daaba1125b7e63f`,
   the map SHA-256 `2edd3b7e30bfef7d4e766222d8c67c681771d4db89101971c83029f9b5c5a1ff`
   after normalising only the toolchain directory prefix, and both control
   spans above. Preserve raw map identity. Stop on control mismatch. [Control evidence][result]
3. **Extent and path review.** Preserve executable
   `[0x13800000, 0x13802000)` and static RAM `[0x13802000, 0x13842000)`.
   Reconcile original ELF, map, LOAD virtual/physical starts and file/memory
   ends, origin-to-highest-end occupancy, trailing space and deltas. Account
   for alignment, gaps, BSS, mailboxes, queue, all three completions, journal
   and other static storage. Trace retained stock routes and every required
   adapter path from the outer hook. Reconcile helpers, literals, interworking
   veneers and visible stack adjustments. Report unresolved call depth and
   runtime stack margin.
4. **Stop and publication.** Stop on unsupported ABI, missing required path,
   unexplained material extent/dependency, compiler failure or need to alter
   flags, regions or stock behaviour. A region overflow corroborated against
   attempted allocated map extents and all companion diagnostics is a valid
   no-fit. Record incomplete or conflicting evidence as unresolved. Preserve
   required behaviour even if it exceeds capacity. Publish only validated
   structured sizing evidence using the existing closed-schema, allowlisted
   journal policy, including failures. Keep raw maps, disassembly, literal
   words, binaries, unrestricted logs and upstream material in disposable
   scratch. Retaining or publishing raw linked instructions, maps, binaries
   or other unapproved upstream material requires its own provenance review
   and separate owner decision before the relevant run.
   [Sizing and publication policy][sizing]

The first run is sizing-only. A successful link can establish reconciled
spans while retained-path acceptance awaits separately authorised evidence
retention and independent review. Static fit leaves worker placement,
permissions, scheduling, runtime feasibility and recovery unresolved.
R0 remains open. The hardware recovery gate remains closed.

[study]: ../../research/separate-ios-service-placement.md
[result]: ../../research/experimental-dip-sizing-results.md
[gate]: ../../research/experimental_dip/README.md#entry-and-fixture-contract
[wire]: ../../research/tcp_peer/README.md#experimental-wire-format
[ipc]: ../../research/ios-ipc-ownership-and-fixture.md
[calls]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/cios-lib/syscalls.h#L32-L86
[usb]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/usb-module/main.c#L162-L249
[queue]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/messaging/messageQueue.c#L27-L295
[timer]: https://github.com/DacoTaco/StarStruck/blob/ec0508f1db187f97764e6c1ac4b0076c09ec77f4/kernel/source/scheduler/timer.c#L37-L377
[hook]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/dip-plugin/plugin.c#L675-L763
[mlstart]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/start.s#L23-L140
[mload]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/main.c
[elf]: https://github.com/wiidev/d2x-cios/blob/33ad1eeeb8f562df99e7d7ca428fdd36e0e31be7/source/mload-module/elf.c
[gxnet]: https://github.com/wiidev/usbloadergx/blob/e25c4f3501ed957b7db73f79c51fdf00715ab2e2/source/network/networkops.cpp#L79-L87
[adr4]: 0004-pc-only-fixture-simulation.md#verdicts
[adr5]: 0005-experimental-dip-sizing-link.md
[stock]: ../../research/d2x-build-baseline.md#hosted-initiation-and-evidence
[sizing]: ../../research/experimental_dip/README.md#publication-and-scratch-evidence
[provenance]: ../../research/experimental_dip/README.md#provenance-for-this-integration
