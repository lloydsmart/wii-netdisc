/* SPDX-License-Identifier: GPL-3.0-only
 * Host-only test doubles for the interfaces used by the two probe C files. */
#ifndef NATIVE_FIXTURE_H
#define NATIVE_FIXTURE_H
#include <stddef.h>
typedef unsigned char u8;
typedef unsigned int u32;
typedef int s32;
typedef struct { u32 command; u32 *inbuf; u32 inlen; u32 *iobuf; u32 iolen; } ioctl;
typedef struct { u32 command, result, rest[6]; } ipcmessage;
typedef struct { void *data; u32 len; } ioctlv;
#define MEM1_SIZE 0x01800000U
void *memcpy(void *, const void *, size_t);
void *memset(void *, int, size_t);
int memcmp(const void *, const void *, size_t);
void os_sync_before_read(void *, s32);
void os_sync_after_write(void *, s32);
s32 os_get_thread_id(void);
s32 os_timer_now(s32);
s32 os_create_timer(s32, s32, s32, s32);
s32 os_destroy_timer(s32);
s32 os_message_queue_create(void *, u32);
s32 os_message_queue_destroy(s32);
s32 os_message_queue_receive(s32, u32 *, u32);
s32 os_open_async(const char *, s32, void *, void *);
s32 os_close_async(s32, void *, void *);
s32 os_ioctl_async(s32, s32, void *, s32, void *, s32, ...);
s32 os_ioctlv_async(s32, s32, s32, s32, ioctlv *, ...);
#endif
