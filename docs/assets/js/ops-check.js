/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* ops-check.js — a mirror of supervisor/main.c parse_line (and the foundation's run-time slot
   gates), for the site's playground. The binary is the authority; this file is checked against
   the ROM OPS_TABLE by tests/site/parity.mjs (make site-check). Works in a browser
   (window.BenchOps) and in node (module.exports). No dependencies. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BenchOps = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var VERBS = ["READ", "WRITE", "EXEC", "TEST", "WAIT"];
  var SUPER = ["INSTALL_ROM", "SET_LOOP", "KILL", "UNPLUG"];
  var KINDS = ["PURE", "SCALAR", "JUDGE", "VISUAL"];
  var SLOTS = ["fs", "tty", "fb", "judge", "radio"];
  var LINE_BYTES = 512, MAX_OPS = 64, MAX_ARGV = 16, T_TOOL_MS = 5000;

  function bytes(s) { return typeof TextEncoder !== "undefined" ? new TextEncoder().encode(s).length : Buffer.byteLength(s); }
  function safeRel(p) { return p.length > 0 && p[0] !== "/" && p.indexOf("..") < 0; }
  /* ASCII only, like strcasecmp: String.toUpperCase folds U+017F to "S" and U+0131 to "I",
     so "TEſT" would pass here and fail in bench (found by tests/deep/fuzz_parse.py). */
  function upper(s) { return s.replace(/[a-z]+/g, function (m) { return m.toUpperCase(); }); }

  /* split like tok(): spaces and tabs; returns {toks, rest(after n tokens)} */
  function take(s, n) {
    var toks = [], i = 0;
    while (toks.length < n) {
      while (i < s.length && (s[i] === " " || s[i] === "\t")) i++;
      if (i >= s.length) break;
      var j = i;
      while (j < s.length && s[j] !== " " && s[j] !== "\t") j++;
      toks.push(s.slice(i, j));
      i = j < s.length ? j + 1 : j;
    }
    return { toks: toks, rest: s.slice(i).replace(/^[ \t]+|[ \t]+$/g, "") };
  }

  function fault(rule, msg) { return { kind: "parse", rule: rule, msg: msg }; }
  function deny(rule, msg) { return { kind: "run", rule: rule, msg: msg }; }

  /* one line -> {kind: "blank"|"ok"|"parse"|"run", verb, rule, msg} */
  function line(raw) {
    if (raw.indexOf("\u0000") >= 0) return fault("line-nul", "NUL byte in line");
    /* cut at the first CR or LF, like strcspn(ln, "\r\n"). a regex /[\r\n].*$/ does not: "." stops
       at the next \r, so "WAIT 1\r\rx" kept a \r (found by tests/deep/fuzz_parse.py) */
    var cut = raw.search(/[\r\n]/), ln = cut < 0 ? raw : raw.slice(0, cut);
    var body = ln.replace(/^[ \t]+/, "");
    if (!body || body[0] === "#") return { kind: "blank" };
    var t = take(body, 1), verb = t.toks[0], rest = t.rest, V = upper(verb);
    if (SUPER.indexOf(V) >= 0) return fault("verb-super", V + " is supervisor; intern emitting it is a spec bug");
    if (VERBS.indexOf(V) < 0) return fault("verb-unknown", "unknown verb '" + verb.slice(0, 64) + "' (five: READ WRITE EXEC TEST WAIT)");
    var r;
    if (V === "READ" || V === "WRITE") {
      r = take(rest, 2);
      var slot = r.toks[0], path = r.toks[1];
      if (!slot || !path) return fault("shape-rw", V + " needs <slot> <path>");
      if (bytes(slot) >= 128 || bytes(path) >= 256) return fault("field-long", "field too long");
      if (!safeRel(path)) return fault("path-escape", "path escapes the world: " + path);
      if (V === "READ" && r.rest) return fault("read-payload", "READ takes no payload");
      if (V === "WRITE") {
        if (path.indexOf("hold/") !== 0 && path.indexOf("proposed/") !== 0)
          return fault("write-ring", "ring: intern writes hold/ or proposed/ only, not " + path);
        if (bytes(r.rest) >= 256) return fault("field-long", "payload too long");
      }
      if (SLOTS.indexOf(slot) < 0) return deny("slot-unknown", "deny slot=" + slot + " unknown");
      if (slot !== "fs") return deny("slot-pulled", "deny slot=" + slot + (slot === "tty" ? " no device in foundation" : " unplugged"));
      return { kind: "ok", verb: V };
    }
    if (V === "EXEC") {
      r = take(rest, 1);
      var prog = r.toks[0];
      if (!prog) return fault("exec-shape", "EXEC needs <program>");
      if (bytes(prog) >= 128) return fault("field-long", "field too long");
      if (!safeRel(prog) || prog.indexOf("tools/") !== 0 || !/\.py$/.test(prog))
        return fault("exec-prog", "EXEC runs tools/*.py only, not " + prog);
      if (bytes(r.rest) >= 256) return fault("field-long", "args too long");
      var args = r.rest ? r.rest.split(/[ \t]+/) : [];
      for (var i = 0; i < args.length; i++) if (!safeRel(args[i])) return fault("exec-arg", "arg escapes the world: " + args[i]);
      if (args.length > MAX_ARGV) return deny("exec-argc", "op=exec too many args");
      return { kind: "ok", verb: V, note: "runs " + prog + " if it exists in tools/" };
    }
    if (V === "TEST") {
      r = take(rest, 2);
      var kind = r.toks[0] ? upper(r.toks[0]) : "", tpath = r.toks[1];
      if (KINDS.indexOf(kind) < 0) return fault("test-kind", "TEST without kind (PURE SCALAR JUDGE VISUAL)");
      if (!tpath) return fault("test-shape", "TEST needs <kind> <path>");
      if (bytes(tpath) >= 256) return fault("field-long", "field too long");
      if (!safeRel(tpath) || tpath.indexOf("tests/rom/") !== 0 || !/\.py$/.test(tpath))
        return fault("test-path", "TEST runs tests/rom/*.py only, not " + tpath);
      if (r.rest) return fault("test-shape", "TEST takes <kind> <path> only");
      if (kind === "JUDGE") return deny("judge-pulled", "deny op=test kind=judge judge/radio unplugged");
      if (kind === "VISUAL") return deny("visual-pulled", "deny op=test kind=visual fb unplugged");
      return { kind: "ok", verb: V };
    }
    /* WAIT */
    r = take(rest, 1);
    var a = r.toks[0];
    if (!a) return fault("wait-shape", "WAIT needs <ms>");
    if (!/^\+?[0-9]+$/.test(a) || Number(a) > 3600000) return fault("wait-shape", "WAIT <ms> not a number: " + a);
    if (r.rest) return fault("wait-shape", "WAIT takes <ms> only");
    if (Number(a) > T_TOOL_MS) return deny("t-tool", "op=wait ms=" + Number(a) + " > T_tool=" + T_TOOL_MS);
    return { kind: "ok", verb: V };
  }

  /* a whole script, as bench would take it: parse every line first (one fault = no frames),
     then frame the ops in order until the first run-time refusal. */
  function script(text) {
    var lines = text.split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    var out = [], ops = 0, parseFault = null;
    for (var i = 0; i < lines.length; i++) {
      var res = bytes(lines[i]) >= LINE_BYTES - 1 ? fault("line-long", "line too long") : line(lines[i]);
      res.n = i + 1;
      res.text = lines[i];
      if (res.kind !== "blank" && res.kind !== "parse" && ++ops > MAX_OPS) { res = { kind: "parse", rule: "script-long", msg: "script over " + MAX_OPS + " ops", n: i + 1, text: lines[i] }; }
      out.push(res);
      if (res.kind === "parse") { parseFault = res; break; }
    }
    var frames = 0, stop = null;
    if (!parseFault) {
      for (var k = 0; k < out.length; k++) {
        var o = out[k];
        if (o.kind === "blank") continue;
        if (frames >= 8) { o.kind = "run"; o.rule = "over-n"; o.msg = "fault=over-N (N=8, --n raises it)"; }
        frames++;
        o.frame = frames;
        if (o.kind === "run") { stop = o; out = out.slice(0, k + 1); break; }
      }
    }
    return { lines: out, parseFault: parseFault, stop: stop, frames: parseFault ? 0 : frames,
             exit: parseFault ? 1 : stop ? 1 : 0 };
  }

  /* bench status --line -> fields with meaning */
  function status(text) {
    var s = text.trim(), f = s.split(/\s+/), out = [];
    if (!s) return out;
    if (f[0] === "none") {
      out.push({ k: "session", v: "none", m: "no session has run in this world yet" });
      f.slice(2).forEach(function (kv) { out.push(explain(kv)); });
      return out;
    }
    out.push({ k: "session", v: f[0], m: "the current session: <epoch>-<pid> of the run that made it" });
    var st = (f[1] || "").split(",");
    var SM = { run: "a run is framing steps now", ok: "the last run finished clean", fault: "a step was refused or failed; read its rule=",
      halt: "stopped by KILL", disarmed: "the owner's token was removed or changed mid-run", restored: "a snapshot was restored as a new session",
      crashed: "STATE says run, but nobody holds the world lock: the run died", nostate: "the session has no STATE file" };
    out.push({ k: "status", v: f[1], m: (SM[st[0]] || "unknown status") + (st[1] === "killed" ? " (a KILL file is present)" : "") });
    f.slice(2).forEach(function (kv) { out.push(explain(kv)); });
    return out;
  }

  function explain(kv) {
    var i = kv.indexOf("="), k = i < 0 ? kv : kv.slice(0, i), v = i < 0 ? "" : kv.slice(i + 1);
    var m = {
      n: "frames used / N budget for this run",
      snap: "the newest snapshot: <k>-<id>; bench verify re-hashes it",
      lamps: "lit lamps: MAIN (crowned change in main/), HOLD (work in quarantine), BLIND (fb and radio pulled)",
      hold: "hold/ growth this session in bytes / the byte quota",
      files: "hold/ growth in entries / the entry quota",
      armed: "is the owner's token present and valid right now",
      helper: "the helper version bench pinned at start",
      lock: "held = a run owns this world now; free = nobody"
    }[k] || "field";
    if (k === "hold" || k === "files") {
      var p = v.split("/"), used = parseInt(p[0], 10), q = parseInt(p[1], 10);
      if (q > 0 && !isNaN(used)) m += " — " + Math.max(0, Math.round(used * 100 / q)) + "% used";
    }
    if (k === "armed" && v === "no") m += " — the next run will refuse (exit 5)";
    return { k: k, v: v, m: m };
  }

  return { line: line, script: script, status: status, VERBS: VERBS };
});
