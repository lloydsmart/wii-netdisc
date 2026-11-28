@ SPDX-License-Identifier: GPL-3.0-only
@ Single-core ARMv5 atomic one-use claim. Thumb callers interwork via bx.
    .text
    .arm
    .align 2
    .global nd_take
    .type nd_take, %function
nd_take:
    mov r1, #1
    swp r2, r1, [r0]
    mov r0, r2
    bx lr
    .size nd_take, . - nd_take
