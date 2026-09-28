// SPDX-License-Identifier: MIT OR Apache-2.0
// ops_line.mjs — the site's parser mirror as a batch oracle for tests/deep/fuzz_parse.py.
// stdin: a JSON array of lines. stdout: a JSON array of {kind, rule}, one per line, judged the
// way `bench check` judges a line on its own (line-long first, then Ops.line).
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const Ops = createRequire(import.meta.url)(path.join(root, "docs/assets/js/ops-check.js"));
let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (buf += d));
process.stdin.on("end", () => {
  const out = JSON.parse(buf).map((l) => {
    if (Buffer.byteLength(l) >= 511) return { kind: "parse", rule: "line-long" };
    const r = Ops.line(l);
    return { kind: r.kind, rule: r.rule || null };
  });
  process.stdout.write(JSON.stringify(out));
});
