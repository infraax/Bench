# Bench

**A custody kernel for agent work — not an agent.** Bench hands an unreliable worker (the
*intern*) five verbs — `READ` `WRITE` `EXEC` `TEST` `WAIT` — runs each as a framed step under a
clock and quotas, keeps a sealed, content-hashed snapshot after every step, and lets only the
owner crown anything into the main tree. The loop that drives the intern, and any model, live
outside it.

Linux only · C11 + Python 3.10 stdlib · offline tests · MIT OR Apache-2.0

```
make env && make ledger-test     # machine card, then the full gate into the ledger
```

## Start here

| | |
|---|---|
| [README](https://github.com/infraax/Bench/blob/HEAD/README.md) | what it is, install, one run, the two graphs |
| [Architecture](architecture.md) | custody vs loop, the frame step by step, rings and the crown ([with rendered graphs on GitHub](https://github.com/infraax/Bench/blob/HEAD/docs/architecture.md)) |
| [Handbook](handbook.md) | owner commands, exit codes, reading a fault |
| [Reference](reference.md) | full behavior: quotas, snapshots, workers, mailbox |
| [Compare](compare.md) | where Bench sits among agent harnesses (layers, not brands) |
| [CI](ci.md) | what hosted CI proves, what only the ledger proves |
| [Agent sessions](agent.md) | how an agent session starts and reports |
| [Toolbox](TOOLBOX.md) | the tools the intern may use, and how a new one is crowned |

## More

- [Roadmap](EVOLUTION.md) · [Development plan](DEVELOPMENT_PLAN.md) · [Perf and map](PERF_AND_MAP.md) · [Test budget](TEST_BUDGET.md) · [Release](RELEASE.md)
- [Spec](https://github.com/infraax/Bench/blob/HEAD/spec/BENCH_SPEC.md) (frozen meaning)
- [History and research](https://github.com/infraax/Bench/tree/HEAD/docs/history) (session notes, the 22-harness audit)
- License: [LICENSE](https://github.com/infraax/Bench/blob/HEAD/LICENSE) · [MIT](https://github.com/infraax/Bench/blob/HEAD/LICENSE-MIT) · [Apache-2.0](https://github.com/infraax/Bench/blob/HEAD/LICENSE-APACHE) · [NOTICE](https://github.com/infraax/Bench/blob/HEAD/NOTICE) · [Third party](https://github.com/infraax/Bench/blob/HEAD/THIRD_PARTY.md)
- [Security](https://github.com/infraax/Bench/blob/HEAD/SECURITY.md) · [Repository](https://github.com/infraax/Bench)
