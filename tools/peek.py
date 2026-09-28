# SPDX-License-Identifier: MIT OR Apache-2.0
"""talk to the head. read-only.

decodes the lamp byte in sessions/<current>/STATE using the bits in supervisor/woz_bus.h.
the header is the only definition; this file parses it rather than keeping a copy.
"""
import os
import re
import sys
from pathlib import Path

IMAGE = Path(__file__).resolve().parents[1]


def woz_bits(header=IMAGE / "supervisor" / "woz_bus.h"):
    src = Path(header).read_text()
    lamps = {m[0]: 1 << int(m[1]) for m in re.findall(r"#define LAMP_(\w+)\s+\(1u<<(\d+)\)", src)}
    enum = re.search(r"enum\s*\{([^}]*)\}", src).group(1)
    slots = {m[0].lower(): int(m[1]) for m in re.findall(r"SLOT_(\w+)=(\d+)", enum) if m[0] != "N"}
    return lamps, slots


def state(world):
    sessions = Path(world) / "sessions"
    cur = (sessions / "CURRENT").read_text().strip()
    text = (sessions / cur / "STATE").read_text()
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def lit(lamp_byte, lamps):
    return [name for name, bit in sorted(lamps.items(), key=lambda kv: kv[1]) if lamp_byte & bit]


if __name__ == "__main__":
    world = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BENCH_ROOT", ".")
    lamps, slots = woz_bits()
    st = state(world)
    byte = int(st["lamps"], 16)
    plug = int(st["plug"], 16)
    print(f"lamps=0x{byte:02x} {' '.join(lit(byte, lamps)) or '(dark)'}")
    print("plugged=" + " ".join(n for n, i in sorted(slots.items(), key=lambda kv: kv[1]) if plug >> i & 1))
