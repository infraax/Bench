/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* woz_bus.h
 *
 * slot 4 is 4. lamps are one byte. talk to the head.
 * i used to do this with a register and a PROM. this is that,
 * without pretending we needed a protocol church.
 */
#ifndef WOZ_BUS_H
#define WOZ_BUS_H
#include <stdint.h>

/* one byte, three lights. if your UI disagrees with this byte, your UI is wrong. */
#define LAMP_MAIN  (1u<<0)
#define LAMP_HOLD  (1u<<1)
#define LAMP_BLIND (1u<<2)

/* slots are indices. name is a courtesy sticker on the cage. */
enum { SLOT_FS=0, SLOT_TTY=1, SLOT_FB=2, SLOT_JUDGE=3, SLOT_RADIO=4, SLOT_N=5 };

typedef struct {
    uint8_t  lamps;
    uint8_t  plug;     /* bit i set => slot i has a cable in */
    uint16_t cap[SLOT_N];
} Bus;

static inline uint8_t lamp_set(uint8_t lamps, uint8_t bit) {
    /* MAIN and HOLD are not allowed on together. that's two vias arguing.
       asking for both at once is a caller bug: HOLD wins, MAIN stays dark. */
    if ((bit & LAMP_MAIN) && (bit & LAMP_HOLD)) bit &= (uint8_t)~LAMP_MAIN;
    if (bit & LAMP_MAIN) lamps &= (uint8_t)~LAMP_HOLD;
    if (bit & LAMP_HOLD) lamps &= (uint8_t)~LAMP_MAIN;
    lamps = (uint8_t)((lamps | bit) & (LAMP_MAIN|LAMP_HOLD|LAMP_BLIND));
    /* a bad byte coming in does not go out: same rule, HOLD wins. */
    if ((lamps & LAMP_MAIN) && (lamps & LAMP_HOLD)) lamps &= (uint8_t)~LAMP_MAIN;
    return lamps;
}

static inline int plugged(const Bus *b, int slot) {
    if (slot < 0 || slot >= SLOT_N) return 0;
    return (b->plug >> slot) & 1;
}

/* pull the cable. BLIND means fb AND radio are both out: no eyes, no news.
   it is read off the plug bits every time, never set by hand, not a fourth religion. */
static inline void pull(Bus *b, int slot) {
    if (slot < 0 || slot >= SLOT_N) return;
    b->plug = (uint8_t)(b->plug & (uint8_t)~(1u << slot));
    if (plugged(b, SLOT_FB) || plugged(b, SLOT_RADIO))
        b->lamps = (uint8_t)(b->lamps & (uint8_t)~LAMP_BLIND);
    else
        b->lamps = (uint8_t)(b->lamps | LAMP_BLIND);
}

/* one byte: lamps in bits 0-2, plugs in bits 3-7. intern may READ these bits, never WRITE them. */
static inline uint8_t peek(const Bus *b) { return (uint8_t)((b->lamps & 7) | (b->plug << 3)); }

#endif
