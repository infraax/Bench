#!/bin/sh
# The file:line references behind each idea in the 2026-09-28 ranking, re-derived from the pinned clones.
#   sh research/evidence.sh [clones_dir]      # default research/clones (run research/fetch.sh first)
C=${1:-$(cd "$(dirname "$0")" && pwd)/clones}
cd "$C" || exit 1
show() { echo; echo "=== $1"; }

show "mini-swe-agent: whole loop in one file, step + cost limits"
wc -l mini-swe-agent/src/minisweagent/agents/default.py
grep -nE "step_limit|cost_limit|LimitsExceeded" mini-swe-agent/src/minisweagent/agents/default.py | head -6

show "SWE-agent: edit rejected when it adds lint errors, original shown back"
grep -nE "flake8|Your proposed edit has introduced|original" SWE-agent/tools/windowed_edit_linting/bin/edit | head -6

show "Pi: small tool set, output truncation bounds"
ls badlogic_pi-mono/packages/coding-agent/src/core/tools
grep -nE "DEFAULT_MAX_(LINES|BYTES)" badlogic_pi-mono/packages/coding-agent/src/core/tools/truncate.ts

show "deepagents: large tool results moved to files, pointer left in context"
grep -rnE "large_tool_results" langchain-ai_deepagents/libs/deepagents/deepagents/middleware/_overflow_clip.py | head -4
grep -nE "tool_token_limit_before_evict: int" langchain-ai_deepagents/libs/deepagents/deepagents/middleware/filesystem.py | head -2

show "Prime Agent: evidence-backed, reversible harness refinement"
sed -n 1,20p PrimeIntellect-ai_prime-agent/packages/coding-agent/skills/refine/SKILL.md

show "Hermes: skill curator — archive, never delete"
sed -n 1,8p NousResearch_hermes-agent/agent/curator.py

show "Omnigent: policy = ALLOW / DENY / ASK + reason, fail closed"
grep -nE '"ALLOW" \| "DENY" \| "ASK"|fail-closed' omnigent-ai_omnigent/omnigent/policies/function.py | head -4

show "Inspect AI: limits and approval as first-class objects"
grep -nE "^def (token|message|time|working|cost)_limit" inspect_ai/src/inspect_ai/util/_limit.py
ls inspect_ai/src/inspect_ai/approval

show "OpenEnv: reset / step / state environment interface"
grep -nE "def (reset|step|state)\(" meta-pytorch_OpenEnv/src/openenv/harbor/environment.py

show "gemini-cli: checkpoints in an isolated shadow git repo"
grep -nE "shadow" gemini-cli/packages/core/src/services/gitService.ts | head -4

show "Codex: agent-metadata paths kept read-only inside writable roots"
grep -nE 'append_default_read_only_project_root_subpath_if_no_explicit_rule' codex/codex-rs/protocol/src/permissions.rs | head -3

show "sandbox-runtime: model-facing reason attached to a denial"
grep -nE "model-facing reason" sandbox-runtime/src/sandbox/sandbox-config.ts | head -2

show "qwen-code: git worktrees for parallel sessions"
ls QwenLM_qwen-code/packages/cli/src/startup/worktreeStartup.ts

show "aider: commit after every edit"
grep -nE "auto_commits=True" aider/aider/coders/base_coder.py | head -2
