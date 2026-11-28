// SPDX-License-Identifier: GPL-3.0-only
#include <string.h>
#include "adapter.h"
#include "mem.h"
#include "syscalls.h"

volatile struct provision nd_provision LINE;
volatile struct effects nd_effects[3] LINE;
struct run nd;
u8 nd_trace[48][32] LINE, nd_checks[48][4] LINE;
u8 nd_commit[32] LINE, nd_reader[32] LINE;
static volatile u32 arm_claim, read_claim, armed;
ASSERT_SIZE(record_stride, sizeof(nd_trace[0]) == 32);

OBSERVED unsigned nd_emit(unsigned event, u32 a, u32 b, u32 c)
{
    u8 *record;
    unsigned i;
    u32 hash = 2166136261U;
    if (nd.frozen || nd.seq == 48)
        return 0;
    record = nd_trace[nd.seq];
    put(record, nd.seq + 1);
    record[4] = event >> 8; record[5] = event;
    record[6] = nd.op; record[7] = nd.ordinal;
    put(record + 8, nd.p.dip);
    put(record + 12, nd.claim);
    put(record + 16, event == SHORT_VERDICT ? nd.tick : (u32)os_timer_now(0));
    put(record + 20, a); put(record + 24, b); put(record + 28, c);
    for (i = 0; i < 32; ++i)
        hash = (hash ^ record[i]) * 16777619U;
    put(nd_checks[nd.seq], hash);
    os_sync_after_write(record, 32);
    os_sync_after_write(nd_checks[nd.seq], 4);
    __asm__ volatile ("" ::: "memory");
    put(nd_commit, nd.p.dip);
    put(nd_commit + 4, ++nd.seq);
    memcpy(nd_commit + 8, nd.arm + 48, 8);
    os_sync_after_write(nd_commit, 32);
    return nd.seq;
}

/* Failure payload: class at 0..7, phase (current operation) at 8..15,
 * raw present, tick present and tick valid in bits 16, 17 and 18. */
unsigned nd_failure_record(unsigned event, unsigned why, s32 raw, int observed)
{
    u32 flags = nd.clock_started ? (nd.clock_fault ? 2 : 6) : 0;
    return nd_emit(event, why | nd.op << 8 | (flags | observed) << 16,
                   observed ? raw : 0, nd.clock_started ? nd.tick : 0);
}

void nd_latch_failure(unsigned why, s32 raw, int observed)
{
    if (!nd.failure) {
        nd.failure = why;
        nd.failure_seq = nd_failure_record(FIRST_FAILURE, why, raw, observed);
    }
}

static int live(const ioctl *c, u32 addr, u32 size)
{
    u32 envelope = (u32)c;
    return addr && size && addr < MEM1_SIZE && size <= MEM1_SIZE - addr
        && (envelope >= MEM1_SIZE || addr + size <= envelope || envelope + sizeof(*c) <= addr);
}

static int valid_extent(const ioctl *c, const struct extent *r, unsigned minimum)
{
    return !((r->base | r->end) & 31) && r->end > r->base
        && r->end - r->base >= minimum && live(c, r->base, r->end - r->base);
}

static int separate(const struct extent *a, const struct extent *b)
{
    return a->end <= b->base || b->end <= a->base;
}

static int starts_in(const struct extent *r, u32 base)
{
    return r->base <= base && base < r->end;
}

static int sync_input(ioctl *c, const struct extent *r)
{
    u32 addr = (u32)c->inbuf, first = addr & ~31U, end;
    if (!starts_in(r, addr) || !c->inlen || c->inlen > r->end - addr)
        return 0;
    end = (addr + c->inlen + 31U) & ~31U;
    if (first < r->base || end > r->end || !live(c, first, end - first))
        return 0;
    os_sync_before_read((void *)first, end - first);
    return 1;
}

static int output_ok(const ioctl *c)
{
    return nd.p.output.base == (u32)c->iobuf && c->iolen == 32 && live(c, (u32)c->iobuf, 32);
}

static int nonzero(const u8 *p, unsigned n)
{
    while (n && !*p) { ++p; --n; }
    return n != 0;
}

static int unicast(u32 ip)
{
    unsigned first = ip >> 24;
    return first && first != 127 && first < 224;
}

static s32 reject(unsigned reason)
{
    nd_emit(ARM_REJECT, reason, 0, 0);
    nd_fail(reason, 0, 0);
    nd_emit(TERMINAL, -1, 0, 0);
    nd.frozen = 1;
    return -1;
}

static OBSERVED s32 admit_arm(ioctl *c, s32 fd)
{
    struct provision *p = &nd.p;
    u8 line[32] __attribute__((aligned(4)));
    u32 host, peer, port;
    if (nd_take(&arm_claim))
        return -1;
    os_sync_before_read((void *)&nd_provision, sizeof(nd_provision));
    *p = nd_provision;
    if (p->ownership != 1 || !p->ios || !p->ios_build || !p->dip || !p->dip_build
        || !p->slot || !p->gx || !p->gx_build || !p->claim || !p->epoch || !p->lease || !p->fd_epoch
        || !p->expected.instance || !p->expected.build || !p->expected.session
        || p->expected.instance != p->registered.instance || p->expected.build != p->registered.build
        || p->expected.session != p->registered.session
        || !valid_extent(c, &p->arm, 96) || !valid_extent(c, &p->read, 32)
        || !valid_extent(c, &p->output, 32) || p->output.end - p->output.base != 32
        || !separate(&p->arm, &p->read) || !separate(&p->arm, &p->output)
        || !separate(&p->read, &p->output) || !output_ok(c)
        || c->inlen != 96 || ((u32)c->inbuf & 31) || !sync_input(c, &p->arm))
        return reject(BAD_ARM);
    memcpy(nd.arm, c->inbuf, 96);
    host = arm_word(36); peer = arm_word(40); port = arm_word(44);
    if (arm_word(0) != 1 || arm_word(4) != p->dip || arm_word(8) != p->slot
        || arm_word(12) != p->dip_build || arm_word(16) != p->gx_build
        || fd < 0 || arm_word(20) != (u32)fd || arm_word(24) != ND_READ || arm_word(28) != 32
        || !unicast(host) || !unicast(peer) || host == peer || !port || port > 65535
        || !nonzero(nd.arm + 48, 8) || !nonzero(nd.arm + 56, 16) || nonzero(nd.arm + 72, 24))
        return reject(BAD_ARM);
    memcpy(line, nd.arm + 48, 8);
    memcpy(line + 8, nd.arm + 4, 20);
    put(line + 28, p->output.base);
    memcpy(c->iobuf, line, 32);
    os_sync_after_write(c->iobuf, 32);
    nd.arm_input = (u32)c->inbuf;
    nd_emit(ARM_BIND, p->dip_build, p->gx_build, p->slot);
    nd_emit(ARM_TAG, arm_word(48), arm_word(52), p->gx);
    nd_emit(ARM_TUPLE, ND_READ, 32, arm_word(32));
    nd_emit(ARM_PEER, host, peer, port);
    nd_emit(ARM_RECEIPT, fd, p->output.base, p->ios);
    __asm__ volatile ("" ::: "memory");
    armed = 1;
    return 1;
}

static OBSERVED int handback_authorised(const ioctl *c, s32 fd)
{
    const volatile struct provision *live = &nd_provision;
    s32 caller;
    os_sync_before_read((void *)live, sizeof(*live));
    caller = os_get_thread_id();
    return live->ownership == 1 && live->ios == nd.p.ios && live->ios_build == nd.p.ios_build
        && live->dip == nd.p.dip && live->dip_build == nd.p.dip_build && live->slot == nd.p.slot
        && live->gx == nd.p.gx && live->gx_build == nd.p.gx_build && live->claim == nd.claim
        && live->fd_epoch == nd.p.fd_epoch && live->expected.session == nd.p.expected.session
        && live->output.base == nd.p.output.base && live->output.end == nd.p.output.end
        && live->expected.opener == nd.p.expected.opener && caller >= 0 && caller == nd.tid
        && (u32)fd == arm_word(20) && output_ok(c);
}

OBSERVED s32 nd_hook(ioctl *c, s32 fd)
{
    const u8 *in = (const u8 *)c->inbuf;
    u8 *out = (u8 *)c->iobuf;
    u8 line[32] __attribute__((aligned(4)));
    int arm_input, read_input;
    unsigned quarantine;
    s32 status;
    if (!armed)
        return c->command == ND_ARM ? admit_arm(c, fd) : 0;
    __asm__ volatile ("" ::: "memory");
    arm_input = starts_in(&nd.p.arm, (u32)in);
    read_input = starts_in(&nd.p.read, (u32)in);
    if (!arm_input && !read_input && nd.p.output.base != (u32)out)
        return 0;
    if (read_claim)
        return -1;
    if ((u32)in == nd.arm_input && c->command == ND_ARM && c->inlen == 96
        && (u32)fd == arm_word(20) && output_ok(c) && sync_input(c, &nd.p.arm)
        && !memcmp(in, nd.arm, 96))
        return -1;
    if (nd_take(&read_claim))
        return -1;
    nd.claim = nd.p.claim;
    if (!read_input || c->command != ND_READ || c->inlen != 32 || !sync_input(c, &nd.p.read)
        || ((u32)in & 31) || !output_ok(c) || arm_word(20) != (u32)fd
        || word(in) != ND_READ << 24 || word(in + 4) != 32 || word(in + 8) != arm_word(32)
        || memcmp(in + 12, nd.arm + 48, 8) || nonzero(in + 20, 12))
        return reject(BAD_READ);
    nd.tid = os_get_thread_id();
    nd.entry = nd_emit(ENTRY, (u32)nd_hook, nd.tid, fd);
    nd_emit(SESSION, nd.p.expected.instance, nd.p.expected.build, nd.p.expected.session);
    nd_exchange();
    nd.op = NO_OP; nd.ordinal = 0;
    quarantine = nd.pinned || nd.inner == 2 || ((nd.issued_slots & 2) && !nd.inner
        && nd.short_form != PRE_REJECTED);
    memcpy(line, nd.arm + 48, 8);
    put(line + 8, nd.p.dip); put(line + 24, quarantine); put(line + 28, nd.tid);
    if (handback_authorised(c, fd)) {
        if (nd.clock_started) nd_sample();
        if (nd.seq <= 46 && !nd.frozen) {
            status = nd.failure ? -1 : 1;
            put(line + 12, nd.seq + 2);
            put(line + 16, status); put(line + 20, nd.failure);
            memcpy(out, line, 32);
            os_sync_after_write(out, 32);
            nd_emit(OUTPUT, status, nd.failure, quarantine);
            nd_emit(TERMINAL, status, quarantine, nd.p.output.base);
            nd.frozen = 1;
            return status;
        }
    }
    nd_emit(TERMINAL, -1, 1, 1);
    nd.frozen = 1;
    for (;;) __asm__ volatile ("" ::: "memory");
}
