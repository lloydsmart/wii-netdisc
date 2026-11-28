// SPDX-License-Identifier: GPL-3.0-only
#ifndef ND_ADAPTER_H
#define ND_ADAPTER_H
#include "plugin.h"

#define LINE __attribute__((aligned(32)))
#define OBSERVED __attribute__((noinline))
#define ASSERT_SIZE(name, test) typedef char name[(test) ? 1 : -1]
#define ND_ARM 0xf7
#define ND_READ 0x8dU
#define HALF 0x80000000U
#define FIVE 9492187U
#define THIRTY 56953125U
#define FIFTY 94921875U
#define CUTOFF 104414062U

/* Local fixture declarations. The two independently prepared descriptions
 * represent the intended session and the confirmed exclusive registration. */
struct extent { u32 base, end; };
struct service {
    char path[32];
    u32 selector, instance, build, worker_tid, worker_pid, opener, session;
};
struct provision {
    struct extent arm, read, output, request, reply;
    u32 ios, ios_build, dip, dip_build, slot, gx, gx_build, claim, epoch, lease;
    struct service expected, registered;
    u32 ownership, registration, visible, ready;
    u32 single_delivery, retirement, release, timer_retirement;
    u32 stale_token, stale_epoch, stale_lease, fd_epoch, wake_token, padding;
};
extern volatile struct provision nd_provision;
/* Independently provisioned per-slot contract, installed before arm. Each
 * flag is conditional on this exact loan and a unique matching delivery.
 * fd_epoch identifies the exclusively owned descriptor namespace lifetime. */
enum effect { PRE_ADMISSION_CODE = 1, RETIRES_ONCE = 2, RELEASES_ORIGINAL = 4 };
struct effects {
    u32 ios, session, claim, open_ordinal, fd_epoch, address, flags, rejection_code;
};
extern volatile struct effects nd_effects[3];

enum operation { NO_OP, OPEN_SERVICE, CONTROL_SERVICE, CLOSE_SERVICE };
enum event {
    ARM_BIND = 1, ARM_TAG, ARM_TUPLE, ARM_PEER, ARM_RECEIPT, ARM_REJECT, ENTRY, SESSION,
    LEASE, OBSERVER, OUTER, SETUP, INTENT, NOT_ISSUED, SUBMITTED, COMPLETION, LOAN, RESOURCE,
    FRAME0, FRAME1, FRAME2, FRAME_ID, FRAME_TIMES, FRAME_STATUS, DIP_TIME, VERDICT,
    NO_FRAME, ABSENT_FAILURE, SHORT_VERDICT, FIRST_FAILURE, FIRST_ANOMALY, WORKER_FAILURE,
    LATE_RESOURCE, TIMER_END, QUEUE_END, OBLIGATIONS, DISPOSITION, OUTPUT, TERMINAL, CAPACITY
};
enum reason {
    BAD_ARM = 1, BAD_READ, BAD_SERVICE, WRONG_CALLER, CLOCK_FAULT, EXPIRED, QUEUE_SETUP,
    TIMER_SETUP, BAD_WORD, DUPLICATE_WORD, OLD_WORD, RECEIVE_ERROR, QUEUE_FULL, EARLY_WAKE,
    NO_COMPLETION, BAD_COMMAND, SUBMIT_ERROR, OP_ERROR, UNRETIRED, BAD_PREFIX, BAD_IDENTITY,
    BAD_MASK, BAD_PHASE, BAD_TIME, BAD_OUTCOME, BAD_FRAME, INNER_FAILURE, DIP_LATE,
    UNRELEASED, TEARDOWN_ERROR, NO_CAPACITY
};
enum control_state { SKIPPED = 1, UNISSUED, PRE_REJECTED, UNDEFINED, ABSENT, REJECTED };
enum ownership { NO_ACQUISITION, POSSIBLE, HELD, CLOSING, RELEASED };
enum timing { INDETERMINATE, TIMELY, LATE };

/* The private arm snapshot is the original 96 wire bytes. */
struct run {
    struct provision p;
    u8 arm[96];
    u32 tick, start, end, observer, last, issue, claim, seq, entry, failure_seq, anomaly_seq;
    u32 arm_input, ack_bound;
    u32 failure, acquisition_ref, operation_ref, loan_ref, worker_failure, decision, short_form;
    s32 tid, fd, queue, timer;
    u8 op, ordinal, issued, active, owner, frozen, bad_queue, timer_seen;
    u8 clock_started, clock_fault, deadline_set, inner, pinned, timer_live, queue_live, capacity, stale_seen, disputed, issued_slots, ack_valid;
};
extern struct run nd;
extern u8 nd_request[160], nd_reply[192], nd_reader[32], nd_commit[32];
extern u8 nd_trace[48][32], nd_checks[48][4];
extern ipcmessage nd_completions[3];
extern char nd_path[32];

static inline u32 word(const u8 *b)
{
    return ((u32)b[0] << 24) | ((u32)b[1] << 16) | ((u32)b[2] << 8) | b[3];
}
static inline void put(u8 *b, u32 n)
{
    b[0] = n >> 24; b[1] = n >> 16; b[2] = n >> 8; b[3] = n;
}
static inline u32 arm_word(unsigned offset) { return word(nd.arm + offset); }
u32 nd_take(volatile u32 *);
s32 nd_hook(ioctl *, s32);
unsigned nd_emit(unsigned, u32, u32, u32);
unsigned nd_failure_record(unsigned event, unsigned why, s32 raw, int observed);
void nd_latch_failure(unsigned, s32, int);
void nd_fail(unsigned, s32, int);
void nd_exchange(void);
unsigned nd_sample(void);
unsigned nd_verdict(u32 deadline);
void nd_make_request(void);
void nd_validate_reply(void);
void nd_short_decision(unsigned kind, unsigned reason, const u8 *response);
#endif
