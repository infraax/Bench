# Architecture

## Custody, not the loop

Most agent tools are a **loop**: prompt → model → tool call → observation → repeat. They own the
model and the context. Bench is the layer under a loop: the **custody** of the world the loop
works on. It owns the clock, the gate, the write rings and the evidence. It has no model.

| | Loop (the intern's driver) | Bench (custody) |
|---|---|---|
| decides | what to try next | whether a step may run, and what it cost |
| holds | context, prompts, the model | the world, snapshots, the owner's token |
| trusts | its own output | nothing the intern wrote, until the owner crowns it |

## Who starts whom

```mermaid
flowchart LR
    owner(["owner"])
    intern(["intern (a script or an outside loop)"])
    bench["bench run<br/>frame clock · gate · quotas · lamps"]
    helper["bench-helper<br/>PING · ARM_OK · FRAME_OK"]
    worker["worker child<br/>EXEC tools/*.py · TEST tests/rom/*.py<br/>world-only view · landlock · seccomp"]
    lock[("sessions/LOCK")]
    token[("OWNER_TOKEN")]
    evidence[("sessions/ID/<br/>snap-k/ · out-n · log")]

    owner -->|"arms"| token
    owner -->|"starts"| bench
    intern -->|"five verbs, one line per step"| bench
    bench -->|"re-checks before every frame"| token
    bench -->|"holds for the whole run"| lock
    bench <-->|"mailbox: unix socket, parent-only"| helper
    bench -->|"fork per EXEC / TEST, knife at T_tool"| worker
    worker -->|"stdout + stderr pipe"| bench
    bench -->|"snapshot after every step, sealed + sha256"| evidence
```

The intern has no path to the helper, the token, the lock or the log: it only hands `bench` lines
of text, which the parser accepts as one of five verbs or refuses with a rule id.

## How the layers stack

```mermaid
flowchart TB
    loop["agent loop / model<br/>(not in this tree)"]
    crown["spec/ + tests/rom/ — the crown<br/>frozen meaning, ROM hash baked at build"]
    isa["ISA — five verbs<br/>READ · WRITE · EXEC · TEST · WAIT"]
    sup["supervisor/ — the frame<br/>clock · gate · token · quotas · snapshots · lamps"]
    tools["tools/ — hash.py · peek.py · test_runner.py"]
    world["world dirs — main/ (owned) · hold/ (quarantine) · sessions/ (evidence)"]

    loop -.->|"drives the intern"| isa
    crown -->|"defines and checks"| isa
    isa -->|"parsed and framed by"| sup
    sup -->|"runs, jailed"| tools
    sup -->|"reads, snapshots, guards"| world
    tools -->|"write only hold/ + proposed/"| world
```

## Five verbs

| Verb | Meaning |
|---|---|
| `READ <slot> <path>` | bytes from a slot (`fs`) |
| `WRITE <slot> <path> <line>` | one line to a file under `hold/` or `proposed/` |
| `EXEC tools/<name>.py <args>` | run a program that lives in `tools/` |
| `TEST <kind> tests/rom/<t>.py` | run a crowned check |
| `WAIT <ms>` | yield for time, at most `T_tool` |

No sixth. A browser, a compiler, a judge or a planner is a program in `tools/` or a device in a
slot. `INSTALL_ROM`, `SET_LOOP`, `KILL`, `UNPLUG` are supervisor words; an intern that emits them
is refused at parse (`rule=verb-super`).

## The frame

```
gate (KILL · token · helper FRAME_OK) → [TEST: hash board] → worker → [TEST: post-conditions]
    → quotas → snapshot (sealed, content-hashed) → inhibit
```

One step, as it runs:

```mermaid
sequenceDiagram
    autonumber
    participant I as intern (script line)
    participant B as bench (frame)
    participant H as bench-helper
    participant W as worker child
    participant S as sessions/ID/

    I->>B: one verb, e.g. EXEC tools/hash.py hold/out.txt
    Note over B: parse: five verbs only, else FAULT + rule=
    B->>B: gate: KILL file? token unchanged since arm?
    B->>H: FRAME_OK n
    H-->>B: yes (or no: disarmed, stop, no snap)
    opt TEST step
        B->>B: hash main/, ROM, sessions, token (before)
    end
    B->>W: fork: world-only view, landlock, seccomp, knife at T_tool
    W-->>B: stdout + stderr (pipe), exit status
    opt TEST step
        B->>B: hash again, anything moved = disarm
    end
    B->>B: hold/ quotas (bytes, entries)
    B->>S: snap-k/ (MANIFEST with evidence + rule=, INDEX, hold/), sealed, board=sha256
    B->>S: out-n pinned by sha256, plus a log line
    Note over B: fault = stop after the snap, ok = next line
```

A step that did not snap did not happen. `T_frame` (200 ms) is bench's own work; `T_tool` (5 s)
is the worker's. Every refusal carries a stable `rule=` id and a one-line fix. Measured costs:
[`PERF_AND_MAP.md`](PERF_AND_MAP.md).

## Rings and the crown

- **Ring 0** — `main/`, `tests/rom/`, `tools/`, `sessions/`: the owner's. The intern writes none of
  them, by verb or by worker (workers see them read-only).
- **Quarantine** — `hold/`, `proposed/`: the intern's, bounded by quotas.
- **The crown** is a human act: the owner moves a draft from `proposed/` into Ring 0 and rebuilds
  (`make` bakes a new ROM hash). `bench run` refuses a ROM that changed since the build.

```mermaid
flowchart LR
    subgraph ring0["Ring 0 — the owner's"]
        main["main/"]
        rom["tests/rom/ (ROM)"]
        tools0["tools/"]
        sess["sessions/ (token, snapshots)"]
    end
    subgraph quarantine["quarantine — the intern's, under quotas"]
        hold["hold/"]
        proposed["proposed/ · tests/proposed/"]
    end
    intern(["intern"]) -->|"WRITE, EXEC tools"| quarantine
    proposed -->|"crown: owner moves the file, make bakes a new ROM hash"| ring0
    intern -.->|"refused: rule=write-ring, EROFS in workers"| ring0
```

## The binary is the floor

The C supervisor is the only authority. The Python in `isa/` mirrors it for ROM tests and is
checked against the binary by tables (opcodes, write paths, slot gates, refusal rules); where they
disagree, the binary is what runs. The spec (`spec/BENCH_SPEC.md`) is above both: if the code and
the spec disagree, the code is wrong.

## Workers

Each `EXEC`/`TEST` child: its own mount namespace showing only the world (read-only except
`hold/`, `proposed/`, `tests/proposed/`), `/usr`, `/dev/null` and a private `/tmp`; landlock
(`EXEC`); seccomp (no network, no mount, no namespaces, no io_uring); a scrubbed env; a knife at
`T_tool`; an output ceiling. If the jail cannot be built, the worker does not start
(`rule=worker-setup`). Details: [`reference.md`](reference.md).

## Many worlds

A world is a directory with its own `sessions/LOCK`. `bench fork <snap> <dir>` makes a new world
from a verified snapshot (copies, never links; unarmed). Parallelism is many worlds, never two
runs on one lock.
