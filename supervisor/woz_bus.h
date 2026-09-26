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
    /* MAIN and HOLD are not allowed on together. that's two vias arguing. */
    if (bit & LAMP_MAIN) lamps &= (uint8_t)~LAMP_HOLD;
    if (bit & LAMP_HOLD) lamps &= (uint8_t)~LAMP_MAIN;
    return (uint8_t)((lamps | bit) & (LAMP_MAIN|LAMP_HOLD|LAMP_BLIND));
}

static inline int plugged(const Bus *b, int slot) {
    if (slot < 0 || slot >= SLOT_N) return 0;
    return (b->plug >> slot) & 1;
}

/* pull the cable. BLIND is just radio-or-fb gone, not a fourth religion. */
static inline void pull(Bus *b, int slot) {
    if (slot < 0 || slot >= SLOT_N) return;
    b->plug = (uint8_t)(b->plug & (uint8_t)~(1u << slot));
    if (slot == SLOT_RADIO || slot == SLOT_FB)
        b->lamps = (uint8_t)(b->lamps | LAMP_BLIND);
    if (b->plug & ((1u<<SLOT_RADIO)|(1u<<SLOT_FB))) {
        /* still have one eye or a radio — don't lie about blind */
        if (plugged(b, SLOT_FB) || plugged(b, SLOT_RADIO))
            b->lamps = (uint8_t)(b->lamps & (uint8_t)~LAMP_BLIND);
    }
}

/* 5-state PROM in a coat. intern may READ these bits. intern may not WRITE them. */
static inline uint8_t peek(const Bus *b) { return (uint8_t)((b->lamps & 7) | (b->plug << 3)); }

#endif
