// SPDX-License-Identifier: GPL-3.0-only
#include <string.h>
#include "netdisc.h"
#include "syscalls.h"

enum phase { BRINGUP = 1, CONNECTING, EXCHANGING, CLEANUP };
enum resource { NCD, SO, KD, SOCKET, RESOURCES };
enum disposition { NONE, UNRESOLVED, KNOWN, RELEASED, NOT_ACQUIRED };
enum op {
    OPEN_NCD = 1, LINK, CLOSE_NCD, OPEN_SO, OPEN_KD, START_KD, CLOSE_KD,
    START_SO, HOST, NEW_SOCKET, CONNECT, SEND, RECEIVE, CLOSE_SOCKET, CLOSE_SO
};
enum { QWORDS = 8, TIMER_BASE = 0x4e440000 };
struct binding { s32 fd; u8 state, acquired, close_attempt, parent; };
static struct binding bindings[RESOURCES];
static char paths[3][32] LINE = {"/dev/net/ncd/manage", "/dev/net/ip/top", "/dev/net/kd/request"};
ipcmessage nd_completions[ND_LIMIT] LINE;
static u32 queue_words[QWORDS] LINE;
static u32 control[16] LINE;
static u32 service[8] LINE;
static u8 scratch[32] LINE;
static u8 frame[32] LINE;
static union { ioctlv v[3]; u8 line[32]; } vectors LINE;
static s32 queue_id, timers[4], result;
static unsigned armed_timers, live_timers, queue_live, sent, received, active, verified;
ASSERT_SIZE(ipc_extent, sizeof(ipcmessage) == 32);
ASSERT_SIZE(pool_extent, sizeof(nd_completions) == 2048);
ASSERT_SIZE(pool_alignment, __alignof__(nd_completions) == 32);
ASSERT_SIZE(vector_extent, sizeof(ioctlv) == 8 && sizeof(vectors) == 32);
ASSERT_SIZE(queue_extent, sizeof(queue_words) == 32);

static int sample(void)
{
    u32 now, gap, tag[2];
    memcpy(tag, nd.arm.request, sizeof(tag));
    /* Independent one-shot fixture lease, cleared at its absolute cutoff.
     * A repeated counter value alone cannot exclude an entire missed wrap. */
    os_sync_before_read(&nd_reader, sizeof(nd_reader));
    now = (u32)os_timer_now(0);
    gap = now - nd.tick;
    nd.tick = now;
    if (nd_reader.word[0] != 1 || nd_reader.word[1] != nd.arm.instance
        || nd_reader.word[2] != tag[0]
        || nd_reader.word[3] != tag[1] || nd_reader.word[4] != 55)
        return nd_pin(CLOCK_GAP, gap);
    if (gap >= 0x80000000U)
        return nd_pin(CLOCK_GAP, gap);
    return 1;
}

static OBSERVED int timely(void)
{
    if (!sample())
        return 0;
    if (nd.tick - nd.start >= nd.budget) {
        nd_begin_cleanup(nd.tick);
        nd_emit(EXPIRED, nd.start, nd.budget);
        return nd_fail(DEADLINE, nd.tick - nd.start);
    }
    return 1;
}

static int phase(unsigned p)
{
    s32 timer, delay = p == BRINGUP ? 30000000 : 5000000;
    nd.phase = p;
    nd.start = p == CLEANUP ? nd.cleanup_start : nd.tick;
    nd.budget = p == BRINGUP ? 56953125 : 9492187;
    nd_emit(PHASE, nd.start, nd.budget);
    if (p == CLEANUP) {
        u32 remaining;
        if (!nd.cleanup_latched || !timely())
            return 0;
        remaining = nd.budget - (nd.tick - nd.start);
        delay = (remaining * 128U + 242U) / 243U;
    }
    timer = os_create_timer(delay, 0, queue_id, TIMER_BASE + p);
    nd_emit(TIMER, p, timer);
    if (timer < 0)
        return nd_pin(TIMER_ERROR, timer);
    timers[p-1] = timer;
    armed_timers |= 1U << p;
    live_timers |= 1U << p;
    return timely();
}

static void record_binding(unsigned owner)
{
    struct binding *b = &bindings[owner];
    nd_emit(LEDGER, owner << 24 | b->state << 16 | b->parent << 8 | b->acquired, b->fd);
}

static void disposition(unsigned owner, unsigned state)
{
    bindings[owner].state = state;
    record_binding(owner);
}

/* Inspect a complete batch through a nonblocking empty observation before
 * assigning ownership. An old address or a second word poisons this loan. */
static OBSERVED int inspect_queue(ipcmessage *current, int *matched)
{
    unsigned i, words = 0, hits = 0, fault = 0;
    u32 word, offending = 0, base = (u32)nd_completions;
    *matched = 0;
    for (i = 0; i <= QWORDS; ++i) {
        s32 status = os_message_queue_receive(queue_id, &word, 1);
        if (status == -7)
            break;
        if (status != 0)
            return nd_pin(QUEUE_ERROR, status);
        if (i == QWORDS)
            return nd_pin(QUEUE_ERROR, word);
        if (word > TIMER_BASE && word <= TIMER_BASE + 4) {
            if (!(armed_timers & (1U << (word - TIMER_BASE)))) {
                fault = UNARMED_TIMER;
                offending = word;
            }
            continue;
        }
        ++words;
        if (current && word == (u32)current) {
            ++hits;
        } else if (!fault) {
            fault = (word >= base && word-base < nd.attempt * 32U && !((word-base) & 31))
                ? OLD_WORD : UNKNOWN_WORD;
            offending = word;
        }
    }
    if (fault)
        nd_emit(QUEUE_FAULT, fault, offending);
    if (words > 1)
        return nd_pin(MULTIPLE_WORDS, words << 16 | hits);
    if (fault)
        return nd_pin(fault, offending);
    *matched = hits;
    return 1;
}

static void vector(unsigned i, void *ptr, unsigned size)
{
    vectors.v[i].data = ptr;
    vectors.v[i].len = size;
}

static s32 submit_ioctl(s32 fd, unsigned cmd, unsigned insize, unsigned outsize, ipcmessage *cb)
{
    return os_ioctl_async(fd, cmd, insize ? control : NULL, insize,
                          outsize ? service : NULL, outsize, queue_id, cb);
}

static OBSERVED s32 submit(unsigned op, unsigned owner, ipcmessage *cb)
{
    s32 so = bindings[SO].fd;
    switch (op) {
    case OPEN_NCD: case OPEN_KD: case OPEN_SO:
        return os_open_async(paths[owner], 0, (void *)queue_id, cb);
    case CLOSE_NCD: case CLOSE_KD: case CLOSE_SO:
        return os_close_async(bindings[owner].fd, (void *)queue_id, cb);
    case LINK:
        return os_ioctlv_async(bindings[NCD].fd, 7, 0, 1, vectors.v, queue_id, cb);
    case START_KD: return submit_ioctl(bindings[KD].fd, 6, 0, 32, cb);
    case START_SO: return submit_ioctl(so, 31, 0, 0, cb);
    case HOST: return submit_ioctl(so, 16, 0, 0, cb);
    case NEW_SOCKET: return submit_ioctl(so, 15, 12, 0, cb);
    case CONNECT: return submit_ioctl(so, 4, 36, 0, cb);
    case SEND: return os_ioctlv_async(so, 13, 2, 0, vectors.v, queue_id, cb);
    case RECEIVE: return os_ioctlv_async(so, 12, 1, 2, vectors.v, queue_id, cb);
    case CLOSE_SOCKET: /* On the original parent SO handle. */
        return submit_ioctl(so, 3, 4, 0, cb);
    default:
        return -1;
    }
}

static void prepare(unsigned op, unsigned owner, ipcmessage *cb)
{
    memset(cb, 0, sizeof(*cb));
    memset(control, 0, sizeof(control));
    memset(&vectors, 0, sizeof(vectors));
    memset(service, 0xff, sizeof(service));
    memset(scratch, 0, sizeof(scratch));
    control[0] = bindings[SOCKET].fd;
    switch (op) {
    case OPEN_NCD: case OPEN_KD: case OPEN_SO:
        os_sync_after_write(paths[owner], 32);
        break;
    case LINK: vector(0, service, 32); break;
    case NEW_SOCKET:
        control[0] = 2;
        control[1] = 1;
        break;
    case CONNECT:
        control[1] = 1;
        control[2] = 0x08020000 | nd.arm.port;
        control[3] = nd.arm.peer;
        break;
    case SEND:
        memcpy(scratch, nd.arm.request + sent, 24 - sent);
        vector(0, scratch, 24 - sent);
        vector(1, control, 40);
        break;
    case RECEIVE:
        vector(0, control, 8);
        vector(1, scratch, 28 - received);
        vector(2, NULL, 0);
        break;
    }
    os_sync_after_write(control, sizeof(control));
    os_sync_after_write(&vectors, sizeof(vectors));
    os_sync_after_write(service, sizeof(service));
    os_sync_after_write(scratch, sizeof(scratch));
    os_sync_after_write(cb, sizeof(*cb));
}

static unsigned obligations(void)
{
    unsigned i, count = 0;
    for (i = 0; i < RESOURCES; ++i)
        count += bindings[i].state == KNOWN;
    return count;
}

static int bind_result(unsigned owner, int acquire, int close)
{
    struct binding *b = &bindings[owner];
    unsigned i;
    if (acquire) {
        if (result < 0) {
            /* Only a retired SO_SOCKET reply can settle this failed acquisition.
             * RM open and a bare trap error have different dispositions. */
            if (nd.op == NEW_SOCKET && owner == SOCKET) {
                nd_begin_cleanup(nd.tick);
                disposition(owner, NOT_ACQUIRED);
                active = 0;
                return nd_fail(RM_ERROR, result);
            }
            return nd_pin(RM_ERROR, result);
        }
        b->fd = result;
        if (owner != SOCKET)
            for (i = 0; i < SOCKET; ++i)
                if (i != owner && bindings[i].state == KNOWN && bindings[i].fd == result) {
                    disposition(i, UNRESOLVED);
                    disposition(owner, UNRESOLVED);
                    return nd_pin(FD_COLLISION, result);
                }
        disposition(owner, KNOWN);
    } else if (close) {
        if (result != 0)
            return nd_pin(RM_ERROR, result);
        disposition(owner, RELEASED);
    }
    return 1;
}

extern void os_thread_yield(void); /* d2x syscalls.s, trap 7 */

static OBSERVED void receive_handoff(unsigned count)
{
    os_sync_before_read(scratch, count);
    memcpy(frame + received, scratch, count);
}

static OBSERVED int operation(unsigned op, unsigned owner)
{
    int acquire = op == OPEN_NCD || op == OPEN_SO || op == OPEN_KD || op == NEW_SOCKET;
    int close = op == CLOSE_NCD || op == CLOSE_KD || op == CLOSE_SOCKET || op == CLOSE_SO;
    struct binding *b = &bindings[owner];
    unsigned reserve, required, next, intent;
    ipcmessage *cb;
    s32 raw;
    int match, on_time;
    nd.op = op;
    if (nd.pinned || active || !inspect_queue(NULL, &match) || !timely())
        return 0;
    if ((!acquire && b->state != KNOWN) || (acquire && b->state != NONE)
        || (close && b->close_attempt) || (owner == SOCKET
            && (bindings[SO].state != KNOWN || (!acquire && b->parent != bindings[SO].acquired))))
        return nd_pin(BAD_REPLY, owner);
    reserve = obligations() + acquire - close;
    if (nd.attempt + 1 + reserve > ND_LIMIT)
        return nd_fail(SUBMIT_LIMIT, reserve);
    /* Keep five records per reserved close. Work also reserves the cleanup
     * transition, verification, failure and terminal records. */
    required = nd.phase == CLEANUP ? 5 + 14 : 8 + 28;
    if (nd.seq + required + 5 * reserve > ND_RECORDS)
        return nd_fail(TRACE_LIMIT, nd.seq);
    cb = &nd_completions[nd.attempt];
    prepare(op, owner, cb);
    next = nd.attempt + 1U;
    intent = next << 16 | owner << 8 | (acquire ? next : b->acquired);
    nd_emit(INTENT, (u32)cb, intent);
    if (!timely()) {
        nd_emit(NOT_ISSUED, (u32)cb, intent);
        return 0;
    }
    /* Only local bookkeeping between the last sample and trap selection. */
    nd.attempt = next;
    active = next;
    if (acquire) {
        b->acquired = active;
        b->fd = -1;
        b->parent = owner == SOCKET ? bindings[SO].acquired : 0;
    }
    if (close)
        b->close_attempt = active;
    if (acquire || close)
        b->state = UNRESOLVED;
    raw = submit(op, owner, cb);
    timely();
    nd_emit(SUBMITTED, raw, (u32)cb);
    if (acquire || close)
        record_binding(owner);
    if (raw != 0)
        return nd_pin(SUBMIT_ERROR, raw);
    if (nd.pinned)
        return 0;
    for (;;) {
        if (!inspect_queue(cb, &match))
            return 0;
        if (match)
            break;
        if (!timely())
            return nd_pin(DEADLINE, active);
        os_thread_yield();
    }
    os_sync_before_read(cb, sizeof(*cb));
    result = (s32)cb->result;
    on_time = timely();
    nd_emit(COMPLETED, cb->command, result);
    if (nd.pinned)
        return 0;
    if (cb->command != 8)
        return nd_pin(BAD_REPLY, cb->command);
    if (!bind_result(owner, acquire, close))
        return 0;
    /* The matched producer must have retired before reading its outputs. */
    if (op == LINK || op == START_KD) {
        os_sync_before_read(service, 32);
        nd_emit(SERVICE, service[0], service[1]);
    }
    if (op == RECEIVE && result > 0 && (u32)result <= 28 - received)
        receive_handoff(result);
    active = 0;
    return on_time && timely();
}

static int zero_result(void)
{
    return result == 0 || nd_fail(RM_ERROR, result);
}

static OBSERVED int bringup(void)
{
    if (!operation(OPEN_NCD, NCD))
        return 0;
    do {
        if (!operation(LINK, NCD) || !zero_result())
            return 0;
        if (service[0] != 0)
            return nd_fail(BAD_SERVICE, service[0]);
    } while (service[1] == 1);
    if (service[1] != 3)
        return nd_fail(BAD_SERVICE, service[1]);
    if (!operation(CLOSE_NCD, NCD) || !operation(OPEN_SO, SO) || !operation(OPEN_KD, KD))
        return 0;
    do {
        if (!operation(START_KD, KD) || !zero_result())
            return 0;
    } while ((s32)service[0] == -29);
    if (service[0] && (s32)service[0] != -15)
        return nd_fail(BAD_SERVICE, service[0]);
    if (!operation(CLOSE_KD, KD) || !operation(START_SO, SO) || !zero_result())
        return 0;
    do {
        if (!operation(HOST, SO))
            return 0;
    } while (!result);
    return (u32)result == nd.arm.host || nd_fail(BAD_SERVICE, result);
}

static OBSERVED int transfer(unsigned op, unsigned *offset, unsigned size)
{
    while (*offset < size) {
        if (!operation(op, SOCKET))
            return 0;
        if (result == -6 || result == -27) /* raw SO EAGAIN and EINTR */
            continue;
        if (!result)
            return nd_fail(op == RECEIVE ? END_OF_STREAM : BAD_COUNT, 0);
        if (result < 0)
            return nd_fail(RM_ERROR, result);
        if ((u32)result > size - *offset)
            return nd_pin(BAD_COUNT, result);
        nd_bytes(op == SEND ? TX_BYTES : RX_BYTES,
                 op == SEND ? nd.arm.request + *offset : frame + *offset, result);
        *offset += result;
    }
    return 1;
}

static OBSERVED int verify_reply(void)
{
    u32 id;
    int echo = memcmp(frame, nd.arm.request, 24) == 0;
    memcpy(&id, frame + 24, 4);
    if (!timely())
        return 0;
    if (!id || !echo)
        return nd_fail(ECHO_ERROR, id);
    nd_begin_cleanup(nd.tick);
    verified = id;
    nd_bytes(VERIFIED_BYTES, frame, 28);
    nd_emit(VERIFIED, id, received);
    return 1;
}

static OBSERVED void cleanup(void)
{
    static const u8 closes[RESOURCES] = {CLOSE_NCD, CLOSE_SO, CLOSE_KD, CLOSE_SOCKET};
    int i, match;
    if (!phase(CLEANUP))
        return;
    for (i = SOCKET; i >= 0; --i)
        if (bindings[i].state == KNOWN && !operation(closes[i], i))
            return;
    for (i = 3; i >= 0; --i) {
        if (!timely())
            return;
        if (live_timers & (1U << (i + 1))) {
            s32 rc = os_destroy_timer(timers[i]);
            nd_emit(TIMER_END, timers[i], rc);
            if (rc != 0) {
                nd_pin(TIMER_ERROR, rc);
                return;
            }
            live_timers &= ~(1U << (i + 1));
        }
    }
    if (timely() && inspect_queue(NULL, &match)) {
        s32 rc = os_message_queue_destroy(queue_id);
        nd_emit(QUEUE_END, queue_id, rc);
        if (rc != 0)
            nd_pin(QUEUE_ERROR, rc);
        else
            queue_live = 0;
        timely();
    }
}

OBSERVED s32 nd_exchange(void)
{
    nd.tick = (u32)os_timer_now(0);
    queue_id = os_message_queue_create(queue_words, QWORDS);
    nd_emit(QUEUE, queue_id, QWORDS);
    if (queue_id < 0)
        nd_fail(QUEUE_ERROR, queue_id);
    else {
        queue_live = 1;
        if (phase(BRINGUP) && bringup() && timely()
            && phase(CONNECTING) && operation(NEW_SOCKET, SOCKET)
            && operation(CONNECT, SOCKET) && zero_result() && timely()
            && phase(EXCHANGING) && transfer(SEND, &sent, 24)
            && transfer(RECEIVE, &received, 28))
            verify_reply();
        if (!nd.pinned)
            cleanup();
        if (!nd.pinned && (obligations() || queue_live || live_timers))
            nd_pin(RM_ERROR, obligations());
    }
    nd_emit(FINISH, queue_live, live_timers);
    nd_emit(FINISH, verified, active << 16 | nd.pinned << 8 | obligations());
    return nd.failed ? -1 : 1;
}
