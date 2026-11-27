/* SPDX-License-Identifier: GPL-3.0-only
 * Linux i386 process, one fresh BSS per scenario, no hardware or target traps. */
#include <stdarg.h>
#include "netdisc.c"
#include "netdisc_net.c"

#define CHECK(expr) do { if (!(expr)) return failed(#expr, sizeof(#expr)-1); } while (0)
static int failed(const char *expr, u32 size)
{
    /* The exit status is only eight bits. Write the failed check to stderr. */
    __asm__ volatile("int $0x80" : : "a"(4), "b"(2), "c"(expr), "d"(size) : "memory");
    return 1;
}
static struct nd_arm input LINE;
static u32 read_packet[24] LINE, output[8] LINE, ordinary_output[8] LINE;
/* One isolated native page lets the kernel catch even an ordinary load from foreign input. */
static u32 other[1024] __attribute__((aligned(4096)));
static u8 main_read[sizeof(read_packet)], main_other[sizeof(other)];
static unsigned now, delivered_at, socket_closes, so_closes, handoffs, input_syncs;
static u32 sync_calls, last_sync, last_sync_size;
static int scenario, cleanup_delay, close_order, stale_copy, repeat_word;
static ipcmessage *pending;

void *memset(void *dst, int ch, size_t n)
{
    u8 *d = dst;
    while (n--) *d++ = ch;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
    u8 *d = dst;
    const u8 *s = src;
    while (n--) *d++ = *s++;
    return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const u8 *x = a, *y = b;
    while (n--) { if (*x != *y) return *x - *y; ++x; ++y; }
    return 0;
}

/* StarStruck DCInvalidateRange rounds the start down before adding length.
 * Dropping a line exposes its main-memory bytes and discards local dirt. */
static void invalidate_model(void *ptr, u32 count, void *cached, const u8 *memory, u32 size)
{
    u32 address = (u32)ptr, start = address & ~31U;
    u32 offset = start - (u32)cached, bytes = (count + 31U) & ~31U;
    if (offset < size && bytes <= size - offset)
        memcpy((u8 *)cached + offset, memory + offset, bytes);
}

void os_sync_before_read(void *p, s32 n)
{
    ++sync_calls;
    last_sync = (u32)p;
    last_sync_size = n;
    if (scenario == 'X' || scenario == 'O' || scenario == 'Q' || scenario == 'c' || scenario == 'h') {
        invalidate_model(p, n, read_packet, main_read, sizeof(read_packet));
        invalidate_model(p, n, other, main_other, sizeof(other));
    }
    if (scenario == 't' && p == &nd_reader && nd.seq && nd.op == CLOSE_SOCKET
        && nd_trace[nd.seq-1].event == INTENT)
        now = nd.cleanup_start + 9492187;
    if (p == &input && n == sizeof(input)) ++input_syncs;
    if (p == scratch && nd.op == RECEIVE) {
        if (!active || n != 1) stale_copy = 1;
        ++handoffs;
        scratch[0] = received < 24 ? nd.arm.request[received] : 0x31;
    }
}

static int protect_foreign_page(int prot)
{
    int status;
    /* Linux i386 mprotect for the foreign input page only. */
    __asm__ volatile("int $0x80" : "=a"(status)
                     : "0"(125), "b"(other), "c"(sizeof(other)), "d"(prot) : "memory");
    return status;
}
void os_sync_after_write(void *p, s32 n)
{
    if (p == &nd_commit && nd.seq && nd_trace[nd.seq-1].event == INTENT) {
        if (nd.op == CLOSE_SOCKET && (scenario == 'u' || scenario == 'U'))
            now = nd.cleanup_start + 9492187 - (scenario == 'u');
        if (nd.op == OPEN_NCD && scenario == 'N')
            now = nd.start + nd.budget;
        if (nd.phase == BRINGUP && nd.op == CLOSE_KD && scenario == 'K')
            now = nd.start + nd.budget;
    }
    if (scenario == 'Z' && nd.seq < ND_RECORDS && p == &nd_trace[nd.seq]
        && nd_trace[nd.seq].event == VERIFIED)
        now = 11390625; /* Six seconds elapse publishing the already verified exchange. */
}
u32 nd_take(volatile u32 *once) { return __sync_lock_test_and_set(once, 1); }
s32 os_get_thread_id(void) { return 7; }
s32 os_timer_now(s32 id) { return now; }
s32 os_create_timer(s32 delay, s32 repeat, s32 q, s32 msg)
{
    if (msg == TIMER_BASE + CLEANUP) cleanup_delay = delay;
    return msg - TIMER_BASE;
}
s32 os_destroy_timer(s32 id) { return 0; }
s32 os_message_queue_create(void *p, u32 cap) { return 0; }
s32 os_message_queue_destroy(s32 q) { return 0; }
void os_thread_yield(void) {}
s32 os_message_queue_receive(s32 q, u32 *word, u32 flags)
{
    if (!pending) return -7;
    if (nd.op == CONNECT && delivered_at) now = delivered_at;
    *word = (u32)pending;
    if (repeat_word) repeat_word = 0;
    else pending = NULL;
    return 0;
}
static s32 reply(ipcmessage *cb, s32 value)
{
    cb->command = 8;
    cb->result = value;
    pending = cb;
    return 0;
}
s32 os_open_async(const char *path, s32 mode, void *q, void *cb)
{
    if (nd.op == OPEN_KD && scenario == 'M') return reply(cb, -24);
    return reply(cb, nd.op == OPEN_SO ? 0 : 1);
}
s32 os_close_async(s32 fd, void *q, void *cb)
{
    if (nd.op == CLOSE_SO) { ++so_closes; close_order = 10*close_order + 2; }
    return reply(cb, 0);
}
s32 os_ioctl_async(s32 fd, s32 cmd, void *in, s32 n, void *out, s32 len, ...)
{
    va_list ap;
    ipcmessage *cb;
    va_start(ap, len);
    (void)va_arg(ap, s32);
    cb = va_arg(ap, ipcmessage *);
    va_end(ap);
    switch (nd.op) {
    case START_KD: service[0] = 0; break;
    case HOST: return reply(cb, nd.arm.host);
    case NEW_SOCKET:
        if (scenario == 'T') return -24;
        if (scenario == 'F') return reply(cb, -24);
        if (scenario == 'C') { repeat_word = 1; return reply(cb, -24); }
        if (scenario == 'Y') { now = 11390625; return 0; } /* Lost completion. */
        break; /* Socket zero on SO fd zero. */
    case CONNECT: if (delivered_at) now = 11390625; break; /* Six seconds. */
    case CLOSE_SOCKET: ++socket_closes; close_order = 10*close_order + 1;
        if (scenario == 'V') return -7;
        if (scenario == 'J') ++now; /* First close exhausts the last tick. */
        break;
    }
    return reply(cb, 0);
}
s32 os_ioctlv_async(s32 fd, s32 cmd, s32 ni, s32 no, ioctlv *v, ...)
{
    va_list ap;
    ipcmessage *cb;
    va_start(ap, v);
    (void)va_arg(ap, s32);
    cb = va_arg(ap, ipcmessage *);
    va_end(ap);
    if (nd.op == LINK) { service[0] = 0; service[1] = 3; return reply(cb, 0); }
    return reply(cb, nd.op == RECEIVE ? 1 : (s32)v[0].len);
}

int run(int mode)
{
    const u32 six = 11390625, cleanup_ticks = 9492187;
    unsigned i;
    ioctl arm = {ND_ARM, (u32 *)&input, sizeof(input), output, sizeof(output)};
    ioctl read = {ND_READ, read_packet, 32, output, 32};
    scenario = mode;
    /* The driver owns these allocations. The ioctls do not supply this provision. */
    struct nd_inputs provision = {
        {(u32)&input, (u32)&input + sizeof(input)},
        {(u32)read_packet, (u32)read_packet + sizeof(read_packet)}
    };
    nd_input_provision = provision;
    input.version = ND_VERSION; input.instance = ND_INSTANCE; input.slot = ND_SLOT;
    input.dip_build = ND_DIP_BUILD; input.gx_build = ND_GX_BUILD;
    input.command = ND_READ; input.length = 32; input.host = 0xc0a80101;
    input.peer = input.host+1; input.port = 1234;
    for (i = 0; i < sizeof(input.request); ++i) input.request[i] = i+1;
    read_packet[0] = ND_READ << 24; read_packet[1] = 32;
    memcpy(read_packet+3, input.request, 8);
    switch (mode) {
    case '0': memset((void *)&nd_input_provision, 0, sizeof(nd_input_provision)); break;
    case '1': ++nd_input_provision.arm.base; break;
    case '2': --nd_input_provision.read.end; break;
    case '3': nd_input_provision.arm.end = provision.arm.base + 64; break;
    case '4': nd_input_provision.read.end = provision.read.base - 32; break;
    case '5': nd_input_provision.read.end = ~31U; break;
    case '6': nd_input_provision.read = provision.arm; break;
    case '7': arm.iobuf = read_packet + 8; break; /* In the idle part of the read reservation. */
    case '8': arm.inbuf = read_packet; break;    /* Right bytes, wrong role. */
    case '9': arm.inbuf = other; break;          /* Plausible aligned foreign storage. */
    }
    if (mode >= '0' && mode <= '9') {
        if (mode == '8' || mode == '9')
            memcpy(arm.inbuf, &input, sizeof(input));
        CHECK(protect_foreign_page(0) == 0);
        CHECK(nd_hook(&arm, 0) == -1 && nd.failed == BAD_ARM && nd.frozen);
        CHECK(protect_foreign_page(3) == 0);
        CHECK(!sync_calls && !nd.output && !bound_inputs.arm.base && !bound_inputs.read.base);
        nd_input_provision = provision;
        arm.inbuf = (u32 *)&input;
        arm.iobuf = output;
        CHECK(nd_hook(&arm, 0) == -1 && !nd.attempt && !sync_calls);
        return 0;
    }
    if (mode == 'I' || mode == 'S' || mode == 'P') {
        if (mode == 'I') arm.iolen = 0;
        else if (mode == 'P') arm.inbuf = NULL;
        else input.version = 42;
        CHECK(nd_hook(&arm, 0) == -1 && nd.failed == BAD_ARM);
        CHECK(input_syncs == (mode == 'S'));
        CHECK(nd.output == 0 && !nd.arm.request[0] && !nd.attempt);
        read.iobuf = other;
        CHECK(nd_hook(&read, 0) == 0); /* Rejected input cannot bind this tag. */
        arm.inbuf = (u32 *)&input; arm.iolen = 32; input.version = ND_VERSION;
        CHECK(nd_hook(&arm, 0) == -1 && !nd.attempt);
        return 0;
    }
    CHECK(nd_hook(&arm, 0) == 1 && input_syncs == 1);
    nd_reader.word[0] = 1; nd_reader.word[1] = ND_INSTANCE; nd_reader.word[4] = 55;
    memcpy((void *)&nd_reader.word[2], input.request, 8);
    if (mode == 'X') {
        ioctl malformed = {ND_READ, read_packet + 4, 32, other, 32};
        s32 first, duplicate;
        memset(read_packet, 0, sizeof(read_packet));
        ((u8 *)read_packet)[64] = 0xa5;
        memcpy(main_read + 28, input.request, 8); /* Only memory has both new tag words. */
        first = nd_hook(&malformed, 0);
        CHECK(sync_calls == 2 && last_sync == (u32)read_packet && last_sync_size == 64);
        CHECK(!memcmp((u8 *)read_packet + 28, input.request, 8) && ((u8 *)read_packet)[64] == 0xa5);
        memset(read_packet, 0, sizeof(read_packet));
        read_packet[0] = ND_READ << 24;
        read_packet[1] = 32;
        memcpy(read_packet + 3, input.request, 8);
        memcpy(main_read, read_packet, sizeof(read_packet));
        duplicate = nd_hook(&read, 0);
        CHECK(first == -1 && duplicate == -1 && !nd.attempt);
        CHECK(nd.failed == BAD_READ && nd.frozen);
        return 0;
    }
    if (mode == 'O' || mode == 'Q' || mode == 'f' || mode == 'q') {
        int bound = mode == 'Q' || mode == 'q';
        ioctl foreign = {ND_READ, other + 4, 32, bound ? output : ordinary_output, 32};
        if (mode == 'f' || mode == 'q') {
            foreign.inbuf = other + 8;
            memcpy(foreign.inbuf, read_packet, 32); /* Aligned and byte-identical to the real read. */
            nd_input_provision.read.base = (u32)other; /* Cannot redirect the latched binding. */
            nd_input_provision.read.end = (u32)other + sizeof(other);
        }
        main_other[0] = 0x11;
        ((u8 *)other)[0] = 0xa5; /* Dirty byte outside the input, on its first cache line. */
        CHECK(protect_foreign_page(0) == 0);
        s32 status = nd_hook(&foreign, 0);
        CHECK(protect_foreign_page(3) == 0);
        CHECK(sync_calls == 1 && ((u8 *)other)[0] == 0xa5 && !nd.attempt);
        if (bound) {
            CHECK(status == -1 && nd.failed == BAD_READ && nd.frozen);
            CHECK(nd_hook(&read, 0) == -1 && sync_calls == 1 && !nd.attempt);
            return 0;
        }
        CHECK(status == 0 && !nd.failed && !read_claim);
        memcpy(main_read, read_packet, sizeof(read_packet)); /* Subsequent intended read succeeds. */
    }
    if (mode == 'e' || mode == 'l' || mode == 'r') {
        ioctl malformed = read;
        malformed.iobuf = ordinary_output;
        if (mode == 'e') malformed.inbuf = read_packet + 20; /* Last 16 bytes, needs 32. */
        if (mode == 'l') malformed.inlen = ~0U;
        if (mode == 'r') malformed.inbuf = (u32 *)&input; /* Arm allocation cannot supply a read. */
        CHECK(nd_hook(&malformed, 0) == -1 && nd.failed == BAD_READ && nd.frozen);
        CHECK(nd_hook(&read, 0) == -1 && !nd.attempt && sync_calls == 1);
        return 0;
    }
    if (mode == 'c' || mode == 'h') {
        memcpy(main_read, read_packet, sizeof(read_packet));
        if (mode == 'c') {
            main_read[12] ^= 1; /* Matching stale cache, wrong fresh tag. */
            CHECK(nd_hook(&read, 0) == -1 && nd.failed == BAD_READ && nd.frozen);
            main_read[12] ^= 1;
            CHECK(nd_hook(&read, 0) == -1 && !nd.attempt);
            return 0;
        }
        read_packet[3] ^= 1; /* Fresh memory must win before a valid admission. */
    }
    if (mode == 'A' || mode == 'G') {
        ioctl malformed = {ND_ARM, read_packet, 96, output, 32};
        if (mode == 'G') malformed.iobuf = other; /* Owned input identity alone. */
        s32 first = nd_hook(&malformed, 0);
        s32 second = nd_hook(&read, 0);
        CHECK(first == -1 && second == -1 && !nd.attempt);
        CHECK(nd.failed == BAD_READ && nd.frozen);
        return 0;
    }
    if (mode == 'a') {
        ++input.port; /* Same arm, fd and output addresses, different owned bytes. */
        CHECK(nd_hook(&arm, 0) == -1 && nd.failed == BAD_READ && nd.frozen);
        --input.port;
        CHECK(nd_hook(&arm, 0) == -1 && nd_hook(&read, 0) == -1 && !nd.attempt);
        return 0;
    }
    if (mode == 'b') {
        read.inbuf = read_packet + 16; /* Last whole line ends exactly at the exclusive limit. */
        memcpy(read.inbuf, read_packet, 32);
    }
    if (mode == 'D') {
        CHECK(nd_hook(&arm, 0) == -1 && !nd.failed && !nd.frozen);
        ioctl ordinary = {0x71, other, 32, other, 32};
        CHECK(nd_hook(&ordinary, 1) == 0 && !nd.attempt);
    }
    if (mode == 'B' || mode == 'J') delivered_at = six+cleanup_ticks-1;
    if (mode == 'E') delivered_at = six+cleanup_ticks;
    if (mode == 'L') delivered_at = six+cleanup_ticks+1;
    if (mode == 'W') delivered_at = six*2;
    s32 rc = nd_hook(&read, 0);
    if (delivered_at) {
        CHECK(rc == -1 && nd.failed == DEADLINE && !active);
        for (i = 0; i < nd.seq; ++i)
            if (nd_trace[i].event == PHASE && nd_trace[i].phase == CLEANUP) break;
        CHECK(i < nd.seq && nd_trace[i].a == six);
        if (mode == 'B') CHECK(close_order == 12 && cleanup_delay == 1 && !queue_live && !nd.pinned);
        else if (mode == 'J') CHECK(close_order == 1 && cleanup_delay == 1 && queue_live && nd.pinned);
        else CHECK(!close_order && !cleanup_delay && nd.pinned && queue_live);
    } else if (mode == 'F') {
        CHECK(rc == -1 && nd.failed == RM_ERROR && !active && !nd.pinned && !queue_live);
        CHECK(!socket_closes && so_closes == 1 && bindings[SOCKET].state == 4);
    } else if (mode == 'M' || mode == 'T' || mode == 'C' || mode == 'Y') {
        CHECK(rc == -1 && nd.pinned && active && queue_live && !close_order);
        CHECK(nd.failed == (mode == 'M' ? RM_ERROR : mode == 'T' ? SUBMIT_ERROR :
                            mode == 'C' ? MULTIPLE_WORDS : DEADLINE));
    } else if (mode == 'K') {
        unsigned cancelled = 0, issued = 0;
        CHECK(rc == -1 && nd.failed == DEADLINE && !nd.pinned && !active && !queue_live);
        for (i = 0; i < nd.seq; ++i) {
            struct nd_record *r = &nd_trace[i];
            if (r->operation != CLOSE_KD) continue;
            if (r->event == NOT_ISSUED) {
                CHECK(r->phase == BRINGUP);
                cancelled = r->attempt + 1;
            } else if (r->event == SUBMITTED) {
                CHECK(r->phase == CLEANUP && r->attempt == cancelled && !issued);
                CHECK(r->b == (u32)&nd_completions[cancelled-1]);
                issued = r->attempt;
            }
        }
        CHECK(issued && bindings[KD].close_attempt == issued && bindings[KD].state == RELEASED);
    } else if (mode == 'U' || mode == 'N' || mode == 'u' || mode == 't') {
        unsigned op = mode == 'N' ? OPEN_NCD : CLOSE_SOCKET;
        unsigned owner = mode == 'N' ? NCD : SOCKET;
        unsigned intents = 0, submissions = 0, withheld = 0, previous = 0;
        if (mode == 'u') CHECK(rc == 1 && close_order == 12 && !nd.failed);
        else if (mode != 'N') {
            CHECK(rc == -1 && !socket_closes && !so_closes && nd.pinned && verified == 0x31313131);
            CHECK(bindings[SOCKET].state == KNOWN && !bindings[SOCKET].close_attempt && queue_live);
        } else CHECK(rc == -1 && !nd.attempt && bindings[NCD].state == NONE && !bindings[NCD].acquired);
        for (i = 0; i < nd.seq; ++i) {
            struct nd_record *r = &nd_trace[i];
            if (r->operation != op) continue;
            if (r->event == INTENT) {
                ++intents;
                previous = r->attempt;
                CHECK(r->a == (u32)&nd_completions[previous] && (r->b >> 16) == previous+1);
                CHECK(((r->b >> 8) & 255) == owner);
            } else if (r->event == SUBMITTED) {
                ++submissions;
                CHECK(r->attempt == previous+1);
            } else if (r->event == NOT_ISSUED) {
                ++withheld;
                CHECK(r->attempt == previous && r->a == (u32)&nd_completions[previous]);
            }
        }
        CHECK(intents == 1 && submissions == (mode == 'u') && withheld == (mode != 'u'));
        if (withheld) CHECK(nd.failed == DEADLINE && nd.attempt == previous && !active);
    } else if (mode == 'Z') {
        CHECK(rc == -1 && nd.failed == DEADLINE && nd.pinned && !active && queue_live);
        CHECK(verified == 0x31313131 && !close_order && !cleanup_delay);
    } else if (mode == 'V') {
        CHECK(rc == -1 && nd.pinned && verified == 0x31313131 && close_order == 1);
    } else {
        CHECK(rc == 1 && !queue_live && !nd.pinned && close_order == 12);
        CHECK(handoffs == 28 && !stale_copy && verified == 0x31313131);
    }
    i = nd.seq;
    CHECK(nd_hook(&read, 0) == -1 && nd.frozen && nd.seq == i);
    CHECK(nd_hook(&arm, 0) == -1 && nd.seq == i);
    return 0;
}

/* Read argv[1] and exit via the native Linux i386 ABI without a multilib libc. */
__asm__(".globl _start\n_start:\n mov 8(%esp),%eax\n movzbl (%eax),%eax\n"
        " push %eax\n call run\n mov %eax,%ebx\n mov $1,%eax\n int $0x80");
