# PC-only diagnostic fixture simulation

**Experimentally verified on PC** means a named event sequence produced the
asserted transitions. Run the suite from the repository root with Python 3.12.

```sh
timeout 30s python3 -B -m unittest discover -s tests -p 'test_fixture_sim.py' -v
```

The driver chooses every event and clock sample. It can withhold a submission
return indefinitely or write the receive scratch after timeout. The model uses
Python records, a bounded mailbox and explicit calls. The TCP peer has its own
loopback tests. [ADR 0004](../../docs/decisions/0004-pc-only-fixture-simulation.md) ·
[Ownership and fixture contracts](../ios-ipc-ownership-and-fixture.md) ·
[Wire format](../tcp_peer/README.md)

## Participants and provisional assumptions

| Participant | Evidence and decisions |
| --- | --- |
| Test driver | Owns hidden RM allocations, descriptor reuse, device writes, publication faults and unwrapped time. Stages the fresh tag, challenge, selected listener and peer run before the attempt. Independent test worlds can share inputs to compare their observable histories. |
| DI | The provisional outer hook binds the instance, slot, builds, DI fd, read tuple, tag and exclusive output extent. Either discriminator identifies a fixture read. A full match claims it, a recognisable mismatch spends it, and an unrelated read follows ordinary handling. DI records the actual caller TID before submission. |
| Network slot | A submission return, a dequeued reply and a coherent output are separate events. Link, KD startup and SO readiness use logical service reports. Socket and SO acquisitions have distinct ledger identities even when both return zero. Simultaneous process descriptors with the same number quarantine both acquisitions. A serial identifies a ledger entry locally. The reply carries only its address, command and result. |
| GX | Requires a matching arm receipt and evidence that at least one discriminator will survive dispatch. Both calls require correlated final PPC IPC handling before wrapper return. A premature return pins the internal request, wait queue, input and output. A later interrupt cannot repair an internal allocation already freed by a faulty wrapper. |
| Observer and evidence review | Capture starts before arming. The reader checks identity, sequence, payload completeness and both commit samples. Only captured records reach review. Separately supplied peer accepts, frame bytes and control results can corroborate those records. The actual GX helper marker carries the final reply observed for its synchronous read. |
| External recovery | An independent clock flags a missed progress checkpoint or the hard cutoff, including when display or DI stalls. Recovery initiation and confirmation are separate events. Only confirmation covering this old instance **and** its relevant I/O closes the external accounting. The old DI ledger remains its last live observation. |

## Invariants and bounds

- One DI thread makes one connection attempt. The private context owns the
  request, path, controls, vectors, scratch, reply, queue and timer bookkeeping
  as one lifetime unit. A possibly admitted operation pins that unit. Full
  queues can drop words silently. A blocked submission cannot dequeue.
- The ledger records unresolved, known and confirmed-release dispositions.
  Each close targets its original acquisition once, with socket before SO.
  Ambiguous admission or close pins the dependent resources. A matched late
  result can establish a handle or release while the first failure stays latched.
  DI may return with quarantined resources once submission has returned, its
  active loan is accounted for, and publication can freeze. GX holds its
  reservation through independent terminal capture and confirmed cleanup.
  Every diagnostic stops before game launch.
- Bring-up gets 30 seconds. All sends, receives and final caller verification
  share five seconds. Connection and cleanup each default to a provisional
  five seconds (`DI(connection=..., cleanup=...)`). Cleanup starts once at
  abandonment or verification. Equality is late. A current token or matching completion checks expiry.
  An older armed phase's token advances elapsed-time accounting. A word from
  a never-armed phase violates the private queue contract and causes quarantine.
- A model tick is one second. The default counter wraps at 256. Each elapsed
  calculation needs a raw sample in the same epoch and evidence that the gap
  from DI's last accepted sample is below half the range. The sampler identifies
  that observation with an anchor. Each new timed event takes a fresh sample
  bound to the last accepted anchor. Two samples at the same tick can establish
  a zero delta. Replaying the consumed sample or losing the interval bound
  makes timeliness unknown. DI accumulates modular deltas across stale wakes.
  Internal checks in one event can share its validated time. The observer's
  provisional progress and hard cutoffs are 35 and 55 independent seconds.
- The default queue holds five words for four distinct phase timers and one
  reply. Reuse of the reply address requires exclusive dequeue and exactly one
  matching delivery per admitted operation. With that assumption disabled,
  the next submission stops. Before dequeue, reply storage reuse or timer
  arming, DI inspects the bounded queue under its existing bindings. A waiting reply
  with no outstanding request, an excess reply or a token for a never-armed
  phase quarantines the queue. If two replies are already visible for one
  loan, DI leaves both words in place, pins the loan and consumes neither
  result. Valid words retain their order. The model makes inspection and
  the corresponding dequeue or binding change one event. IOS57 needs an equivalent ordering
  guarantee. An old reply first delivered **after** reuse begins can still
  match the new request.
- Each submission reserves room for intent, return and completion. The default
  limit of 64 operations covers byte-at-a-time transfers. First failure, reply
  verification and terminal records have separate slots. Interrupted publication
  can leave a permanent gap. The external reader may also see a torn, stale or
  incomplete frame. Queue retirement requires matching evidence of producer
  quiescence and inspection of remaining words.

## Evidence crossing the fixture boundaries

- **Arm and capture.** The staged command denotes the documented unencrypted
  read. The fd must be a nonnegative signed descriptor. Length and word offset
  must fit their 32-bit command words. The typed input is 32 bytes and the
  exclusive output extent must match the positive intended length. Opaque
  labels stand for actual mappings. Byte inputs become owned immutable bytes
  at record construction. Tuples recursively freeze their contents. The
  allowed record types contain only immutable values. Previously captured
  records and the peer's byte evidence retain their original contents.
- **PPC completion.** Each call owns a pinned PPC request and a distinct
  synchronous return path. DI deposits its actual result on exit. For the
  completed read it also returns the sequence of its terminal trace slot.
  The final reply-handler event supplies the actual PPC request address and
  raw result. Only handling that request after its return supplies a handback
  witness. The wrapper, handback and marker carry evidence from that chain.
  Capture can arrive later or out of order. Review uses the recorded
  dependencies and writer sequences. This assumes a target hook at final PPC
  reply handling and visibility of the terminal sequence in the returned
  output. The PPC address stays local to that side of IPC.
- **Submission rejection.** The optional bounded ingress adapter models a
  synchronous try-enqueue. A full queue leaves its contents intact and emits
  a local refusal for the attempted operation before any forwarding. DI may
  retire that prospective acquisition. This is one trusted, observable
  pre-admission contract. Applying it to a target submission path requires
  evidence of the same no-forward guarantee. A bare nonzero trap return
  leaves the slot uncertain, even if a matching-looking word is queued.
  Under this policy DI preserves both until independent termination.
- **Receive handoff.** Each receive lends the same scratch for a new range.
  The driver can write it until the matching completion. That completion is
  assumed to retire producer access to the returned range. DI still owns the
  slot while it requests synchronization and takes an immutable copy. Only
  this handoff can publish the range for that completion. Earlier snapshots
  supply no bytes. A missing or short final range quarantines the loan. A
  late coherent range contributes diagnostic evidence only. On Wii, the order
  of final writes and completion, exclusive cache-line ownership, producer
  retirement, and cache maintenance exposing exactly the fresh returned bytes
  all require evidence. A hidden write after assumed retirement violates the
  contract and may be undetectable to DI.

## Reading the three outcomes

The caller latches the full reply and decoded nonzero unsigned big-endian ID
before cleanup. DI also records the phase budget at transition and publishes
each completion's operation, result, raw tick, late disposition and accepted
byte range. A timely completion carries its phase-relative elapsed time.
Exchange review checks the ordered admissions and completions from exchange
entry through verification. The fragments must account for the exact 24-byte
request followed by the full 28-byte reply. Each completion must be timely,
with nondecreasing elapsed time through verification in [0, 5) seconds.
DI publishes raw ticks at phase boundaries, readiness and verification.
In DI sequence order, a timely completion or verification must have raw tick
`(phase start tick + elapsed seconds) % modulus`. The observer uses the
configured modulus. The sampler supplies the interval bound needed to
distinguish genuine wrap from an unobserved full counter cycle.
The reviewer decodes the ID and joins both byte streams and endpoints to the
accept and frame for the listener and peer run selected before arming. The
peer assigns the ID on accept. These extra observations use DI's trace. The
delivered reply word still carries only address, command and result.

A baseline pass additionally requires matching caller identity, timed readiness,
both safe PPC handbacks, and the matching synchronous DI return ordered before
the captured actual marker. An attributable failure needs captured entry and a
demonstrated failure ordered before cleanup, plus independent wired and listener
checks. Review checks the ordered bring-up and connection operations, including
successful link, startup and readiness service reports and bring-up in [0, 30)
seconds. The ownership check replays the acquisition ledger through connection
for readiness and through retirement for release. Distinct live process fds
must have distinct numbers. A socket and its SO process fd can both be zero.
Failure attribution checks the active phase, its clock and the recorded cause.
An error closing the socket during cleanup leaves an earlier genuine network
failure intact. Positive gate
rejection requires the negative gate result, its intended tuple and the
corresponding wrapper status. The marker's correlated result can establish that ordering if the
separate DI return record was lost. A positive GX skip or matching pre-entry
rejection can establish that the probe never ran. A skip ends the GX stream
and carries an empty payload. Captured DI execution for
the same attempt contradicts either claim, even if its entry record was lost.
Missing or contradictory baseline evidence can leave an independently verified
exchange intact. [Baseline definitions](../ios57-baseline-plan.md)

Safe termination requires confirmed cleanup of all I/O and loans, or independent
confirmation of the end of the old instance and its I/O. Before issuing a
release receipt the observer reconciles every captured intent, admission and
completion with acquisition identities, close results, queue retirement and
the final handback. A gap or live acquisition blocks the receipt. GX checks
the receipt with the issuing observer through a trusted callback. The observer
recognises its issued object and rechecks eligibility. GX then releases its
reservation and records that receipt immediately after its marker. Safe
termination and the watchdog use the same predicate. Both require capture of
that authorised release or independent confirmation of the end of this instance
and its I/O. Requesting recovery leaves the hard cutoff active. For example, an
ambiguous socket close can leave the exchange verified and the baseline passing
if DI returns and GX reaches the actual marker. A blocked close can leave the
same exchange verified with an indeterminate baseline. Both keep resources pinned.

DI returns only after freezing its publication. Any captured DI sequence
beyond that return contradicts normal termination and invalidates an issued
receipt. GX rechecks before acting. If contradictory evidence arrives after
GX has released the reservation, the release has already happened. Safe
termination then becomes unconfirmed and the independent watchdog applies
again. Prospective release therefore relies on actual producer quiescence and
faithful publication of a final record. Independent confirmation that both
the old instance and its I/O ended can still establish termination.

## ADR coverage

The named test groups and scenarios are in [the simulation suite](../../tests/test_fixture_sim.py).

| Requirement | Tests and observable result |
| --- | --- |
| Arm and claim | `ArmingTests` varies each discriminator and read field, interleaves ordinary reads, and submits valid duplicates after rejection and claim. Lost or mismatched receipts and unproved preservation withhold dispatch. |
| PPC handback | The premature-return subtests exercise both calls and a foreign completion. They check every retained PPC loan, blocked marker, spent arm and inhibited launch. `ObservationTests` also varies raw IPC and wrapper status. |
| Ownership | `OwnershipTests` compares identical DI histories across hidden allocation outcomes, checks known pre-admission rejection and blocks in open. It writes into quarantined receive scratch, reuses a numeric handle during ambiguous close and delivers both successful and failed late closes. |
| Deadlines and queue | `DeadlineTests` permutes timer/reply order on either side of equality, advances through partial I/O and delays verification. It crosses counter wrap, loses the sampling bound, fills the queue, tests stale and duplicate words, exhausts trace capacity and challenges timer retirement. |
| Publication and recovery | `ObservationTests` interrupts a writer, presents partial, stale and conflicting frames, freezes reader or display and omits the actual marker. It checks watchdog, recovery initiation and matching two-part termination confirmation separately. |
| Evidence and verdicts | `test_complete_reference_run` follows all four acquisitions through retirement. Other observation tests change peer bytes, accept, caller TID, service evidence, controls and return ordering. The ownership and observation tests preserve a verified exchange across failed, late and blocked cleanup. |

### Independent review regressions

All cases below drive the fixture in `RemediationTests`. Corruption cases
replace the first captured copy of the affected record.

| Finding | Regression and observed decision |
| --- | --- |
| PPC request identity and order | A distinct same-labelled request, a premature final callback, and a later genuine DI return cannot establish the earlier marker. A mismatched terminal sequence prevents a pass. |
| Mutable aliases | Changing the original tag, challenge or peer buffers preserves admitted bytes and historical captures. Nested mutable containers are rejected. |
| Receive coherence | A 24-byte fragment leaves the expected ID in scratch. A four-byte result without current-range visibility quarantines the slot, including when a send count is replayed. |
| Contradictory evidence | Truncated frames, a wire/decoded ID mismatch, verification at five seconds and readiness at 30 seconds lose their respective verdicts. A false clean record, failed close or missing submission blocks reservation release. |
| Clock interval | Stale wakes at 90 and 180 seconds count toward a reply observed at 258. Invalid starting ticks and a bound tied to an unconsumed sample prevent progression. The original bounded-wrap and equality tests also run. |
| Peer attribution | A mutually consistent accept and frame for another listener or peer run cannot verify the intended exchange. |
| Ownership | A full ingress demonstrates rejection. A negative trap with a queued apparent success retains an unresolved loan. Two live process fds numbered seven prohibit either close. The reference run permits a socket and process fd both numbered zero. |
| Timer origin | A cleanup token at initial claim quarantines the queue. Early and duplicate tokens from armed producers retain their original deadline. |
| Gate rejection and parameters | A claimed rejection with raw success and wrapper zero is indeterminate. Invalid fd, length, command or word offset cannot arm the fixture. |

The second review's reproductions and companion cases run in `SecondReviewTests`.

| Finding | Regression and observed decision |
| --- | --- |
| Receipt and watchdog | A borrowed release after ambiguous close and a renamed dispatch during blocked open leave the cutoff active. A GX-made receipt or a copy of an issued receipt leaves the reservation pinned. Issuance, actual release and capture are tested separately. |
| Clock replay | Reusing the second-zero sample at second 12 prevents timely receive or verification. Distinct anchored samples at the same tick permit verification. |
| Final receive bytes | Overwriting the ID between early synchronization and completion changes the bytes DI checks. A missing final range pins the slot, a correct final fragment verifies and a late fragment stays diagnostic. |
| Queued words | A second close reply waiting before SO close prevents its submission. A waiting cleanup token prevents arming that timer. Earlier armed timer words survive both boundary checks. |
| Transcript | Altering or omitting receive evidence defeats verification. Failed link evidence or a contradictory skip defeats the baseline while preserving a corroborated exchange. A captured network intent contradicts both skip and pre-entry rejection. |
| Failure attribution | A relabelled cleanup close cannot establish an attributable failure when peer evidence is unavailable. A genuine send error remains attributable after a later close error. |

The third review's cases run in `ThirdReviewTests`.

| Finding | Regression and observed decision |
| --- | --- |
| Queued completions | Both orders of +4 and −1 on receive pin the loan and leave the baseline indeterminate. Two close results preserve the earlier exchange and leave socket ownership unresolved. |
| Terminal sequence | An operation captured after the terminal sequence blocks issuance, invalidates an outstanding receipt or withdraws cleanup confirmation after release, according to when capture occurs. |
| Phase clock | Changing the final receive tick to 12 at elapsed zero or advancing only the verification elapsed time defeats verification. A genuine fragmented exchange across wrap verifies with frames captured in reverse order. A contradictory tick also defeats attribution in a failed send. |
| Readiness and ownership | A KD open returning the live SO descriptor prevents a baseline pass. Independent exchange evidence still verifies. |
| Skip structure | A dispatch relabelled as skipped retains its call and read payload and leaves the baseline indeterminate. A genuine empty skip establishes that the probe never ran. |

**Remaining trust boundary.** An internally consistent fabrication of the
instrumentation, peer records and lifetime guarantees can reproduce a valid
transcript. The model trusts the sampler, final-visibility provider, captured
writer events, observer receipt channel and external termination confirmation.
The checks cover required observations and contradictions between them.
In the paired close histories, a stale zero result first delivered after reply
address reuse can falsely establish release of a still-live SO fd.
The paired send/receive histories detect missing current-range visibility,
while the raw words alone carry no operation identity.

## Link decision

**Hypothesis for review.** The modified DIP sizing link stays deferred pending
independent review. Two limits affect the design a future link would measure. A blocked trap can outlast every DI
deadline, and a reused reply address cannot identify an undetectable duplicate.
The external watchdog bounds a decision to intervene. A target design still
needs justified exactly-once completion semantics or non-reused reply storage
with its memory cost measured explicitly.

Target ABI and permissions, actual outer-hook caller equivalence, discriminator
preservation, PPC request lifetime, clocks and scheduling, coherent cross-CPU
mapping and publication, space for per-fragment evidence, code and stack fit,
and an independently safe recovery
route all require evidence. R0 remains open, direct DIP remains the candidate,
ADR 0003 covers stock links only, and the hardware recovery gate remains closed.
[Direct-DIP fit study](../direct-dip-tcp-probe-fit.md)
