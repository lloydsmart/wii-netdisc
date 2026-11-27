// SPDX-License-Identifier: GPL-3.0-only
#include <string.h>
#include "netdisc.h"
#include "mem.h"
#include "syscalls.h"

struct nd_run nd;
static volatile u32 arm_claim, read_claim, armed;
/* The native fixture provisions these DIP-local bounds before any call. */
volatile struct nd_inputs nd_input_provision;
static struct nd_inputs bound_inputs;
struct nd_record nd_trace[ND_RECORDS] LINE;
u32 nd_checks[ND_RECORDS] LINE;
struct nd_line nd_commit LINE;
/* Reserved for the independent reader. The writer never touches this line. */
struct nd_line nd_reader LINE;
ASSERT_SIZE(record_stride, sizeof(struct nd_record) == 32);
ASSERT_SIZE(arm_extent, sizeof(struct nd_arm) == 96);
ASSERT_SIZE(commit_extent, sizeof(struct nd_line) == 32);

OBSERVED void nd_emit(unsigned event, u32 a, u32 b)
{
    struct nd_record *r;
    u32 i, check = 2166136261U;
    if (nd.frozen || nd.seq >= ND_RECORDS)
        return;
    r = &nd_trace[nd.seq];
    r->seq = nd.seq + 1;
    r->instance = nd.arm.instance;
    memcpy(r->tag, nd.arm.request, 8);
    r->tick = nd.tick;
    r->event = event;
    r->phase = nd.phase;
    r->operation = nd.op;
    r->attempt = nd.attempt;
    r->a = a;
    r->b = b;
    for (i = 0; i < sizeof(*r); ++i)
        check = (check ^ ((const u8 *)r)[i]) * 16777619U;
    nd_checks[nd.seq] = check;
    /* The reviewed syscall cleans the range and drains the write buffer. */
    os_sync_after_write(r, sizeof(*r));
    os_sync_after_write(&nd_checks[nd.seq], sizeof(check));
    __asm__ volatile ("" ::: "memory");
    nd_commit.word[0] = ++nd.seq;
    os_sync_after_write(&nd_commit, sizeof(nd_commit));
}

void nd_bytes(unsigned event, const u8 *data, unsigned count)
{
    while (count) {
        u32 words[2] = {0, 0};
        unsigned n = count > 8 ? 8 : count;
        memcpy(words, data, n);
        nd_emit(event + n, words[0], words[1]);
        data += n;
        count -= n;
    }
}

void nd_begin_cleanup(u32 epoch)
{
    if (!nd.cleanup_latched) {
        nd.cleanup_start = epoch;
        nd.cleanup_latched = 1;
    }
}

static void abandon(void)
{
    /* Validation before an exchange owns no timed resources. Keep nd.tick as
     * the previous lease-checked sample for the next modular gap check. */
    if (!nd.cleanup_latched)
        nd_begin_cleanup(nd.phase ? (u32)os_timer_now(0) : nd.tick);
}

OBSERVED int nd_fail(unsigned why, u32 detail)
{
    if (!nd.failed) {
        abandon();
        nd.failed = why;
        nd_emit(FIRST_FAILURE, why, detail);
    }
    return 0;
}

OBSERVED int nd_pin(unsigned why, u32 detail)
{
    abandon();
    nd.pinned = 1;
    nd_emit(QUARANTINE, why, detail);
    return nd_fail(why, detail);
}

OBSERVED s32 nd_finish(void)
{
    s32 result = nd.failed ? -1 : 1;
    nd_emit(TERMINAL, result, nd.seq + 1);
    nd.frozen = 1;
    return result;
}

/* Limit the fixture to normalised physical MEM1 IPC spans. The kernel must
 * validate the actual live mapping and GX must keep the output exclusive. */
static int live(const ioctl *c, const void *p, u32 n)
{
    u32 addr = (u32)p, envelope = (u32)c;
    if (!addr || !n || addr >= MEM1_SIZE || n > MEM1_SIZE - addr)
        return 0;
    return envelope >= MEM1_SIZE || addr+n <= envelope || envelope+sizeof(*c) <= addr;
}

static int separate(ioctl *c)
{
    u32 in = (u32)c->inbuf, out = (u32)c->iobuf;
    return live(c, c->inbuf, c->inlen) && live(c, c->iobuf, c->iolen)
        && !((in | out) & 31) && (in + c->inlen <= out || out + c->iolen <= in);
}

static int valid_reservation(const ioctl *c, const struct nd_extent *r, u32 minimum)
{
    u32 out = (u32)c->iobuf;
    /* separate() has already validated the live arm output and its end. */
    return !((r->base | r->end) & 31) && r->base < r->end && r->end <= MEM1_SIZE
        && r->end - r->base >= minimum && live(c, (void *)r->base, r->end - r->base)
        && (r->end <= out || out + c->iolen <= r->base);
}

static int starts_in(const struct nd_extent *r, u32 addr)
{
    return r->base <= addr && addr < r->end;
}

static int sync_owned_input(const ioctl *c, const struct nd_extent *r)
{
    u32 addr = (u32)c->inbuf, first, end;
    if (!starts_in(r, addr) || !c->inlen || c->inlen > r->end - addr)
        return 0;
    /* addr + inlen is now bounded by the validated MEM1 end. Round the
     * original exclusive end, even when the start is partway into a line. */
    first = addr & ~31U;
    end = (addr + c->inlen + 31U) & ~31U;
    if (first < r->base || end > r->end || !live(c, (void *)first, end - first))
        return 0;
    os_sync_before_read((void *)first, end - first);
    return 1;
}

static s32 reject(unsigned why, u32 detail)
{
    abandon();
    nd_emit(REJECT, why, detail);
    nd_fail(why, detail);
    return nd_finish();
}

static int unicast(u32 ip)
{
    unsigned first = ip >> 24;
    return first && first != 127 && first < 224;
}

static OBSERVED s32 admit_arm(ioctl *c, s32 fd)
{
    struct nd_arm snapshot;
    struct nd_inputs inputs;
    const struct nd_arm *a = &snapshot;
    u32 receipt[8];
    static const u32 zeros[6] = {0};
    if (nd_take(&arm_claim))
        return -1;
    inputs = nd_input_provision;
    if (c->inlen != sizeof(*a) || c->iolen != 32 || !separate(c)
        || !valid_reservation(c, &inputs.arm, sizeof(*a))
        || !valid_reservation(c, &inputs.read, 32)
        || !(inputs.arm.end <= inputs.read.base || inputs.read.end <= inputs.arm.base)
        || !sync_owned_input(c, &inputs.arm))
        return reject(BAD_ARM, fd);
    memcpy(&snapshot, c->inbuf, sizeof(snapshot));
    memcpy(receipt, a->request, sizeof(a->request));
    if (!(receipt[0] | receipt[1]) || !(receipt[2] | receipt[3] | receipt[4] | receipt[5])
        || memcmp(a->reserved, zeros, sizeof(zeros)) || a->version != ND_VERSION
        || a->instance != ND_INSTANCE || a->slot != ND_SLOT
        || a->dip_build != ND_DIP_BUILD || a->gx_build != ND_GX_BUILD
        || fd < 0 || a->fd != (u32)fd || a->command != ND_READ || a->length != 32
        || !unicast(a->host) || !unicast(a->peer) || a->peer == a->host || !a->port || a->port > 65535)
        return reject(BAD_ARM, fd);
    memcpy(&nd.arm, a, sizeof(*a));
    bound_inputs = inputs;
    nd.output = (u32)c->iobuf;
    receipt[2] = a->instance;
    receipt[3] = a->slot;
    receipt[4] = a->dip_build;
    receipt[5] = a->gx_build;
    receipt[6] = fd;
    receipt[7] = nd.output;
    memcpy(c->iobuf, receipt, sizeof(receipt));
    os_sync_after_write(c->iobuf, sizeof(receipt));
    nd_emit(BIND, a->dip_build, a->gx_build);
    nd_emit(BIND, a->slot, fd);
    nd_emit(TUPLE, a->command, a->length);
    nd_emit(TUPLE, a->offset, nd.output);
    nd_emit(ENDPOINT, a->host, a->peer);
    nd_emit(ARM_OK, a->port, (u32)&nd_reader);
    __asm__ volatile ("" ::: "memory");
    armed = 1;
    return 1;
}

OBSERVED s32 nd_hook(ioctl *c, s32 fd)
{
    const u32 *in = c->inbuf;
    int arm_input, read_input;
    s32 tid, status;
    u32 handback[8];
    if (!armed)
        return c->command == ND_ARM ? admit_arm(c, fd) : 0;
    __asm__ volatile ("" ::: "memory");
    arm_input = starts_in(&bound_inputs.arm, (u32)in);
    read_input = starts_in(&bound_inputs.read, (u32)in);
    if (!arm_input && !read_input && (u32)c->iobuf != nd.output)
        return 0;
    if (read_claim)
        return -1;
    if (arm_input && c->command == ND_ARM && c->inlen == sizeof(nd.arm) && c->iolen == 32
        && (u32)c->iobuf == nd.output && (u32)fd == nd.arm.fd && separate(c)
        && sync_owned_input(c, &bound_inputs.arm) && !memcmp(in, &nd.arm, sizeof(nd.arm)))
        return -1; /* Genuine arm replay preserves the unspent read opportunity. */
    if (nd_take(&read_claim))
        return -1;
    if (!read_input || c->command != ND_READ || c->inlen != 32
        || !sync_owned_input(c, &bound_inputs.read) || c->iolen != nd.arm.length
        || !separate(c) || (u32)c->iobuf != nd.output || (u32)fd != nd.arm.fd)
        return reject(BAD_READ, c->command);
    if (in[0] != ND_READ << 24 || in[1] != nd.arm.length || in[2] != nd.arm.offset
        || memcmp(in + 3, nd.arm.request, 8) || in[5] || in[6] || in[7])
        return reject(BAD_READ, c->command);
    tid = os_get_thread_id();
    nd_emit(ENTRY, tid, fd);
    if (tid < 0)
        return reject(BAD_TID, tid);
    status = nd_exchange();
    memcpy(handback, nd.arm.request, 8);
    handback[2] = nd.arm.instance;
    handback[3] = nd.seq + 1;
    handback[4] = status;
    handback[5] = nd.failed;
    handback[6] = nd.pinned;
    handback[7] = tid;
    memcpy(c->iobuf, handback, sizeof(handback));
    os_sync_after_write(c->iobuf, sizeof(handback));
    return nd_finish();
}
