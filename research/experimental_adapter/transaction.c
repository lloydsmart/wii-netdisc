// SPDX-License-Identifier: GPL-3.0-only
#include <string.h>
#include "adapter.h"
#include "syscalls.h"

ipcmessage nd_completions[3] LINE;
char nd_path[32] LINE;
static u32 queue_words[8] LINE;
ASSERT_SIZE(ipc_extent, sizeof(ipcmessage) == 32 && __builtin_offsetof(ipcmessage, command) == 0
            && __builtin_offsetof(ipcmessage, result) == 4);
ASSERT_SIZE(pool_extent, sizeof(nd_completions) == 96 && __alignof__(nd_completions) == 32);
ASSERT_SIZE(provision_lines, sizeof(struct provision) % 32 == 0);
ASSERT_SIZE(effects_line, sizeof(struct effects) == 32);

static void anomaly(unsigned why, u32 detail)
{
    int raw_present = why == RECEIVE_ERROR;
    if (!nd.anomaly_seq)
        nd.anomaly_seq = nd_failure_record(FIRST_ANOMALY, why, detail, raw_present);
    nd_latch_failure(why, detail, raw_present);
}

static void queue_fault(unsigned why, u32 detail)
{
    nd.bad_queue = 1;
    /* A later contradiction can withdraw an earlier retirement assumption.
     * Keep every issued slot, the original acquisition and the full prefix. */
    nd.disputed = nd.issued_slots;
    if (nd.owner == RELEASED) nd.owner = CLOSING;
    anomaly(why, detail);
}

unsigned nd_verdict(u32 deadline)
{
    if (!nd.deadline_set)
        return INDETERMINATE;
    if (nd.last - nd.start >= deadline - nd.start)
        return LATE;
    return !nd.clock_fault && nd.last - nd.observer < CUTOFF ? TIMELY : INDETERMINATE;
}

static void acquire_clock(const u32 *event_tick)
{
    u8 line[32];
    u32 now, start, elapsed, remaining;
    os_sync_before_read(nd_reader, 32);
    memcpy(line, nd_reader, 32);
    os_sync_before_read(nd_reader, 32);
    now = event_tick ? *event_tick : (u32)os_timer_now(0);
    start = word(line + 24);
    elapsed = now - start;
    nd.tick = now;
    if (memcmp(line, nd_reader, 32) || word(line) != 1 || word(line + 4) != nd.p.lease
        || word(line + 8) != nd.p.ios || word(line + 12) != nd.p.epoch
        || memcmp(line + 16, nd.arm + 48, 8) || word(line + 28) != start + CUTOFF
        || elapsed >= HALF || (nd.clock_started && (now - nd.last >= HALF || start != nd.observer))) {
        nd.clock_fault = 1;
    }
    if (!nd.clock_started) {
        nd.observer = start;
        nd.start = now;
        remaining = elapsed < CUTOFF ? CUTOFF - elapsed : 0;
        nd.end = now + (remaining < FIFTY ? remaining : FIFTY);
        nd.deadline_set = !nd.clock_fault;
    }
    nd.clock_started = 1;
    if (!nd.clock_fault) nd.last = now;
}

static unsigned clock_result(void)
{
    if (nd.clock_fault) {
        anomaly(CLOCK_FAULT, nd.tick);
        return INDETERMINATE;
    }
    if (nd_verdict(nd.end) != TIMELY) {
        nd_latch_failure(EXPIRED, 0, 0);
        return LATE;
    }
    return TIMELY;
}

OBSERVED unsigned nd_sample(void)
{
    acquire_clock(NULL);
    return clock_result();
}

void nd_fail(unsigned why, s32 raw, int observed)
{
    if (!nd.failure) {
        if (nd.clock_started) {
            u32 event_tick = (u32)os_timer_now(0);
            acquire_clock(&event_tick);
        }
        nd_latch_failure(why, raw, observed);
        if (nd.clock_started) clock_result();
    }
}

static int mailbox_extent(const struct extent *r, void *base, unsigned size)
{
    const struct extent *external[3] = { &nd.p.arm, &nd.p.read, &nd.p.output };
    unsigned i;
    if (r->base != (u32)base || (r->base & 31) || r->end <= r->base || r->end-r->base != size)
        return 0;
    for (i = 0; i < 3; ++i)
        if (r->base < external[i]->end && external[i]->base < r->end)
            return 0;
    return 1;
}

static int pool_address(u32 word)
{
    return word - (u32)nd_completions < sizeof(nd_completions);
}

static int provisioned(void)
{
    const struct provision *p = &nd.p;
    const struct service *s = &p->expected;
    unsigned i = 0;
    while (i < sizeof(s->path) && s->path[i]) ++i;
    if (!i || i == sizeof(s->path) || memcmp(s, &p->registered, sizeof(*s))
        || !p->ios || !p->ios_build || !p->gx || !p->claim || !p->lease || !p->epoch
        || !p->fd_epoch || !s->session || !s->instance || !s->build || (s32)s->worker_tid < 0
        || (s32)s->worker_pid < 0 || p->registration != 1 || p->visible != 1 || p->ready != 1
        || !mailbox_extent(&p->request, nd_request, sizeof(nd_request))
        || !mailbox_extent(&p->reply, nd_reply, sizeof(nd_reply))
        || !p->wake_token || pool_address(p->wake_token)
        || (p->stale_token && (p->stale_token == p->wake_token || pool_address(p->stale_token)
            || !p->stale_epoch || !p->stale_lease
            || (p->stale_epoch == p->epoch && p->stale_lease == p->lease)))) {
        nd_fail(BAD_SERVICE, 0, 0);
        return 0;
    }
    if (nd.tid < 0 || s->opener != (u32)nd.tid) {
        nd_fail(WRONG_CALLER, nd.tid, 1);
        return 0;
    }
    memcpy(nd_path, s->path, sizeof(nd_path));
    return 1;
}

/* Return a single attributable address only after classifying the entire
 * batch. The ninth call after eight words is strictly an emptiness probe. */
struct observation { u32 tick; unsigned valid; };

static OBSERVED int inspect_queue(ipcmessage *active, int block, struct observation *receipt)
{
    unsigned count = 0, hits = 0;
    for (;;) {
        u32 value = 0;
        s32 status = os_message_queue_receive(nd.queue, &value, block ? 0 : 1);
        int blocking = block;
        unsigned wake_time;
        u32 observed;
        block = 0;
        if (status == -7 && !blocking)
            break;
        observed = (u32)os_timer_now(0);
        acquire_clock(&observed);
        if (status != 0) {
            queue_fault(RECEIVE_ERROR, status);
            clock_result();
            break;
        }
        wake_time = clock_result();
        if (++count > 8) {
            queue_fault(QUEUE_FULL, count);
            break;
        }
        if (nd.timer_live == 1 && value == nd.p.wake_token) {
            if (nd.timer_seen)
                queue_fault(DUPLICATE_WORD, value);
            nd.timer_seen = 1;
            if (wake_time == TIMELY)
                anomaly(EARLY_WAKE, value);
        } else if (value && value == nd.p.stale_token && !nd.stale_seen) {
            nd.stale_seen = 1;
        } else if (active && value == (u32)active) {
            if (++hits != 1) queue_fault(DUPLICATE_WORD, value);
            else {
                receipt->valid = !nd.clock_fault;
                receipt->tick = observed;
            }
        } else {
            u32 offset = value - (u32)nd_completions;
            queue_fault(offset < sizeof(nd_completions) && !(offset & 31) ? OLD_WORD : BAD_WORD, value);
        }
    }
    nd_sample();
    return !nd.bad_queue && hits == 1;
}

static int reserve(unsigned op)
{
    unsigned remaining_ops = 4 - op;
    unsigned needed = 5 * remaining_ops + (nd.decision ? 0 : 8)
        + (nd.failure_seq ? 0 : 1) + (nd.anomaly_seq ? 0 : 1) + (nd.worker_failure ? 0 : 1)
        + 8 + 2;
    if (nd.seq <= 48 && needed <= 48 - nd.seq)
        return 1;
    nd_fail(NO_CAPACITY, 0, 0);
    if (!nd.capacity) {
        nd.capacity = 1;
        nd_emit(CAPACITY, needed, nd.seq, op);
    }
    return 0;
}

static int original_acquisition(void)
{
    const u8 *entry;
    if (!nd.acquisition_ref || nd.acquisition_ref > nd.seq) return 0;
    entry = nd_trace[nd.acquisition_ref-1];
    return entry[5] == RESOURCE && entry[6] == OPEN_SERVICE && entry[7] == 1
        && word(entry+12) == nd.claim && word(entry+20) == HELD && word(entry+24) == (u32)nd.fd;
}

/* Read only after acquiring the current provision. A numerical descriptor
 * and session serial can recur in a different instance or allocation. */
static int acquisition_domain(void)
{
    const volatile struct provision *p = &nd_provision;
    const struct service *s = &nd.p.expected;
    return p->ios == nd.p.ios && p->ios_build == nd.p.ios_build
        && p->dip == nd.p.dip && p->dip_build == nd.p.dip_build
        && p->claim == nd.claim && p->fd_epoch == nd.p.fd_epoch
        && p->expected.instance == s->instance && p->expected.build == s->build
        && p->expected.session == s->session && p->registered.instance == s->instance
        && p->registered.build == s->build && p->registered.session == s->session;
}

static unsigned confirmed_effects(const struct effects *bound, unsigned flags)
{
    const volatile struct effects *source = &nd_effects[nd.op-1];
    os_sync_before_read((void *)source, sizeof(*source));
    os_sync_before_read((void *)&nd_provision, sizeof(nd_provision));
    if (memcmp(bound, (const void *)source, sizeof(*source)) || !acquisition_domain())
        return 0;
    if (nd_provision.single_delivery != 1 || nd_provision.retirement != 1) flags &= ~RETIRES_ONCE;
    if (nd_provision.release != 1) flags &= ~RELEASES_ORIGINAL;
    return flags;
}

/* Private to this invocation, its ordinal, slot and original acquisition. */
static unsigned bind_effects(ipcmessage *message, struct effects *e)
{
    const volatile struct effects *source = &nd_effects[nd.op-1];
    os_sync_before_read((void *)source, sizeof(*source));
    *e = *source;
    if (e->ios != nd.p.ios || e->session != nd.p.expected.session || e->claim != nd.claim
        || e->address != (u32)message || e->open_ordinal != (nd.op == OPEN_SERVICE ? 0U : 1U)
        || e->fd_epoch != nd.p.fd_epoch || (e->flags & ~7U))
        return 0;
    return confirmed_effects(e, e->flags);
}

/* The fixture generation is immutable while the original fd is exclusive.
 * Loss of that guarantee cannot be repaired by matching a numeric fd. */
static int owns_fd(void)
{
    os_sync_before_read((void *)&nd_provision, sizeof(nd_provision));
    return original_acquisition() && acquisition_domain();
}

static OBSERVED s32 submit(ipcmessage *message)
{
    if (nd.op == OPEN_SERVICE)
        return os_open_async(nd_path, 0, (void *)nd.queue, message);
    if (nd.op == CLOSE_SERVICE)
        return os_close_async(nd.fd, (void *)nd.queue, message);
    return os_ioctl_async(nd.fd, nd.p.expected.selector, nd_request, sizeof(nd_request),
                          nd_reply, sizeof(nd_reply), nd.queue, message);
}

static int current_registration(void)
{
    os_sync_before_read((void *)&nd_provision, sizeof(nd_provision));
    return !memcmp((const void *)&nd_provision, &nd.p, sizeof(nd.p));
}

static OBSERVED void operation(unsigned op)
{
    ipcmessage *message = &nd_completions[op-1];
    s32 raw, result;
    struct effects bound;
    struct observation receipt = {0, 0};
    unsigned matched, sampled, returned, ref, facts, command, eligible, previous = nd.owner;
    nd.op = op;
    nd.ordinal = nd.issued + 1;
    if (!reserve(op)) return;
    if (op != CLOSE_SERVICE && !current_registration()) {
        nd_fail(BAD_SERVICE, 0, 0);
        return;
    }
    inspect_queue(NULL, 0, NULL);
    if (nd.bad_queue || nd.timer_seen || nd_sample() != TIMELY) return;
    memset(message, 0, sizeof(*message));
    os_sync_after_write(message, sizeof(*message));
    if (op == CONTROL_SERVICE) {
        nd_make_request();
        os_sync_after_write(nd_request, sizeof(nd_request));
        memset(nd_reply, 0, sizeof(nd_reply));
        os_sync_after_write(nd_reply, sizeof(nd_reply));
    } else if (op == OPEN_SERVICE) {
        os_sync_after_write(nd_path, sizeof(nd_path));
    }
    nd_emit(INTENT, (u32)message, nd.p.expected.session, op == OPEN_SERVICE ? 0 : nd.acquisition_ref);
    facts = bind_effects(message, &bound);
    eligible = op == OPEN_SERVICE || owns_fd();
    if (!eligible) nd_fail(UNRELEASED, 0, 0);
    if (op != CLOSE_SERVICE && !current_registration()) {
        eligible = 0;
        nd_fail(BAD_SERVICE, 0, 0);
    }
    if (nd_sample() != TIMELY || !eligible) {
        ref = nd_emit(NOT_ISSUED, (u32)message, nd.p.expected.session, nd.acquisition_ref);
        if (op == CONTROL_SERVICE) { nd.short_form = UNISSUED; nd.operation_ref = ref; }
        return;
    }
    nd.active = op; nd.issued = nd.ordinal;
    nd.issued_slots |= 1U << (op-1);
    if (op == OPEN_SERVICE) nd.owner = POSSIBLE;
    if (op == CLOSE_SERVICE) nd.owner = CLOSING;
    if (op == CONTROL_SERVICE) nd.issue = nd.tick;
    raw = submit(message);
    if (raw != 0) nd_fail(SUBMIT_ERROR, raw, 1);
    ref = nd_emit(SUBMITTED, raw, (u32)message, nd.acquisition_ref);
    facts = confirmed_effects(&bound, facts);
    sampled = nd_sample();
    if (raw < 0 && (u32)raw == bound.rejection_code && (facts & PRE_ADMISSION_CODE)) {
        inspect_queue(NULL, 0, NULL);
        if (!nd.bad_queue && (confirmed_effects(&bound, facts) & PRE_ADMISSION_CODE)) {
            nd.owner = previous; nd.active = 0;
            nd.loan_ref = nd_emit(LOAN, (u32)message, PRE_REJECTED, ref);
            nd.operation_ref = ref;
            if (op == CONTROL_SERVICE) nd.short_form = PRE_REJECTED;
            nd_emit(RESOURCE, nd.owner, nd.fd, nd.acquisition_ref);
        } else {
            nd_emit(LOAN, (u32)message, 0, ref);
            nd_emit(RESOURCE, nd.owner, nd.fd, nd.acquisition_ref);
        }
        return;
    }
    do {
        matched = inspect_queue(message, raw == 0 && sampled == TIMELY && !nd.timer_seen, &receipt);
        sampled = nd_verdict(nd.end);
    } while (!matched && raw == 0 && !nd.bad_queue && !nd.timer_seen && sampled == TIMELY);
    if (!matched) {
        nd_fail(NO_COMPLETION, 0, 0);
        nd_emit(LOAN, (u32)message, 0, ref);
        nd_emit(RESOURCE, nd.owner, nd.fd, nd.acquisition_ref);
        return;
    }
    os_sync_before_read(message, sizeof(*message));
    command = message->command;
    result = (s32)message->result;
    {
        u32 observation = (u32)os_timer_now(0);
        acquire_clock(&observation);
    }
    facts = confirmed_effects(&bound, facts);
    if (command != 8) nd_latch_failure(BAD_COMMAND, 0, 0);
    else if (!(facts & RETIRES_ONCE) || nd.p.single_delivery != 1 || nd.p.retirement != 1)
        nd_fail(UNRETIRED, 0, 0);
    else if ((op == OPEN_SERVICE && result < 0) || (op == CONTROL_SERVICE && result != 0))
        nd_latch_failure(OP_ERROR, result, 1);
    else if (op == CLOSE_SERVICE && result != 0)
        nd_latch_failure(UNRELEASED, result, 1);
    clock_result();
    returned = nd_emit(COMPLETION, (u32)message, command, result);
    sampled = nd_sample();
    facts = confirmed_effects(&bound, facts);
    if (command != 8 || nd.p.single_delivery != 1 || nd.p.retirement != 1
        || !(facts & RETIRES_ONCE)) {
        nd_fail(command != 8 ? BAD_COMMAND : UNRETIRED, 0, 0);
        nd_emit(LOAN, (u32)message, 0, returned);
        nd_emit(RESOURCE, nd.owner, nd.fd, nd.acquisition_ref);
        return;
    }
    nd.loan_ref = nd_emit(LOAN, (u32)message, 1, returned);
    if (op == OPEN_SERVICE) {
        if (result >= 0) { nd.fd = result; nd.owner = HELD; }
    } else if (op == CONTROL_SERVICE) {
        nd.operation_ref = returned;
        if (result == 0) {
            nd.ack_valid = receipt.valid;
            nd.ack_bound = receipt.tick;
            nd_validate_reply();
        }
        else {
            nd_short_decision(UNDEFINED, OP_ERROR, NULL);
        }
    } else if (result == 0 && nd.p.release == 1 && (facts & RELEASES_ORIGINAL) && owns_fd()) {
        nd.owner = RELEASED;
    } else {
        nd_fail(UNRELEASED, result, 1);
    }
    nd.active = 0;
    ref = nd_emit(RESOURCE, nd.owner, nd.fd, op == OPEN_SERVICE ? nd.ordinal : nd.acquisition_ref);
    if (op == OPEN_SERVICE) nd.acquisition_ref = ref;
    if (sampled != TIMELY) nd_emit(LATE_RESOURCE, ref, nd.owner, returned);
}

static void setup(void)
{
    u32 remaining, delay;
    nd_sample();
    nd_emit(LEASE, nd.p.epoch, nd.p.lease, nd.p.ios_build);
    nd_emit(OBSERVER, nd.observer, nd.observer + CUTOFF, (u32)nd_reader);
    nd_emit(OUTER, nd.start, nd.end, nd.claim);
    if (nd.failure) return;
    nd.queue = os_message_queue_create(queue_words, 8);
    if (nd.queue < 0) {
        nd.queue_live = 2; /* Unknown disposition, no destroyable identity. */
        nd_fail(QUEUE_SETUP, nd.queue, 1);
    } else {
        nd.queue_live = 1;
        if (nd_sample() == TIMELY) {
            remaining = nd.end - nd.tick;
            /* ceil(ticks * 128 / 243) without a 64-bit multiplication. */
            delay = (remaining / 243U) * 128U + ((remaining % 243U) * 128U + 242U) / 243U;
            nd.timer = os_create_timer(delay, 0, nd.queue, nd.p.wake_token);
            if (nd.timer < 0) {
                nd.timer_live = 2;
                nd_fail(TIMER_SETUP, nd.timer, 1);
            } else nd.timer_live = 1;
        }
    }
    nd_emit(SETUP, nd.queue, nd.timer, nd.p.wake_token);
}

static void teardown(void)
{
    s32 stop, destroy;
    if (nd.timer_live == 1) {
        stop = os_stop_timer(nd.timer);
        destroy = stop == 0 ? os_destroy_timer(nd.timer) : -1;
        if (stop || destroy || nd.p.timer_retirement != 1)
            nd_fail(TEARDOWN_ERROR, stop ? stop : destroy, 1);
        nd_emit(TIMER_END, nd.timer, stop, destroy);
        if (stop == 0 && destroy == 0 && nd.p.timer_retirement == 1) {
            if (!nd.bad_queue && !nd.active) inspect_queue(NULL, 0, NULL);
            nd.timer_live = 0;
        }
    }
    if (nd.queue_live == 1 && !nd.timer_live && !nd.active && !nd.bad_queue) {
        destroy = os_message_queue_destroy(nd.queue);
        if (destroy) nd_fail(TEARDOWN_ERROR, destroy, 1);
        nd_emit(QUEUE_END, nd.queue, destroy, 0);
        if (destroy == 0) nd.queue_live = 0;
    }
    nd.pinned = nd.queue_live || nd.timer_live || nd.active || (nd.owner != NO_ACQUISITION && nd.owner != RELEASED);
    nd_emit(OBLIGATIONS, nd.active | nd.disputed << 8, nd.owner, nd.fd);
    nd_emit(DISPOSITION, nd.pinned | nd.inner << 8, nd.timer_live, nd.queue_live);
}

OBSERVED void nd_exchange(void)
{
    nd.fd = nd.queue = nd.timer = -1;
    if (!provisioned()) return;
    setup();
    if (!nd.failure) operation(OPEN_SERVICE);
    if (nd.owner == HELD && !nd.active) {
        nd.short_form = SKIPPED;
        nd.operation_ref = nd.acquisition_ref;
        nd.loan_ref = 0;
        if (!nd.failure) operation(CONTROL_SERVICE);
        if (!nd.active && !nd.decision) {
            nd.op = CONTROL_SERVICE;
            if (nd.short_form == SKIPPED) nd.ordinal = 0;
            nd_short_decision(nd.short_form, nd.failure, NULL);
        }
        if (nd.decision && !nd.active && !nd.bad_queue && !nd.timer_seen && nd_sample() == TIMELY)
            operation(CLOSE_SERVICE);
    }
    nd.op = NO_OP; nd.ordinal = 0;
    teardown();
    if (nd.deadline_set) nd_sample();
}
