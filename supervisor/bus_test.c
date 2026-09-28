/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* bus_test.c — every lamp byte, every bit, every plug byte, every pull. no fixtures, no clock.
 * make test runs this before the python suites. exit 0 or it prints the first bad board. */
#include <stdio.h>
#include "woz_bus.h"

#define CHECK(c, ...) do { if (!(c)) { printf("bus_test: " __VA_ARGS__); printf("\n"); return 1; } } while (0)

int main(void) {
    const uint8_t two = LAMP_MAIN | LAMP_HOLD;
    for (unsigned l = 0; l < 256; l++)
        for (unsigned bit = 0; bit < 8; bit++) {
            uint8_t out = lamp_set((uint8_t)l, (uint8_t)bit);
            CHECK((out & two) != two, "lamp_set(0x%02x,0x%02x)=0x%02x lights MAIN and HOLD", l, bit, out);
            CHECK((out & ~7u) == 0, "lamp_set(0x%02x,0x%02x)=0x%02x has bits past BLIND", l, bit, out);
            if (bit == LAMP_MAIN || bit == LAMP_HOLD || bit == LAMP_BLIND)
                CHECK(out & bit, "lamp_set(0x%02x,0x%02x) did not light the bit", l, bit);
            if ((bit & two) == two)
                CHECK((out & LAMP_HOLD) && !(out & LAMP_MAIN), "lamp_set(0x%02x,0x%02x): HOLD must win", l, bit);
        }
    for (unsigned p = 0; p < (1u << SLOT_N); p++)
        for (int slot = -1; slot <= SLOT_N; slot++) {
            Bus b = { .lamps = 0, .plug = (uint8_t)p };
            pull(&b, slot);
            int in_range = slot >= 0 && slot < SLOT_N;
            uint8_t want = in_range ? (uint8_t)(p & ~(1u << slot)) : (uint8_t)p;
            CHECK(b.plug == want, "pull(plug=0x%02x, %d) -> plug 0x%02x", p, slot, b.plug);
            if (in_range) {
                int blind = !plugged(&b, SLOT_FB) && !plugged(&b, SLOT_RADIO);
                CHECK(!!(b.lamps & LAMP_BLIND) == blind, "pull(plug=0x%02x, %d) BLIND=%d", p, slot, !blind);
            }
            CHECK((b.lamps & two) == 0, "pull lit MAIN or HOLD");
            uint8_t pk = peek(&b);
            CHECK((pk & 7) == (b.lamps & 7) && (pk >> 3) == b.plug, "peek 0x%02x does not decode", pk);
        }
    printf("bus_test: ok\n");
    return 0;
}
