// SPDX-License-Identifier: GPL-3.0-only
/* Host Linux i386 driver. Each process starts with a new one-shot instance. */
#include <stdarg.h>
#include "adapter.h"

static const char *scenario;
static u8 arm[192] LINE, read_area[96] LINE, output[32] LINE, ordinary[32] LINE;
static u8 foreign[4096] __attribute__((aligned(4096)));
static u8 shared_read[96];
static u32 now, words[12], queued, consumed, traps, blocks, ioctls, closes, syncs, last_sync;
static u32 token, timer_delay, snapshots, expected_commit, variant, mutation;
static unsigned service_fd(void) { return variant ? 23 : 0; }
static u8 reader_copy[48][32];
static u32 reader_count;
static u32 seen_loan, seen_payload, seen_check, probe_receives;

static int same(const char *s)
{
    const char *p = scenario;
    while (*p && *p == *s) { ++p; ++s; }
    return *s == *p;
}
static void exit_code(int code)
{
    __asm__ volatile("int $0x80" : : "a"(1), "b"(code));
    __builtin_unreachable();
}
static void failed(const char *what, unsigned size)
{
    __asm__ volatile("int $0x80" : : "a"(4), "b"(2), "c"(what), "d"(size) : "memory");
    exit_code(1);
}
#define CHECK(x) do { if (!(x)) failed(#x, sizeof(#x)-1); } while (0)

void *memset(void *dest, int c, size_t size)
{
    u8 *d = dest;
    while (size--) *d++ = c;
    return dest;
}
void *memcpy(void *dest, const void *src, size_t size)
{
    u8 *d = dest; const u8 *s = src;
    while (size--) *d++ = *s++;
    return dest;
}
int memcmp(const void *a, const void *b, size_t size)
{
    const u8 *x = a, *y = b;
    if (snapshots && size == 64 && nd.active == CONTROL_SERVICE && same("reject-work"))
        now = 53; /* Time spent checking the private reply prefix. */
    while (size--) { if (*x != *y) return *x - *y; ++x; ++y; }
    return 0;
}
u32 nd_take(volatile u32 *once) { return __sync_lock_test_and_set(once, 1); }
static void protect(void)
{
    int rc;
    __asm__ volatile("int $0x80" : "=a"(rc) : "0"(125), "b"(foreign), "c"(4096), "d"(0) : "memory");
    CHECK(rc == 0);
}
static unsigned event(unsigned i) { return (nd_trace[i][4] << 8) | nd_trace[i][5]; }
static unsigned find(unsigned code)
{
    unsigned i;
    for (i = 0; i < nd.seq; ++i) if (event(i) == code) return i + 1;
    return 0;
}
static u32 payload(unsigned seq, unsigned index)
{
    CHECK(seq && seq <= nd.seq && index < 3);
    return word(nd_trace[seq-1] + 20 + index*4);
}
static u32 fnv(const u8 *record)
{
    unsigned j;
    u32 hash = 2166136261U;
    for (j = 0; j < 32; ++j) hash = (hash ^ record[j]) * 16777619U;
    return hash;
}
static int capture(void)
{
    unsigned i, count = word(nd_commit + 4);
    if (count > 48 || count < reader_count || count != expected_commit
        || word(nd_commit) != nd.p.dip || memcmp(nd_commit + 8, nd.arm + 48, 8)) return 0;
    for (i = 16; i < 32; ++i) if (nd_commit[i]) return 0;
    for (i = 0; i < count; ++i) {
        if (word(nd_trace[i]+12) && word(nd_trace[i]+12) != nd.p.claim) return 0;
        if (word(nd_trace[i]) != i+1 || word(nd_trace[i] + 8) != nd.p.dip
            || fnv(nd_trace[i]) != word(nd_checks[i])) return 0;
    }
    if (memcmp(reader_copy, nd_trace, reader_count * 32)) return 0;
    memcpy(reader_copy, nd_trace, count * 32);
    reader_count = count;
    return 1;
}
static void waiting(void)
{
    __asm__ volatile("int $0x80" : : "a"(4), "b"(1), "c"("waiting\n"), "d"(8) : "memory");
}
static void block_forever(void)
{
    char ch;
    waiting();
    __asm__ volatile("int $0x80" : : "a"(3), "b"(0), "c"(&ch), "d"(1) : "memory");
    exit_code(2);
}
void os_sync_before_read(void *p, s32 n)
{
    if (p == nd_reply && (same("causal") || same("causal-loss") || same("timer-causal")
        || same("delayed-validation") || same("missing-receipt-clock"))) now += 200;
    if (p == nd_reply && same("timer-separated")) now = 247;
    if (p == nd_reply && (same("causal-loss") || same("late-loss") || same("mixed-loss"))) put(nd_reader,0);
    if (p == (void *)&nd_provision && find(DISPOSITION)) {
        if (same("handback-reload")) { ++nd_provision.ios; ++nd_provision.dip; ++nd_provision.fd_epoch; }
        if (same("handback-time") || same("handback-expired")) now = nd.end;
        if (same("handback-time") || same("handback-lease")) put(nd_reader,0);
    }
    ++syncs;
    CHECK((u32)p < (u32)foreign || (u32)p >= (u32)foreign + sizeof(foreign));
    if (p == read_area && same("split")) {
        last_sync = n;
        memcpy(p, shared_read, n);
    }
    if (p == nd_reader && snapshots && (same("reject-delay") || same("reject-equality") || same("reject-loss"))) {
        static unsigned acquisitions;
        /* Two reads qualify the pre-validation sample. Change the world in
         * the first lease acquisition after the malformed frame is observed. */
        if (++acquisitions == 3) {
            if (same("reject-loss")) put(nd_reader, 0);
            else now = same("reject-equality") ? nd.end : 1047;
        }
    }
    if (p == nd_reader && snapshots && same("dip-clock-loss")) put(nd_reader, 0);
    if (p == nd_reply) {
        CHECK(nd.active == CONTROL_SERVICE && n == 192);
        ++snapshots;
    }
}
void os_sync_after_write(void *p, s32 n)
{
    if (nd.seq < 48 && p == nd_trace[nd.seq]) {
        CHECK(n == 32 && expected_commit == nd.seq);
        seen_payload = nd.seq + 1;
    } else if (nd.seq < 48 && p == nd_checks[nd.seq]) {
        CHECK(n == 4 && seen_payload == nd.seq + 1);
        seen_check = seen_payload;
    } else if (p == nd_commit) {
        CHECK(n == 32 && seen_check == nd.seq && seen_payload == nd.seq);
        expected_commit = nd.seq;
        CHECK(capture());
        if (event(nd.seq-1) == TERMINAL && (same("fd-reuse") || same("handback-reload"))) {
            CHECK(!find(OUTPUT) && !memcmp(output,arm+48,8) && !memcmp(output+8,arm+4,20));
            CHECK(word(output+28) == (u32)output && payload(nd.seq,2) == 1 && closes == 1);
            if (same("fd-reuse")) CHECK(nd.owner == CLOSING && nd.pinned && nd.active == CLOSE_SERVICE);
            waiting();
        }
        if (event(nd.seq-1) == SETUP && same("capacity")) {
            /* Fault injection consumes the first slot needed for the open
             * reserve. No service trap may run against this shortened budget. */
            while (nd.seq < 13) nd_emit(ARM_BIND, 0, 0, 0);
        }
        if (event(nd.seq-1) == VERDICT) { CHECK(nd.active == CONTROL_SERVICE); ++seen_loan; }
        if (event(nd.seq-1) == INTENT && same("global-close") && nd.op == CLOSE_SERVICE)
            nd_provision.release = 0;
        if (event(nd.seq-1) == INTENT && same("withdrawn-control") && nd.op == CONTROL_SERVICE)
            nd_provision.ready = 0;
        if (event(nd.seq-1) == INTENT && same("preissue") && nd.op == CONTROL_SERVICE) now = nd.end;
        if (event(nd.seq-1) == INTENT && same("close-expired") && nd.op == CLOSE_SERVICE) now = nd.end;
        if (event(nd.seq-1) == RESOURCE && same("skipped") && nd.op == OPEN_SERVICE)
            nd_provision.ready = 0;
    }
}
s32 os_get_thread_id(void) { return variant ? 17 : 7; }
s32 os_timer_now(s32 id) { CHECK(id == 0); return now; }
s32 os_create_timer(s32 delay, s32 repeat, s32 q, s32 msg)
{
    CHECK(repeat == 0 && q == 9 && delay > 0 && (u32)msg == nd.p.wake_token);
    timer_delay = delay; token = msg; return same("no-timer") ? -8 : 3;
}
s32 os_stop_timer(s32 id)
{
    CHECK(id == 3);
    if (same("late-duplicate")) { consumed = 0; queued = 1; words[0] = (u32)&nd_completions[2]; }
    return same("stop-failed") ? -5 : 0;
}
s32 os_destroy_timer(s32 id) { CHECK(id == 3); return 0; }
s32 os_message_queue_create(void *p, u32 cap)
{
    CHECK(!((u32)p & 31) && cap == 8);
    if (same("setup-tick")) { now += 1000; return -3; }
    if (same("zero-tick")) return -3;
    return same("no-queue") ? -3 : 9;
}
s32 os_message_queue_destroy(s32 id) { CHECK(id == 9 && !nd.active && !nd.timer_live); return 0; }
s32 os_message_queue_receive(s32 q, u32 *value, u32 mode)
{
    CHECK(q == 9 && mode <= 1);
    if (!mode) {
        ++blocks;
        if (same("missing-wake") && nd.active == CONTROL_SERVICE) {
            CHECK(nd.owner == HELD && !nd.decision && capture());
            block_forever();
        }
        CHECK(nd.active && !nd.timer_seen);
        if (nd.active == CONTROL_SERVICE && (same("timer-first") || same("timer-last"))) now = nd.end;
        if (same("receive-error") || (same("lost-open") && nd.active == OPEN_SERVICE)) return -7;
    }
    if (consumed == queued) return -7;
    if (same("saturated") && nd.active == CONTROL_SERVICE) ++probe_receives;
    if (nd.active == CONTROL_SERVICE && (same("missing-receipt-clock") || same("unknown-deadline")))
        put(nd_reader,0);
    if (nd.active == CONTROL_SERVICE && same("timer-separated") && consumed == 1) now = 147;
    *value = words[consumed++];
    return 0;
}

static void provision(void)
{
    struct provision p;
    unsigned i;
    u32 start = same("wrap") ? 0xffffffd0 : 0;
    memset(&p, 0, sizeof(p));
#define EXT(buf) (struct extent){(u32)(buf), (u32)(buf) + sizeof(buf)}
    p.arm = EXT(arm); p.read = EXT(read_area); p.output = EXT(output);
    if (!same("relocated-arm")) p.arm.end = p.arm.base + 96;
    p.request = EXT(nd_request); p.reply = EXT(nd_reply);
    p.ios = 90; p.ios_build = 91; p.dip = 7; p.dip_build = 0x24abcd;
    p.slot = 249; p.gx = 22; p.gx_build = 29; p.claim = 63; p.epoch = 510; p.lease = 311;
    memcpy(p.expected.path, variant ? "alternate" : "fixture", variant ? 10 : 8);
    p.expected.selector = variant ? 205 : 107;
    p.expected.instance = 601; p.expected.build = 702 + variant;
    p.expected.worker_tid = 37; p.expected.worker_pid = 43; p.expected.session = 3 + variant;
    p.expected.opener = os_get_thread_id();
    p.registered = p.expected;
    p.ownership = p.registration = p.visible = p.ready = 1;
    p.single_delivery = p.retirement = p.release = p.timer_retirement = 1;
    p.fd_epoch = 429; p.wake_token = 377 + variant;
    p.stale_token = 100; p.stale_epoch = 509; p.stale_lease = 310;
    put(arm, 1); put(arm+4, p.dip); put(arm+8, p.slot); put(arm+12, p.dip_build);
    put(arm+16, p.gx_build); put(arm+20, 40); put(arm+24, ND_READ); put(arm+28, 32);
    put(arm+32, 0x12345678); put(arm+36, 0xc0a80101); put(arm+40, 0xc0a80103); put(arm+44, 33440);
    for (i = 0; i < 24; ++i) arm[48+i] = 99-i;
    put(read_area, ND_READ << 24); put(read_area+4, 32);
    memcpy(read_area+8, arm+32, 4); memcpy(read_area+12, arm+48, 8);
    put(nd_reader, 1); put(nd_reader+4, p.lease); put(nd_reader+8, p.ios); put(nd_reader+12, p.epoch);
    memcpy(nd_reader+16, arm+48, 8); put(nd_reader+24, start); put(nd_reader+28, start+CUTOFF);
    now = start + (same("clipped") ? FIVE*2 : 40);
    if (same("zero-tick")) now = 0;
    if (same("clipped-deadline") || same("ready-at-cutoff")) now = start+CUTOFF-20;
    if (same("zero-identity")) {
        u32 *ids[] = {&p.claim,&p.ios,&p.ios_build,&p.dip,&p.dip_build,&p.slot,&p.gx,
                     &p.gx_build,&p.epoch,&p.lease,&p.fd_epoch,&p.expected.session,
                     &p.expected.build,&p.expected.instance};
        CHECK(mutation < sizeof(ids)/sizeof(*ids)); *ids[mutation] = 0;
        p.registered = p.expected;
    }
    if (same("wrong-opener")) p.registered.opener = ++p.expected.opener;
    if (same("stale-session")) ++p.registered.session;
    if (same("stale-build")) ++p.registered.build;
    if (same("bad-path")) memset(p.expected.path, 'x', 32), p.registered = p.expected;
    if (same("aliased-mailbox")) p.reply = p.request;
    if (same("bad-output")) p.output = p.read;
    if (same("unowned")) p.ownership = 0;
    if (same("stale-lease")) put(nd_reader+4, 12);
    if (same("bad-arm")) arm[95] = 1;
    if (same("token-collision")) p.wake_token = (u32)&nd_completions[2];
    if (same("stale-token-alias")) p.wake_token = p.stale_token;
    if (same("no-retirement")) p.retirement = 0;
    if (same("no-release")) p.release = 0;
    for (i = 0; i < 3; ++i) {
        struct effects e = {p.ios, p.expected.session, p.claim, i ? 1 : 0, p.fd_epoch,
                            (u32)&nd_completions[i], RETIRES_ONCE, 0};
        if (i == 2 && !same("release-unconfirmed")) e.flags |= RELEASES_ORIGINAL;
        if (i == 1 && same("proven-reject")) { e.flags |= PRE_ADMISSION_CODE; e.rejection_code = -24; }
        nd_effects[i] = e;
    }
    if (same("postfacts-open")) nd_effects[0].flags = 0;
    if (same("postfacts-ioctl")) nd_effects[1].flags = 0;
    if (same("postfacts-close")) nd_effects[2].flags = 0;
    if (same("initial-clock")) put(nd_reader,0);
    nd_provision = p;
}

static void verify_request(const u8 *in)
{
    u8 expected[160];
    unsigned i;
    u32 prefix[] = {0x10001,160,90,91,7,0x24abcd,601,702+variant,63,3+variant,249,29};
    memset(expected, 0, sizeof(expected));
    for (i=0; i<12; ++i) put(expected+4*i, prefix[i]);
    memcpy(expected+48, arm+48, 8); put(expected+56, 510); put(expected+60, 22);
    put(expected+64, os_get_thread_id()); put(expected+68, 40); put(expected+72, ND_READ);
    put(expected+76, 32); put(expected+80, 0x12345678); put(expected+84, 32);
    put(expected+88, 0xc0a80101); put(expected+92, 0xc0a80103); put(expected+96, 33440U << 16);
    memcpy(expected+100, arm+56, 16); put(expected+116, word(nd_reader+24));
    put(expected+120, word(nd_reader+28)); put(expected+124, nd.start);
    put(expected+128, nd.end); put(expected+132, 311);
    CHECK(!memcmp(in, expected, 160));
}

static void reply(u8 *b)
{
    unsigned i;
    u32 x = nd.issue + 4;
    memcpy(b, nd_request, 64); put(b+4, 192);
    put(b+64, 37); put(b+68, 43); put(b+72, 255);
    for (i=0; i<4; ++i) put(b+76+4*i, nd.issue+1+i);
    put(b+92, x+FIVE); put(b+96, x+1); put(b+100, x+1); put(b+104, x+2);
    put(b+120,28); memcpy(b+124,arm+48,24); put(b+148,0x123456ab);
    put(b+152,411); put(b+156,1); put(b+160,nd.end); put(b+164,311);
    memcpy(b+168,nd_request+64,8); put(b+184,255);
    now = x+3;
    if (same("late-dip")) now = x+FIVE;
    if (same("late-outer")) now = nd.end;
    if (same("cleanup-failure") || same("clock-after") || same("clock-at-latch")) {
        put(b+72,511); put(b+184,511); put(b+108,5); put(b+112,x+2);
        put(b+116,1); put(b+156,2); put(b+180,5);
        if (same("clock-after")) { put(b+184,191); put(b+188,2); }
        if (same("clock-at-latch")) {
            put(b+108,6); put(b+180,4); put(b+188,2); put(b+184,31);
        }
    }
    if (same("eof") || same("absent-raw") || same("clock-before")) {
        put(b+72,479); put(b+184,479); put(b+96,0); put(b+108,2); put(b+112,x+1);
        put(b+116,1); put(b+120,0); memset(b+124,0,28); put(b+180,4);
        put(b+188,same("eof"));
        if (same("clock-before")) { put(b+108,6); put(b+184,7); put(b+188,2); }
    }

    if (same("connect")) {
        put(b+72,455); put(b+184,455); /* bring-up, ready, connected, cleanup, final, failure */
        put(b+88,0); put(b+92,0); put(b+96,0); put(b+108,2); put(b+112,x+1);
        put(b+116,1); put(b+120,0); memset(b+124,0,28);
        put(b+176,-111); put(b+180,3); put(b+188,1);
    }
    if (same("unproved-deadline")) {
        put(b+72,455); put(b+184,455); put(b+88,0); put(b+92,0); put(b+96,0);
        put(b+108,4); put(b+112,x+1); put(b+116,1); put(b+120,0); memset(b+124,0,28);
        put(b+180,4); put(b+188,2);
    }
    if (same("phase-after-cleanup")) {
        put(b+72,479); put(b+184,479); put(b+96,0); put(b+108,6); put(b+112,x+2);
        put(b+116,1); put(b+180,4); put(b+188,2);
    }
    if (same("causal") || same("causal-loss")) put(b+104,now+100);
    if (same("bad-length")) put(b+120,27);
    if (same("late-loss")) now = nd.end;

    if (same("ended-bringup") || same("ended-connect") || same("ended-unobserved")
        || same("expire-bringup") || same("expire-connect") || same("ready-at-cutoff")) {
        unsigned connection = same("ended-connect") || same("expire-connect");
        unsigned mask = connection ? 455 : 451;
        now = connection ? word(b+80)+FIVE : word(b+76)+THIRTY;
        if (same("ready-at-cutoff")) { now = nd.end; put(b+80,now); }
        if (!connection) put(b+84,0);
        if (same("expire-bringup")) put(b+80,now);
        if (same("expire-connect")) put(b+84,now);
        put(b+88,0); put(b+92,0); put(b+96,0); put(b+100,now); put(b+104,now);
        put(b+108,4); put(b+112,now); put(b+116,1); put(b+120,0); memset(b+124,0,28);
        put(b+180,connection ? 3 : 2);
        if (same("ended-unobserved")) {
            mask &= ~320U; put(b+100,0); put(b+112,0); put(b+188,2);
            now = nd.end; put(b+104,now);
        }
        put(b+72,mask); put(b+184,mask);
    }
    if (same("exchange-at-cutoff") || same("exchange-before-cutoff")) {
        u32 start = same("exchange-at-cutoff") ? nd.end : nd.end-1;
        put(b+88,start); put(b+92,start+FIVE); put(b+96,0); put(b+100,0);
        now = nd.end+4; put(b+104,now); put(b+108,5); put(b+112,now-1);
        put(b+72,415); put(b+184,415); put(b+116,1); put(b+156,2); put(b+180,5); put(b+188,2);
    }
    if (same("reject-delay") || same("reject-equality") || same("reject-loss") || same("reject-work")) put(b+120,27);
    if (same("partial-readiness")) {
        put(b+72, 477); put(b+184, 477); put(b+80, 0); put(b+96, 0);
        put(b+84, nd.issue+THIRTY+FIVE); put(b+88, word(b+84)+1); put(b+92, word(b+88)+FIVE);
        now = word(b+88)+1; put(b+100,now); put(b+104,now); put(b+112,now); put(b+108,6);
        put(b+116,1); put(b+120,0); memset(b+124,0,28); put(b+180,4); put(b+188,2);
    }
    if (same("timer-causal")) put(b+104, now+100);
    if (same("timer-separated")) put(b+104,100);
    if (same("missing-receipt-clock")) put(b+104, now+100);
    if (same("mixed-loss")) now = x+FIVE;
    if (same("partial-deadline") || same("clipped-deadline") || same("missing-failure") || same("unknown-deadline")) {
        u32 end = same("partial-deadline") ? x+FIVE : same("clipped-deadline") ? nd.end : x+1;
        put(b+72, same("missing-failure") ? 199 : 455);
        put(b+184, word(b+72)); put(b+88,0); put(b+92,0); put(b+96,0);
        put(b+100,end); put(b+104,end+1); put(b+108,4); put(b+112,same("missing-failure") ? 0 : end);
        put(b+116,1); put(b+120,0); memset(b+124,0,28); put(b+180,4); put(b+188,2);
        now = end+2;
        if (same("unknown-deadline")) put(b+184,7);
    }
    if (same("modified-request")) { nd_request[33] ^= 1; b[33] ^= 1; }
    if (same("zero-id")) put(b+148,0);
    if (same("zero-sequence")) put(b+152,0);
    if (same("unknown-flags")) put(b+188,4);
    if (same("valid-absent")) put(b+72,253);
    if (same("nonzero-absent")) put(b+112,1);
    if (same("false-deadline")) put(b+92,x+FIVE+1);
    if (same("out-of-order")) put(b+80,nd.issue);
    if (same("late-readiness")) {
        put(b+80,nd.issue+1+THIRTY);
        for (i=84; i<=104; i+=4) put(b+i,word(b+i)+THIRTY);
        now += THIRTY;
    }
    if (same("late-cleanup")) { put(b+104,x+1+FIVE); now = x+2+FIVE; }
    if (same("unflagged-raw")) put(b+176,5);
    if (same("false-absence")) {
        put(b+72,479); put(b+184,479); put(b+96,0); put(b+108,2); put(b+112,x+1);
        put(b+116,1); put(b+120,0); put(b+180,4);
    }
    if (same("malformed")) b[63] ^= 1;
    if (same("mutate")) b[mutation] ^= 0x80;
}

static void completion(ipcmessage *m, s32 result)
{
    CHECK(nd.active && nd.issued == ++traps && m == nd_completions + nd.op-1);
    CHECK(find(ENTRY) && find(SESSION) && event(nd.seq-1) == INTENT);
    m->command = 8; m->result = result;
    queued = consumed = 0;
    words[queued++] = (u32)m;
}

s32 os_open_async(const char *path, s32 mode, void *q, void *cb)
{
    CHECK(!mode && (u32)q == 9 && path == nd_path && !memcmp(path, nd.p.expected.path, 32));
    if (same("postfacts-open")) nd_effects[0].flags = RETIRES_ONCE;
    completion(cb, same("negative-open") ? -19 : (s32)service_fd());
    if (same("lost-open") || same("ambiguous-open")) queued = 0;
    return same("ambiguous-open") || same("ambiguous-matched-open") ? -4 : 0;
}

s32 os_ioctl_async(s32 fd, s32 cmd, void *in, s32 size, void *out, s32 length, ...)
{
    va_list ap; ipcmessage *m;
    va_start(ap, length); CHECK(va_arg(ap, s32) == 9); m = va_arg(ap, ipcmessage *); va_end(ap);
    CHECK((u32)fd == service_fd() && (u32)cmd == nd.p.expected.selector && size == 160 && length == 192);
    CHECK(in == nd_request && out == nd_reply && nd.acquisition_ref);
    verify_request(in);
    ++ioctls;
    if (same("postfacts-ioctl")) nd_effects[1].flags = RETIRES_ONCE;
    if (same("revoke-ioctl")) nd_effects[1].flags = 0;
    completion(m, same("undefined") ? -22 : 0);
    reply(out);
    if (same("timer-first") || same("timer-causal") || same("timer-separated")) { words[0] = token; words[queued++] = (u32)m; }
    if (same("timer-last")) words[queued++] = token;
    if (same("lost-ioctl") || same("early-timer")) { queued = 1; words[0] = token; }
    if (same("lost-ioctl")) now = nd.end;
    if (same("conflict-first")) { words[0] = 1; words[queued++] = (u32)m; }
    if (same("conflict-last")) words[queued++] = 1;
    if (same("duplicate")) words[queued++] = (u32)m;
    if (same("old-word")) words[queued++] = (u32)nd_completions;
    if (same("stale-wake")) { words[0] = nd.p.stale_token; words[queued++] = (u32)m; }
    if (same("double-timer")) { words[queued++] = token; words[queued++] = token; }
    if (same("saturated")) while (queued < 10) words[queued++] = (u32)m;
    if (same("bad-command")) m->command = 7;
    if (same("proven-reject")) {
        queued = 0;
        return -24;
    }
    return 0;
}
s32 os_close_async(s32 fd, void *q, void *cb)
{
    CHECK((u32)fd == service_fd() && (u32)q == 9 && nd.owner == CLOSING && nd.acquisition_ref);
    CHECK(nd.decision && nd.active == CLOSE_SERVICE && capture());
    CHECK(event(nd.decision-1) == VERDICT || event(nd.decision-1) == SHORT_VERDICT);
    CHECK(event(nd.seq-1) == INTENT && payload(nd.seq,2) == nd.acquisition_ref);
    ++closes;
    if (same("blocked-close")) {
        CHECK(seen_loan == 1 && !find(TERMINAL) && payload(nd.decision,2) == 5);
        block_forever();
    }
    completion(cb, same("positive-close") ? 1 : same("negative-close") ? -7 : 0);
    if (same("postfacts-close")) nd_effects[2].flags = RETIRES_ONCE | RELEASES_ORIGINAL;
    if (same("global-close")) nd_provision.release = 1;
    if (same("fd-reuse")) ++nd_provision.fd_epoch;
    if (same("late-close")) now = nd.end;
    return 0;
}

int run(const char *name, const char *arg)
{
    ioctl a = {ND_ARM,(u32 *)arm,96,(u32 *)output,32};
    ioctl r = {ND_READ,(u32 *)read_area,32,(u32 *)output,32};
    ioctl other = {ND_READ,(u32 *)foreign,32,(u32 *)ordinary,32};
    unsigned seq, s, group, snap, i;
    s32 rc;
    scenario = name;
    variant = same("variant");
    if (same("mutate") || same("zero-identity")) while (*arg) mutation = mutation*10 + *arg++ - '0';
    provision();
    protect();
    CHECK(nd_hook(&other,40) == 0 && !syncs);
    rc = nd_hook(&a,40);
    if (same("bad-arm") || same("bad-output") || same("unowned") || same("zero-identity")
        || same("stale-session") || same("stale-build")) {
        CHECK(!find(ENTRY) && !find(ARM_BIND) && !find(ARM_RECEIPT) && !word(output));
        CHECK(!(payload(nd.failure_seq,0) & (6U<<16)) && !payload(nd.failure_seq,2));
        CHECK(rc == -1 && nd.frozen && !traps && find(ARM_REJECT));
        CHECK(nd_hook(&a,40) == -1);
        return 0;
    }
    CHECK(rc == 1 && !memcmp(output,arm+48,8) && !memcmp(output+8,arm+4,20)
          && word(output+28) == (u32)output);
    seq = nd.seq;
    CHECK(nd_hook(&a,40) == -1 && nd.seq == seq);
    s = syncs;
    CHECK(nd_hook(&other,40) == 0 && syncs == s);
    if (same("foreign")) {
        other.iobuf = (u32 *)output;
        CHECK(nd_hook(&other,40) == -1 && syncs == s && nd.frozen && !traps);
        CHECK(nd_hook(&r,40) == -1);
        return 0;
    }
    if (same("relocated-arm")) {
        memcpy(arm+96,arm,96); a.inbuf = (u32 *)(arm+96);
        CHECK(nd_hook(&a,40) == -1 && nd.frozen && !traps && nd.failure == BAD_READ);
        CHECK(nd_hook(&r,40) == -1 && nd.arm_input == (u32)arm);
        return 0;
    }
    if (same("changed-replay")) {
        ++arm[56];
        CHECK(nd_hook(&a,40) == -1 && nd.frozen && !traps);
        CHECK(nd_hook(&r,40) == -1);
        return 0;
    }
    if (same("split")) {
        memcpy(shared_read+16, read_area, 32);
        r.inbuf = (u32 *)(read_area+16);
        CHECK(nd_hook(&r,40) == -1 && last_sync == 64 && nd.frozen && !traps);
        CHECK(!memcmp(read_area, shared_read, 64));
        return 0;
    }
    if (same("short-reservation")) r.inbuf = (u32 *)(read_area+80);
    if (same("changed-registration")) ++nd_provision.registered.session;
    if (same("half-gap")) now += HALF;
    if (same("bad-read")) read_area[31] = 1;
    if (same("bad-extent")) ++r.inlen;
    rc = nd_hook(&r,40);
    CHECK(nd.frozen && nd.seq <= 48 && capture());
    seq = nd.seq;
    CHECK(nd_hook(&r,40) == -1 && nd.seq == seq && nd_hook(&a,40) == -1);
    if (same("bad-read") || same("bad-extent") || same("short-reservation")) {
        CHECK(rc == -1 && nd.failure == BAD_READ && !traps);
        return 0;
    }
    CHECK(word(output+12) == seq && (s32)word(output+16) == rc && word(output+20) == nd.failure);
    if (same("initial-clock") || same("setup-tick") || same("zero-tick")) {
        CHECK(rc == -1 && !traps && nd.failure == (same("initial-clock") ? CLOCK_FAULT : QUEUE_SETUP));
        CHECK(((payload(nd.failure_seq,0)>>17)&3) == (same("initial-clock") ? 1U : 3U));
        CHECK(payload(nd.failure_seq,2) == (same("setup-tick") ? 1040U : same("zero-tick") ? 0U : 40U));
        return 0;
    }
    if (same("reject-delay") || same("reject-equality") || same("reject-loss") || same("reject-work")) {
        unsigned verdict = payload(find(SHORT_VERDICT),2);
        CHECK(rc == -1 && nd.failure == BAD_FRAME && (payload(nd.failure_seq,0)&255) == BAD_FRAME);
        CHECK(payload(nd.failure_seq,2) == (same("reject-work") ? 53U : 47U));
        CHECK(((payload(nd.failure_seq,0)>>17)&3) == (same("reject-loss") ? 1U : 3U));
        CHECK(find(SHORT_VERDICT) > nd.failure_seq && payload(find(SHORT_VERDICT),1) == nd.failure_seq);
        CHECK(payload(find(NO_FRAME),0) == REJECTED && !nd.worker_failure && !find(FRAME0));
        CHECK((verdict>>6) == BAD_FRAME && ((verdict>>4)&3) ==
              (same("reject-loss") ? INDETERMINATE : same("reject-equality") ? LATE : TIMELY));
        CHECK(now == (same("reject-delay") ? 1047U : same("reject-equality") ? nd.end : same("reject-work") ? 53U : 47U));
        if (same("reject-loss")) CHECK(nd.clock_fault && (payload(find(FIRST_ANOMALY),0)&255) == CLOCK_FAULT);
        return 0;
    }
    if (same("exchange-before-cutoff")) {
        CHECK(rc == -1 && nd.worker_failure && nd.inner == 2 && find(FRAME0) && find(VERDICT));
        return 0;
    }
    if (same("connect") || same("unproved-deadline") || same("phase-after-cleanup")
        || same("causal") || same("causal-loss") || same("bad-length") || same("timer-causal")
        || same("missing-failure") || same("partial-readiness") || same("ended-bringup")
        || same("ended-connect") || same("ended-unobserved") || same("exchange-at-cutoff")) {
        CHECK(rc == -1 && !nd.inner && !nd.worker_failure && !find(FRAME0)
              && payload(find(NO_FRAME),0) == REJECTED);
        if (same("causal") || same("causal-loss") || same("timer-causal"))
            CHECK(nd.ack_valid && nd.ack_bound == 47 && word(nd_reply+104) == 147 && now == 247);
        return 0;
    }
    if (same("partial-deadline") || same("clipped-deadline") || same("unknown-deadline")
        || same("expire-bringup") || same("expire-connect") || same("ready-at-cutoff")) {
        CHECK(rc == -1 && nd.worker_failure && payload(find(NO_FRAME),0) == ABSENT);
        return 0;
    }
    if (same("postfacts-close") || same("postfacts-open") || same("postfacts-ioctl") || same("revoke-ioctl")) {
        CHECK(rc == -1 && nd.failure == UNRETIRED && nd.pinned && nd.active == traps
              && nd.owner == (traps == 3 ? CLOSING : traps == 2 ? HELD : POSSIBLE));
        CHECK(closes == (unsigned)same("postfacts-close") && (traps == 3 || !snapshots));
        return 0;
    }
    if (same("capacity")) {
        CHECK(rc == -1 && !traps && find(CAPACITY) && !find(INTENT) && !nd.active);
        return 0;
    }
    if (same("wrong-opener") || same("stale-session") || same("stale-build")
        || same("bad-path") || same("aliased-mailbox") || same("stale-lease")
        || same("no-timer") || same("no-queue") || same("changed-registration") || same("half-gap")
        || same("token-collision") || same("stale-token-alias")) {
        CHECK(rc == -1 && !traps && !nd.active);
        CHECK(!!nd.pinned == (same("no-timer") || same("no-queue")));
        return 0;
    }
    if (same("negative-open")) {
        CHECK(rc == -1 && traps == 1 && nd.pinned && nd.owner == POSSIBLE && !nd.active && !closes);
        return 0;
    }
    if (same("ambiguous-matched-open")) {
        CHECK(rc == -1 && traps == 2 && !ioctls && closes == 1 && nd.owner == RELEASED);
        CHECK(payload(find(NO_FRAME),0) == SKIPPED && !nd.active);
        return 0;
    }
    if (same("lost-open") || same("ambiguous-open") || same("no-retirement") || same("receive-error")) {
        CHECK(rc == -1 && traps == 1 && nd.pinned && nd.owner == POSSIBLE && nd.active == OPEN_SERVICE);
        return 0;
    }
    if (same("withdrawn-control")) {
        group = find(NO_FRAME);
        CHECK(rc == -1 && payload(group,0) == UNISSUED && !payload(group,2));
        CHECK(event(payload(group,1)-1) == NOT_ISSUED && closes == 1 && traps == 2 && !ioctls);
        CHECK(nd.owner == RELEASED && !word(output+24));
        return 0;
    }
    if (same("preissue") || same("skipped") || same("proven-reject")) {
        group = find(NO_FRAME);
        CHECK(group && find(SHORT_VERDICT) == group+1 && !seen_loan);
        if (same("skipped")) {
            CHECK(payload(group,0) == SKIPPED && payload(group,1) == nd.acquisition_ref
                  && !payload(group,2) && closes == 1 && !ioctls && nd.owner == RELEASED);
        } else if (same("preissue")) {
            CHECK(payload(group,0) == UNISSUED && event(payload(group,1)-1) == NOT_ISSUED
                  && !payload(group,2) && !closes && !ioctls && traps == 1 && nd.owner == HELD);
        } else {
            CHECK(payload(group,0) == PRE_REJECTED && event(payload(group,1)-1) == SUBMITTED
                  && event(payload(group,2)-1) == LOAN && closes == 1 && !snapshots);
        }
        return 0;
    }
    if (same("lost-ioctl") || same("early-timer") || same("duplicate") || same("bad-command")
        || same("double-timer") || same("old-word") || same("conflict-first")
        || same("conflict-last") || same("saturated")) {
        CHECK(rc == -1 && traps == 2 && nd.active == CONTROL_SERVICE && nd.owner == HELD
              && !closes && !snapshots && nd.pinned && !nd.decision);
        if (same("saturated")) CHECK(probe_receives == 9);
        nd_completions[1].result = 0; nd_reply[124] ^= 1;
        CHECK(nd.seq == seq && nd_hook(&r,40) == -1 && capture());
        return 0;
    }
    if (same("zero-id") || same("zero-sequence") || same("unknown-flags") || same("valid-absent")
        || same("nonzero-absent") || same("false-deadline") || same("out-of-order")
        || same("late-readiness") || same("late-cleanup") || same("unflagged-raw")
        || same("modified-request") || same("false-absence")) {
        CHECK(rc == -1 && !seen_loan && !nd.worker_failure && payload(find(NO_FRAME),0) == REJECTED);
        return 0;
    }
    if (same("undefined") || same("malformed") || same("mutate") || same("eof")
        || same("absent-raw") || same("clock-before")) {
        group = find(NO_FRAME);
        CHECK(rc == -1 && !seen_loan && group && closes == 1 && nd.owner == RELEASED);
        s = find(SHORT_VERDICT);
        CHECK(payload(s,0) == group && payload(s,1) == nd.failure_seq);
        if (same("undefined")) CHECK(payload(group,0) == UNDEFINED && !snapshots && !nd.worker_failure);
        else if (same("malformed") || same("mutate")) {
            CHECK(payload(group,0) == REJECTED && snapshots == 1 && s == group+1
                  && !nd.worker_failure && (payload(s,2) & 3) == 1);
        } else {
            CHECK(payload(group,0) == ABSENT && nd.worker_failure && s == group+2);
            CHECK(payload(group+1,2) == nd.worker_failure && payload(nd.worker_failure,1) == 0);
            CHECK(((payload(nd.worker_failure,0) >> 16) & 1) == (unsigned)same("eof"));
        }
        return 0;
    }
    group = find(FRAME0); s = find(VERDICT);
    CHECK(snapshots == 1 && seen_loan == 1 && s == group+7 && payload(s,0) == group
          && payload(s,1) == nd.entry && payload(group+3,0) == 0x123456ab);
    CHECK(!memcmp(nd_trace[group-1]+20,arm+48,12) && !memcmp(nd_trace[group]+20,arm+60,12));
    CHECK(payload(group+2,0) == 0x123456ab && !payload(group+2,1) && !payload(group+2,2));
    CHECK(payload(group+3,1) == 411 && payload(group+3,2) == nd.entry);
    if (same("timer-separated")) {
        CHECK(rc == -1 && nd.failure == EARLY_WAKE && nd.ack_valid && nd.ack_bound == 147
              && word(nd_reply+104) == 100 && now == 247 && payload(s,2) == 5);
        return 0;
    }
    if (same("handback-time") || same("handback-expired") || same("handback-lease")) {
        CHECK(rc == -1 && nd.owner == RELEASED && find(OUTPUT)
              && nd.failure == (same("handback-expired") ? EXPIRED : CLOCK_FAULT));
        return 0;
    }
    if (same("delayed-validation") || same("mixed-loss") || same("late-loss") || same("missing-receipt-clock")) {
        CHECK(nd.ack_valid == !same("missing-receipt-clock"));
        CHECK(payload(s,2) == (same("late-loss") ? 10U : same("mixed-loss") ? 2U :
                               same("delayed-validation") ? 5U : 0U));
        CHECK(rc == (same("delayed-validation") ? 1 : -1));
        if (same("late-loss")) CHECK(nd.failure == EXPIRED);
        if (same("delayed-validation")) CHECK(nd.ack_bound == 47 && now == 247);
        return 0;
    }
    if (same("dip-clock-loss") || same("timer-first") || same("timer-last")) {
        CHECK(rc == -1 && payload(s,2) == (same("dip-clock-loss") ? 0U : 10U));
        CHECK(!closes && nd.pinned && nd.owner == HELD && !nd.active);
    } else if (same("late-dip") || same("late-outer")) {
        CHECK(rc == -1 && payload(s,2) == (same("late-dip") ? 6U : 10U));
        CHECK(closes == (unsigned)same("late-dip"));
    } else if (same("close-expired")) {
        CHECK(rc == -1 && find(NOT_ISSUED) && nd.owner == HELD && traps == 2 && !closes);
    } else if (same("release-unconfirmed") || same("positive-close") || same("negative-close") || same("no-release") || same("global-close")) {
        CHECK(rc == -1 && nd.pinned && nd.owner == CLOSING && closes == 1 && !nd.active);
    } else if (same("late-close")) {
        CHECK(rc == -1 && !nd.pinned && nd.owner == RELEASED && find(LATE_RESOURCE));
    } else if (same("late-duplicate")) {
        CHECK(rc == -1 && nd.disputed == 7 && nd.owner == CLOSING && nd.pinned && nd.queue_live);
    } else if (same("stop-failed")) {
        CHECK(rc == -1 && nd.timer_live && nd.queue_live && nd.pinned);
    } else if (same("clock-after") || same("clock-at-latch") || same("cleanup-failure")) {
        CHECK(rc == -1 && nd.worker_failure && nd.inner == 2 && closes == 1 && nd.owner == RELEASED);
        CHECK(!nd.pinned && word(output+24) == 1);
        CHECK((payload(group+5,1)&255) == 2 && (payload(group+5,2)&255) == 28);
    } else {
        CHECK(rc == 1 && !nd.pinned && nd.owner == RELEASED && closes == 1 && traps == 3);
        CHECK(payload(s,2) == 5 && blocks == 3 && nd.inner == 1);
    }
    if (same("clipped")) CHECK(nd.end == word(nd_reader+28) && timer_delay < 50000000);
    if (same("torn")) {
        snap = nd.seq;
        for (i=0; i<snap; ++i) {
            nd_trace[i][19] ^= 1; CHECK(!capture()); nd_trace[i][19] ^= 1;
            nd_checks[i][3] ^= 1; CHECK(!capture()); nd_checks[i][3] ^= 1;
        }
        nd_trace[0][20] ^= 1; put(nd_checks[0],fnv(nd_trace[0])); CHECK(!capture());
        nd_trace[0][20] ^= 1; put(nd_checks[0],fnv(nd_trace[0])); CHECK(capture());
        nd_commit[31] = 1; CHECK(!capture()); nd_commit[31] = 0;
        put(nd_commit+4,snap-1); CHECK(!capture()); put(nd_commit+4,snap);
        CHECK(!nd_emit(TERMINAL,1,2,3) && capture());
    }
    CHECK(event(seq-1) == TERMINAL);
    return 0;
}

__asm__(".globl _start\n_start:\n push 12(%esp)\n push 12(%esp)\n call run\n"
        " mov %eax,%ebx\n mov $1,%eax\n int $0x80");
