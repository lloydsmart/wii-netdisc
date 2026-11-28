// SPDX-License-Identifier: GPL-3.0-only
#include <string.h>
#include "adapter.h"
#include "syscalls.h"

u8 nd_request[160] LINE, nd_reply[192] LINE;

static void prefix(u8 *b, u32 length)
{
    struct provision *p = &nd.p;
    put(b, 0x00010001); put(b + 4, length);
    put(b + 8, p->ios); put(b + 12, p->ios_build);
    put(b + 16, p->dip); put(b + 20, p->dip_build);
    put(b + 24, p->expected.instance); put(b + 28, p->expected.build);
    put(b + 32, nd.claim); put(b + 36, p->expected.session);
    put(b + 40, p->slot); put(b + 44, p->gx_build);
    memcpy(b + 48, nd.arm + 48, 8);
    put(b + 56, p->epoch); put(b + 60, p->gx);
}

void nd_make_request(void)
{
    u8 *b = nd_request;
    memset(b, 0, sizeof(nd_request));
    prefix(b, sizeof(nd_request));
    put(b + 64, nd.tid); put(b + 68, arm_word(20));
    memcpy(b + 72, nd.arm + 24, 12);
    put(b + 84, 32); memcpy(b + 88, nd.arm + 36, 8);
    put(b + 96, arm_word(44) << 16);
    memcpy(b + 100, nd.arm + 56, 16);
    put(b + 116, nd.observer); put(b + 120, nd.observer + CUTOFF);
    put(b + 124, nd.start); put(b + 128, nd.end); put(b + 132, nd.p.lease);
}

enum sample_index { BRINGUP, READY, CONNECTED, EXCHANGE, END, VERIFIED, CLEANUP, FINAL, FAILURE };
/* Decode privately after acquiring every reply line. Offsets are wire byte
 * positions. Only a completely checked snapshot can supply worker evidence. */
struct timing_fields { u32 tick[9], present, valid; };

static int ordered(u32 earlier, u32 later)
{
    return later - earlier < HALF;
}

/* All comparable observations are offsets from ioctl issue below HALF.
 * Walk backward for a lower bound, forward for an upper bound. Verification
 * and cleanup start coincide on a byte-bearing reply. Both wire samples
 * retain their original presence and validity in the published decision. */
static u32 time_bound(const struct timing_fields *t, int event, int step)
{
    if (event == VERIFIED && step < 0) event = CLEANUP;
    for (; event >= BRINGUP && event <= FINAL; event += step)
        if (event != END && (t->valid & (1U << event)))
            return t->tick[event] - nd.issue;
    if (step < 0) return 0;
    return nd.ack_valid ? nd.ack_bound - nd.issue : HALF;
}

static unsigned phase_timing(const struct timing_fields *t, unsigned phase, unsigned failure)
{
    /* Admission has only the clipped outer deadline. Bring-up and connection
     * share readiness, and verified exchange and cleanup share the latch. */
    static const struct { u8 start, finish; u32 budget; } limits[] = {
        {0, 0, 0}, {BRINGUP, BRINGUP, 0}, {BRINGUP, READY, THIRTY},
        {READY, CONNECTED, FIVE}, {EXCHANGE, VERIFIED, FIVE}, {VERIFIED, FINAL, FIVE}
    };
    u32 prior_limit = HALF, outer = nd.end - nd.issue;
    unsigned p;
    for (p = phase == 1 ? 1 : 2; p <= (phase ? phase : 5); ++p) {
        int start = limits[p].start, finish = limits[p].finish;
        u32 latest = time_bound(t, finish, 1), budget = limits[p].budget;
        u32 start_bound, earliest_end;
        if (p == phase) {
            /* The first failure is at or before this phase's end. Before
             * cleanup it also dates abandonment (or verification at the latch). */
            unsigned observed = (t->valid & (1U << FAILURE)) ? FAILURE : CLEANUP;
            if ((observed == FAILURE || p < 5) && (t->valid & (1U << observed))) {
                u32 when = t->tick[observed] - nd.issue;
                if (when > latest) return BAD_PHASE;
                latest = when;
            }
            if (failure == 4 && latest < outer
                && (!budget || latest - time_bound(t, start, -1) < budget))
                return BAD_TIME;
            break;
        }
        /* A completed phase must admit a strictly timely end. Propagate its
         * latest possible end only when that event starts the next phase. */
        start_bound = time_bound(t, start, 1);
        if (p > 2 && limits[p-1].finish == start && prior_limit < start_bound)
            start_bound = prior_limit;
        prior_limit = start_bound + budget - 1;
        if (latest < prior_limit) prior_limit = latest;
        earliest_end = time_bound(t, finish, -1);
        if (earliest_end > prior_limit || earliest_end >= outer)
            return phase ? BAD_PHASE : BAD_TIME;
    }
    return 0;
}

static unsigned validate(const u8 *b, struct timing_fields *t)
{
    const u32 failure = word(b + 108), outcome = word(b + 116), length = word(b + 120);
    const u32 disposition = word(b + 156), phase = word(b + 180), flags = word(b + 188);
    u32 prior = nd.issue, reached, required, i, last_phase;
    static const u8 empty[28];
    u8 expected[64];
    prefix(expected, sizeof(nd_reply));
    if (memcmp(b, expected, sizeof(expected)))
        return BAD_PREFIX;
    if (word(b + 64) != nd.p.expected.worker_tid || word(b + 68) != nd.p.expected.worker_pid
        || !word(b + 152) || word(b + 160) != nd.end || word(b + 164) != nd.p.lease
        || word(b + 168) != (u32)nd.tid || word(b + 172) != arm_word(20))
        return BAD_IDENTITY;
    t->present = word(b + 72); t->valid = word(b + 184);
    if ((t->present & ~511U) || (t->valid & ~t->present) || (flags & ~3U)
        || (t->present != t->valid && !(flags & 2)))
        return BAD_MASK;
    if (outcome > 1 || (disposition != 1 && disposition != 2)
        || (!(flags & 1) && word(b + 176)))
        return BAD_OUTCOME;
    if (length == 28) {
        if (memcmp(b + 124, nd.arm + 48, 24) || !word(b + 148))
            return BAD_FRAME;
    } else if (length || memcmp(b + 124, empty, 28) || (t->present & (1U << VERIFIED))) {
        return BAD_FRAME;
    }
    if (!outcome) {
        if (t->valid != 255 || t->present != 255 || flags || failure || phase
            || length != 28 || disposition != 1)
            return BAD_OUTCOME;
    } else if (!failure || failure > 6 || !phase || phase > 5
               || (failure == 1 && phase != 1) || (failure == 2 && phase < 2)
               || (failure == 3 && phase != 4) || (failure == 6 && !(flags & 2))
               || (!length && phase == 5)
               || (length && phase != 5 && !(phase == 4 && (failure == 4 || failure == 6)))) {
        return BAD_PHASE;
    }
    /* A failure within a phase can precede its first sample. Earlier phase
     * milestones must have occurred. Admission can abandon before bring-up. */
    last_phase = length ? 5 : phase;
    required = (1U << CLEANUP) | (1U << FINAL) | (outcome << FAILURE);
    reached = required;
    if (last_phase >= 2) required |= 1U << BRINGUP;
    if (last_phase >= 3) required |= 1U << READY;
    if (last_phase >= 4) required |= 1U << CONNECTED;
    if (last_phase >= 5 || failure == 3 || (phase == 4 && failure == 2))
        required |= (1U << EXCHANGE) | (1U << END);
    if (length) required |= 1U << VERIFIED;
    reached |= required;
    if (last_phase == 2) reached |= 1U << READY;
    if (last_phase == 3) reached |= 1U << CONNECTED;
    if (last_phase == 4) reached |= (1U << EXCHANGE) | (1U << END);
    if (failure == 2 && ((phase == 3 && (t->present & (1U << CONNECTED)))
        || (phase == 2 && (t->present & (1U << READY)))))
        return BAD_PHASE;
    if ((t->present & ~reached) || ((required & ~t->present) && !(flags & 2))
        || (((t->present >> EXCHANGE) ^ (t->present >> END)) & 1)
        || (((t->valid >> EXCHANGE) ^ (t->valid >> END)) & 1))
        return BAD_MASK;
    for (i = 0; i < 9; ++i) {
        u32 tick = word(b + (i == FAILURE ? 112 : 76 + 4*i));
        t->tick[i] = tick;
        if (!(t->present & (1U << i)) && tick)
            return BAD_MASK;
        if (!(t->valid & (1U << i)) || i == END || i == FAILURE)
            continue;
        if (!ordered(prior, tick) || !ordered(nd.issue, tick)
            || (nd.ack_valid && tick - nd.issue > nd.ack_bound - nd.issue))
            return BAD_TIME;
        prior = tick;
    }
    if ((t->valid & (1U << END)) && t->tick[END] != t->tick[EXCHANGE] + FIVE)
        return BAD_TIME;
    i = length ? VERIFIED : FAILURE;
    if ((t->valid & (1U << i)) && (t->valid & (1U << CLEANUP))
        && t->tick[i] != t->tick[CLEANUP])
        return BAD_TIME;
    if (t->valid & (1U << FAILURE)) {
        u32 f = t->tick[FAILURE];
        for (i = 0; i < FINAL; ++i)
            if (i != END && (i != CLEANUP || length) && (t->valid & (1U << i))
                && !ordered(t->tick[i], f))
                return BAD_TIME;
        if (!ordered(nd.issue, f) || ((t->valid & (1U << FINAL)) && !ordered(f, t->tick[FINAL]))
            || (nd.ack_valid && f - nd.issue > nd.ack_bound - nd.issue))
            return BAD_TIME;
    }
    return phase_timing(t, phase, failure);
}

void nd_short_decision(unsigned kind, unsigned reason, const u8 *reply)
{
    unsigned begin, exchange = INDETERMINATE, outer;
    nd_sample();
    outer = nd_verdict(nd.end);
    if (reply && (word(reply + 184) & (1U << END)))
        exchange = nd_verdict(word(reply + 92));
    begin = nd_emit(NO_FRAME, kind, nd.operation_ref, nd.loan_ref);
    if (reply)
        nd_emit(ABSENT_FAILURE, word(reply + 152), word(reply + 156), nd.worker_failure);
    nd.decision = nd_emit(SHORT_VERDICT, begin, nd.failure_seq,
                          (reason << 6) | (outer << 4) | (exchange << 2) | (kind == REJECTED));
}

OBSERVED void nd_validate_reply(void)
{
    u8 b[192];
    struct timing_fields t;
    u32 reason, first, exchange, outer, sample;
    os_sync_before_read(nd_reply, sizeof(nd_reply));
    memcpy(b, nd_reply, sizeof(b));
    nd_sample();
    reason = validate(b, &t);
    if (reason) {
        nd_fail(reason, 0, 0); /* Observe the rejection before acquiring the lease. */
        nd_short_decision(REJECTED, reason, NULL);
        return;
    }
    if (word(b + 116)) nd_fail(INNER_FAILURE, 0, 0);
    nd_sample(); /* Independent DIP verification time, including later faults. */
    sample = nd.tick;
    nd.inner = word(b + 156);
    if (word(b + 116)) {
        u32 flags = (word(b + 188) & 1) | ((t.present >> FAILURE) << 1) | ((t.valid >> FAILURE) << 2);
        nd.worker_failure = nd_emit(WORKER_FAILURE, word(b + 108) | word(b + 180) << 8 | flags << 16,
                                    word(b + 176), t.tick[FAILURE]);
    }
    if (!word(b + 120)) {
        nd_short_decision(ABSENT, INNER_FAILURE, b);
        return;
    }
    exchange = (t.valid & (1U << END)) ? nd_verdict(t.tick[END]) : INDETERMINATE;
    outer = nd_verdict(nd.end);
    if (exchange != TIMELY || outer != TIMELY)
        nd_latch_failure(DIP_LATE, 0, 0);
    first = nd_emit(FRAME0, word(b + 124), word(b + 128), word(b + 132));
    nd_emit(FRAME1, word(b + 136), word(b + 140), word(b + 144));
    nd_emit(FRAME2, word(b + 148), 0, 0);
    nd_emit(FRAME_ID, word(b + 148), word(b + 152), nd.entry);
    nd_emit(FRAME_TIMES, t.tick[EXCHANGE], t.tick[END], t.tick[VERIFIED]);
    nd_emit(FRAME_STATUS, word(b + 116) | word(b + 188) << 8,
            word(b + 156) | t.present << 8, 28 | t.valid << 8);
    nd_emit(DIP_TIME, sample, t.tick[END], nd.end);
    nd.decision = nd_emit(VERDICT, first, nd.entry, exchange | outer << 2);
}
