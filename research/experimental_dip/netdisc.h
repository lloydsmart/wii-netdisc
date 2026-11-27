// SPDX-License-Identifier: GPL-3.0-only
#ifndef NETDISC_H
#define NETDISC_H

#include "plugin.h"

#define ND_ARM 0xf7
#define ND_READ 0x8dU
#define ND_VERSION 1
#define ND_INSTANCE 1
#define ND_SLOT 249
#define ND_DIP_BUILD 0x4e440501
#define ND_GX_BUILD 0x47580501
#define ND_LIMIT 64
#define ND_RECORDS 320
#define LINE __attribute__((aligned(32)))
#define OBSERVED __attribute__((noinline))
#define ASSERT_SIZE(name, expr) typedef char name[(expr) ? 1 : -1]

/* Big-endian sizing fixture. No pointer in this input is followed. */
struct nd_arm {
    u32 version, instance, slot, dip_build, gx_build, fd;
    u32 command, length, offset, host, peer, port;
    u8 request[24];
    u32 reserved[6];
};

/* Trusted fixture provision, independent of both ioctls. Ends are exclusive. */
struct nd_extent { u32 base, end; };
struct nd_inputs { struct nd_extent arm, read; };
extern volatile struct nd_inputs nd_input_provision;

enum nd_event {
    ARM_OK = 1, REJECT, ENTRY, BIND, PHASE, INTENT, SUBMITTED, COMPLETED,
    SERVICE, LEDGER, FIRST_FAILURE, QUEUE_FAULT, VERIFIED, FINISH, TERMINAL,
    TIMER, TIMER_END, QUEUE, QUEUE_END, QUARANTINE, ENDPOINT, TUPLE, EXPIRED, NOT_ISSUED,
    TX_BYTES = 32, RX_BYTES = 48, VERIFIED_BYTES = 64
};

enum nd_failure {
    BAD_ARM = 1, BAD_READ, BAD_TID, QUEUE_ERROR, TIMER_ERROR, CLOCK_GAP,
    DEADLINE, SUBMIT_LIMIT, TRACE_LIMIT, SUBMIT_ERROR, OLD_WORD,
    UNKNOWN_WORD, MULTIPLE_WORDS, UNARMED_TIMER, BAD_REPLY, RM_ERROR,
    BAD_SERVICE, BAD_COUNT, END_OF_STREAM, ECHO_ERROR, FD_COLLISION
};

struct nd_record {
    u32 seq, instance, tag[2], tick;
    u8 event, phase, operation, attempt;
    u32 a, b;
};

struct nd_run {
    struct nd_arm arm;
    u32 output, seq, tick, start, budget, cleanup_start;
    u8 phase, op, attempt, failed, pinned, frozen, cleanup_latched;
};

struct nd_line { volatile u32 word[8]; };
extern struct nd_line nd_reader;
extern struct nd_run nd;
void nd_emit(unsigned event, u32 a, u32 b);
void nd_bytes(unsigned event, const u8 *data, unsigned count);
void nd_begin_cleanup(u32 epoch);
int nd_fail(unsigned why, u32 detail);
int nd_pin(unsigned why, u32 detail);
s32 nd_finish(void);
s32 nd_exchange(void);
s32 nd_hook(ioctl *call, s32 fd);
u32 nd_take(volatile u32 *once);
#endif
