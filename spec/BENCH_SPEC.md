# Bench

**Work here. Decide what goes home.**

A closed intern-ISA with quarantine, typed evidence, and a crown the ghost cannot wear.  
Customer name: **Bench.** Engineering name in this file: the machine.  
Status: decided through four design rounds, a form/runtime pass, a Jobs surface pass, and four core sources. Open bets are marked. They are not theorems.

---

## 0. One sentence

A small ISA around an unreliable intern: five actuators, mapped sensors, framed steps, typed evidence, privilege rings. The intern may labor in quarantine. Only ROM crowns. Tomorrow is a reload with the ghost unplugged.

---

## 1. The room

This spec is the product of a round table, not teams.

| Role | Person | Vote |
|---|---|---|
| Algebra / ownership | George Hotz | yes |
| Loop physics / ship | John Carmack | yes |
| Representation / leash | Andrej Karpathy | yes |
| Fewest parts / play | Steve Wozniak | yes |
| Taste-advisor | Steve Jobs | artifact gate only |
| Standing judge | Leslie Lamport | process: unwritten ≠ decided |
| Wild-card judge | Sophie Wilson | process + metal: if it is not an instruction or a cycle, say what it is |

**House rules (Lamport, Wilson)**

1. One object per round.
2. A claim is a theorem-as-design, a measurement, or a bet. Mark it.
3. Decision = a paragraph both judges can initial.
4. Jobs-pass is last on a paragraph. He may cut surface. He may not add verbs.
5. No factions. Steelmans assigned.

**What each operator was hunting**

| Person | Scarce resource | Question they would not leave |
|---|---|---|
| Hotz | closed ontology + off-switch | What is a legal move, and who can add a new one? |
| Carmack | milliseconds + known state | What happens in one step, how long may it take, what exists after? |
| Karpathy | leash + verifiable chunks | What can be checked fast enough that the intern may run? |
| Woz | part count you can hold and show | Which parts are middlemen, and can a person see the whole board? |

**The one question all four had to sit on**

> What is the minimum closed machine an unreliable intern may touch, such that a human still owns the result tomorrow?

---

## 2. Decision log

### Round 1 — hands

**Object:** what is allowed to exist.

**Positions**

- Hotz: five verbs; filesystem bus; git memory; no planner daemon, no MCP garden, no skill-runtime ISA.
- Carmack: one step = one frame; budget; serializable snapshot; planner is a function with a deadline or it is a daemon.
- Karpathy: intern is already author; design the leash; 1.0 / 2.0 / 3.0 on a slider; verification is the compiler of 3.0.
- Woz: count parts; talk to the head; open slots named by seat; Homebrew demo as review.

**Ink**

- Actuators closed at five: `read`, `write`, `exec`, `test`, `wait`.
- Sensors are slots, not verbs.
- One step = observe → ≤1 actuator → observe → optional test → commit snapshot.
- Long work is N steps, declared, killable.
- Unattended permitted iff a test or scalar metric is defined first.
- Snapshot + files + git on disk the human controls. Transcript is a log, not RAM.

**Who won which clause, and why**

| Clause | Settled toward | Why |
|---|---|---|
| Verb set | Hotz | Wilson: an ISA must be finite. Karpathy granted five *actuators* if sensors stay explicit. |
| Sensors | Karpathy + Woz | Perception is not an actuator. Slots are pullable cables (Woz) and optional eyes (Karpathy). |
| Frame | Carmack | Lamport: if it is not a state machine with a commit, it is a chat. |
| Unattended | Hotz ∧ Karpathy | Test-gated (Hotz) and metric-declared (Karpathy). Not “improve the company.” |
| Unplug | Hotz + Woz | Ownership is local. Radio is a card. |

**Rejected:** sixth actuator, multi-agent company, MCP as ontology, chat-as-world-state.

---

### Round 2 — evidence

**Object:** what counts as evidence. A check you cannot see is a priest. Eyes with no check are vibe.

**Ink**

Evidence is typed on every world-changing step: `{kind, budget_used, slot, hash, dirty}`.

| Kind | Dirty | May crown `owned` |
|---|---|---|
| `pure` (script, compiler, bench, golden) | no | yes |
| `scalar` in-repo, no model | no | yes |
| `judge` (human or model score file) | yes | no (open after R2; closed in R3) |
| `visual` (framebuffer sample) | depends | not by itself |

Eyes are `fb.read(rect, scale) → bytes`, not a verb. Carmack: feedback pass (MegaTexture shape), not a composited desktop. Sample hashed into the snapshot. Click/browse are `exec` of a program in a slot.

**Who / why**

| Piece | Forced by | Why |
|---|---|---|
| Typed evidence | Lamport | Predicate or it is poetry. |
| Dirty ≠ crown (direction) | Hotz | Slop grading slop. |
| Judge as DMA / slot | Wilson + Karpathy | Neural judge is a device on the bus, not the CPU “understanding.” |
| Rectangle sample | Carmack + Karpathy | Eyes exist; unbounded desktop grab is a missed frame. |
| Pullable cable | Woz | Club test: priest sick, board still runs. |

---

### Round 3 — the crown

**Object:** may a dirty judge promote, or only delay death?

**Ink:** dirty never crowns.

Ownership is a lattice, not a boolean (Lamport). Privilege rings (Wilson):

| Ring | Who | May write |
|---|---|---|
| 0 ROM | human key, pure test runner, dead scalar | `owned`, `INSTALL_ROM`, `SET_LOOP` |
| 1 | intern + dirty devices + long notch | `hold/` only |
| 2 | intern actuators | working snapshot, `proposed/` |

```
held         snapshot exists
proposed     intern emitted a diff / file
quarantined  in hold/
promoted     Ring 0 wrote the bit
owned        promoted ∧ reloadable with models and judge unplugged
```

Two address spaces: `main/` (ghost-unplugged) and `hold/` (may need judge/model; halt if they vanish). Merge `hold → main` is Ring 0 only.

**Who / why**

| Move | Who | Why the others accepted |
|---|---|---|
| Dirty cannot write `owned` | Hotz | Algebra dies if slop stamps slop. |
| Lattice not bool | Lamport | “Owned” was a type error. |
| Rings | Wilson | Intern is user mode. Dirty is another user. Supervisor bit is ROM. |
| Quarantine / `hold/` | Carmack | Rank in one address space, crown in another. Main stays reloadable. |
| Keep the long notch | Karpathy | Lost the crown, kept density. Suit, not robot. |
| Lamps MAIN / HOLD | Woz | Two slots on the board, lights a person can see. |

Karpathy’s remaining demand (accepted as design, not as dirty-crown): Ring 0 must include in-repo deterministic scalars so exit from `hold/` is not only a human sitting on the hose.

---

### Round 4 — smuggle and unbounded frame

**Trap A (Hotz):** a prompt walks into Ring 0 wearing a test.  
**Trap B (Carmack):** `hold/` runs overnight and becomes one frame with no edges.

**Ink**

`is_ring0(f)` iff all of:

- in the image (`tests/rom/` or equivalent)
- closed over the snapshot
- does not call a model (no HTTP LLM, no local ghost socket, no judge subprocess)
- deterministic on that snapshot

The intern may draft tests into `proposed/tests/` (`WRITE_TEST`). Installing into ROM (`INSTALL_ROM`) is Ring 0. A prompt may midwife the draft. A prompt is never ROM. If a ROM file grows a network opcode: revert. Spec bug.

`hold/` session file, hashed into snapshot 0, **immutable** for the session:

- `N_max`, `T_step`, `T_session`, `K` snapshot period
- also snapshot on every Ring-1 gate
- out of range ⇒ fault
- raising `N` is `SET_LOOP`, Ring 0
- default `N` is small
- resume loads a snapshot; transcript is not RAM
- kill is local

Notch = those params + which slots are plugged. Changing params mid-loop is a new session.

**Who / why**

| Rule | Who | Why |
|---|---|---|
| Prompts midwife, never ROM | Hotz ∧ Karpathy | 3.0 writes 1.0; 1.0 crowns. Both signed. |
| `calls_model` includes euphemisms | Lamport | No poetry in the predicate. |
| Frozen loop params | Carmack + Wilson | `LOOP n=N cap=T snap=K` or it is not an instruction. |
| Intern cannot raise `N` | Hotz | Otherwise N means “until I like it.” |
| Resume ≠ continue chat | Carmack + Woz | Photograph the board, not the priest talking. |

---

### Form and runtime (wildcard)

**Instruction set is not a programming language (Wilson).** The ISA is the five intern ops plus supervisor ops the intern cannot emit: `INSTALL_ROM`, `SET_LOOP`, `KILL`, `UNPLUG`.

Every step is an opcode stream. Replay is stream + snapshots. Chat is a comment track.

**Languages**

| Layer | Language | Forced by |
|---|---|---|
| Supervisor / frame / clock / snap / hooks / kill | C (small) | Carmack, Wilson |
| Tools, midwife, render, skill loader, ROM tests | Python 3, few deps, radio off by default | Hotz, Karpathy |
| Briefs, skills, session notes | Markdown / English as *data* | Karpathy |

No JS runtime. No container orchestra. No second supervisor. English is never fetched by `test kind=pure`.

**Runtime picture**

One C supervisor thread owns the frame. Intern is a device on the bus. Tools are child processes with `T_step` and a knife. World is directories: `main/`, `hold/`, `proposed/`, `tests/rom/`, snaps, skills, session. If the GUI dies, the machine is still there.

Low-level means kill/unplug as signals and locks, monotonic clock, atomic snap + hash, `fb.sample` as buffer+crop, lamps as bits in a file the UI must mirror.

**Rejected:** Rust-as-church (Hotz), Node (Carmack), English-as-supervisor (Hotz + Wilson), container factory (Woz), custom ASIC fetish (table).

---

### Surface (Jobs pass)

Product name: **Bench.**

Not a chatbot. Not an IDE graveyard. Not a platform. A bench with a stage and lamps.

Customer never hears: harness, agent, copilot, model, ISA, Ring 0, lattice, quarantine.

Customer sees and may use:

| Control | Does |
|---|---|
| Run | start session at current notch |
| Kill | local halt, last snap kept |
| Notch | three detents: Touch / Chunk / Overnight |
| Radio | plug / pull intern+judge network |
| Eyes | plug / pull `fb` |
| Install | promote proposed test → ROM (two-step, ugly on purpose) |
| Demo | run ROM tests, one green |
| Open snap | restore world |

Visible at all times: MAIN / HOLD / BLIND, snapshot id, last step cost, slot list, session `{N,K,caps}` when in Hold.

Jobs vetoes: chat history as home screen; an “Agents” tab; per-tool permission toast spam; Overnight without HOLD lamp; Install that looks friendly.

Jobs does not veto: C supervisor, five verbs, dirty-cannot-crown.

Why *Bench*: harness is livestock and engineering slang. Bench is a place a human stands. One word. Does not need a paragraph.

---

### Tools and abilities (round table)

Built-in means in the image. Tools are slots/`exec`. Abilities are ROM patterns, not verbs.

**Core tools**

| Tool / slot | Whose demand | Why |
|---|---|---|
| `fs` + `git` | Hotz | bus + memory |
| `sh` (bounded) | Hotz | `exec` without a sixth verb |
| `test-runner` | Hotz, Carmack | Ring 0 muscle |
| `clock` + `snap` + `hash` | Carmack | frame is real |
| `fb.sample` | Carmack, Karpathy | eyes as addressing mode |
| `hookd` | Hotz | policy without new ops |
| `skill` + `diff` + `render` | Karpathy | ghost I/O, still files |
| `lamp` + `peek` + `slots` | Woz | board is visible |
| `judge` + `metric` | Karpathy | optional, unplugged on beginner SKU |

**Core abilities**

`frame`, `commit-snap`, `loop`, `resume`, `fault` / `kill` / `unplug`, `install-rom` / `midwife`, `notch` / `sku`, `leash`, `p99` + `lamp`, `layout`.

**Not in core:** planner daemon, MCP garden, neural judge as ROM, desktop-sized framebuffer, “understood the screenshot” as an instruction, one green light.

---

### 1v1s (scored, not design votes)

Judges scored arguments as machines. Points are not amendments to the ISA.

| Bout | Point |
|---|---|
| Hotz vs Carmack (rewrite vs stay) | Carmack |
| Hotz vs Karpathy (English as supervisor) | Hotz |
| Hotz vs Woz (off-switch vs loved box) | Woz |
| Carmack vs Karpathy (clock vs ghost) | Carmack |
| Carmack vs Woz (physics vs vias) | Carmack |
| Karpathy vs Woz (intern at the club) | Karpathy |

**Carmack 3 · Hotz 1 · Karpathy 1 · Woz 1**

Roles those points reflect: Carmack owns edges; Hotz owns the crown fight; Woz owns whether a human will touch it; Karpathy owns that the intern is already in the room.

---

## 3. The machine

### 3.1 Actuators (Ring 2)

| Verb | Meaning |
|---|---|
| `read` | bytes from a named slot |
| `write` | bytes to a named slot |
| `exec` | run a program that lives in a slot |
| `test` | run a check (kind on the ticket) |
| `wait` | yield until time, I/O, or a gate |

No sixth. Browser, click, compiler, judge, planner are programs or devices in slots. A skill is a file. Adding a verb requires written proof it is not these five, both judges.

Supervisor-only (intern emitting these is a spec bug): `INSTALL_ROM`, `SET_LOOP`, `KILL`, `UNPLUG`.

### 3.2 Slots

Named, bounded, pullable.

| Slot | Role |
|---|---|
| `fs` | files, git, skills, tests, snapshots |
| `tty` | bytes in/out |
| `fb` | optional framebuffer: `read(rect, scale) → bytes` |
| `judge` | optional dirty device; score file |
| `tools/*` | programs via `exec` only |

Unplugged slot ⇒ that sense is gone. Blind intern is legal on file work. Unplugged `judge` mid-`hold` ⇒ halt.

Views (AST, HTML) are `read` + program.

### 3.3 Frame

```
observe slots → intern emits ≤1 actuator → observe → evidence ticket → commit snapshot
```

A step that does not commit a snapshot did not occur.  
Each step: wall budget, output-size budget, evidence record, snapshot id.

### 3.4 Evidence

See Round 2 table. Dirty may halt, annotate, or extend `hold/`. Dirty may not write `owned`.

### 3.5 Rings and lattice

See Round 3. Intern never writes Ring 0. Dirty DMA never writes Ring 0.

### 3.6 `is_ring0`

See Round 4. Closed, offline, deterministic, no model call.

### 3.7 `hold/` cadence

See Round 4. Frozen session params. Snapshot every `K` and on gates. Intern cannot raise `N`.

### 3.8 Notches (slider is skin)

| Detent (Jobs) | Typical params | Slots |
|---|---|---|
| Touch | N=1, tiny caps | radio optional, no `fb` required |
| Chunk | small N, `test` pure | radio optional |
| Overnight | large N, `hold/` | optional `judge` and `fb`; Ring 0 to exit to Main |

### 3.9 Surface minimum

MAIN / HOLD / BLIND, last snapshot id, last step cost, slot list and pulled cables, session params in Hold. Two states, not one green. Further beauty is Jobs’s pass (above), not more verbs.

### 3.10 What this is not

Not a multi-agent company. Not an MCP garden. Not a planner daemon. Not English as supervisor. Not a desktop OS soldered into the motherboard. Not a chat log pretending to be world state.

---

## 4. Core sources

Four files. They compose. They do not add verbs.

| File | Author | What it is | Why only they write it that way |
|---|---|---|---|
| `harness/hotz_isa.py` | Hotz | Interned `Step`, closed constructors, `hook()` rewrite | Hash-cons + total constructors. Illegal terms die at birth. CSE is identity. Tinygrad muscle. |
| `harness/carmack_frame.c` | Carmack | Frame loop, monotonic clock, snap-always-then-inhibit, session edges | Worst-case is the design. Skipping snap because “nothing changed” is hidden state. |
| `harness/woz_bus.h` | Woz | One lamp byte, slots as indices, `pull` / `peek` | Fewest parts. MAIN and HOLD cannot be lit together. Intern may read the head, not write it. |
| `harness/karpathy_rom.py` | Karpathy | `is_ring0` as AST fold, midwife, leash | 3.0 writes 1.0. Purity is a local dirty-bit reduced OR — micrograd shape on a different object. |

Composition:

```
intern emit → Hotz Step (interned, hooked)
                  → Carmack frame (clock, snap, N)
                  → Woz bus byte (lamps, plugs)
                  → Karpathy is_ring0 / midwife / leash
                     when the op is TEST or INSTALL_ROM
```

Paths under `/home/workdir/artifacts/harness/`.

---

## 5. Open bets (not decided)

- **Karpathy:** Ring-1 density plus cheap Ring-0 scalars is enough leash for the decade.
- **Hotz:** a prompt will try to enter ROM within a year; treat as bug, not evolution.
- **Carmack:** teams will skip K-snapshots under schedule pressure; that is a missed frame.
- **Woz:** if the lamps become a dashboard, the board has too many vias.

These may be measured. They may not silently amend sections 3.x.

---

## 6. Rejected list (so it does not come back as a feature request)

Sixth actuator · planner daemon · MCP ontology · multi-agent org chart · skill runtime as a second language · LLM-as-judge writing `owned` · screenshot-as-verb · composited desktop as `fb` · “understood the UI” as an instruction · resume-from-transcript · mutable `N` mid-session · English as `test kind=pure` · Node supervisor · container orchestra · chat as home screen · Agents tab · one green light for two truths · Jobs adding verbs.

---

## 7. How to read this file

Theorems-as-design are sections 3.x and the Round ink marked as such.  
Jobs named the object and cut the glass. He did not specify the opcode.  
Lamport and Wilson initial the machine when it is written as a state machine and an ISA.  
The four operators remain in disagreement on the bets in §5. That is allowed. The crown is not.

**Bench.**  
Work here. Decide what goes home.
