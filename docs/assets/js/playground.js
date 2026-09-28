/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* playground.js — the script checker and status decoder on /playground/. Uses BenchOps
   (ops-check.js). Offline: no request leaves the page. */
(function () {
  "use strict";
  var Ops = window.BenchOps;
  if (!Ops) return;
  var rulesEl = document.getElementById("rules-data");
  var RULES = {};
  try { JSON.parse(rulesEl.textContent).forEach(function (r) { RULES[r.id] = r; }); } catch (e) {}
  var RULES_URL = window.BENCH_RULES_URL || "../rules/";

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  /* ---------- script checker ---------- */
  var box = document.querySelector("[data-checker]");
  if (box) {
    var ta = box.querySelector("#ops"), out = box.querySelector("[data-lines]"), verdict = box.querySelector("[data-verdict]");
    var PRESETS = {
      clean: "READ  fs main/hello.txt\nWRITE fs hold/out.txt hello from the intern\nEXEC  tools/hash.py hold/out.txt\nTEST  PURE tests/rom/test_isa.py\nWAIT  100",
      ring: "READ fs main/app.py\nWRITE fs main/app.py fixed it\nWAIT 10",
      slot: "WAIT 10\nREAD fb main/screen.png\nWAIT 10",
      shell: "EXEC tools/hash.py ../secrets\nEXEC ./build.sh\nTEST tests/rom/test_isa.py\nWAIT 1s\nBROWSE https://example.com"
    };

    var render = function () {
      var res = Ops.script(ta.value);
      out.textContent = "";
      res.lines.forEach(function (r) {
        if (r.kind === "blank") return;
        var li = el("li", "line line--" + r.kind);
        var head = el("div", "line__head");
        head.appendChild(el("span", "line__n", "line " + r.n + (r.frame ? " · frame " + r.frame : "")));
        head.appendChild(el("span", "line__tag", r.kind === "ok" ? "ok" : r.kind === "parse" ? "refused at parse" : "refused at run"));
        li.appendChild(head);
        li.appendChild(el("code", "line__text", r.text.trim()));
        if (r.rule) {
          var p = el("p", "line__rule");
          var a = el("a", null, "rule=" + r.rule);
          a.href = RULES_URL + "#" + r.rule;
          p.appendChild(a);
          var fix = RULES[r.rule] ? RULES[r.rule].fix : "";
          p.appendChild(document.createTextNode(" fix: " + fix));
          li.appendChild(p);
          li.appendChild(el("p", "line__msg", r.msg));
        } else if (r.note) {
          li.appendChild(el("p", "line__msg", r.note));
        }
        out.appendChild(li);
      });
      /* bench stops at the first parse fault; for teaching, show what the rest would hit too */
      if (res.parseFault) {
        var all = ta.value.split("\n");
        for (var i = res.parseFault.n; i < all.length; i++) {
          var r2 = Ops.line(all[i]);
          if (r2.kind === "blank") continue;
          var li2 = el("li", "line line--after");
          var h2 = el("div", "line__head");
          h2.appendChild(el("span", "line__n", "line " + (i + 1) + " · after the stop"));
          h2.appendChild(el("span", "line__tag", r2.kind === "ok" ? "would parse" : "would also be refused"));
          li2.appendChild(h2);
          li2.appendChild(el("code", "line__text", all[i].trim()));
          if (r2.rule) {
            var p2 = el("p", "line__rule"), a2 = el("a", null, "rule=" + r2.rule);
            a2.href = RULES_URL + "#" + r2.rule;
            p2.appendChild(a2);
            p2.appendChild(document.createTextNode(" fix: " + (RULES[r2.rule] ? RULES[r2.rule].fix : "")));
            li2.appendChild(p2);
          }
          out.appendChild(li2);
        }
      }
      var shown = res.lines.filter(function (r) { return r.kind !== "blank"; }).length;
      if (!shown) verdict.textContent = "Empty script: bench would start a session with no frames.";
      else if (res.parseFault) verdict.innerHTML = "<b>exit 1 before any frame.</b> A parse fault stops the whole script: no session, no snapshot.";
      else if (res.stop) verdict.innerHTML = "<b>exit 1 at frame " + res.stop.frame + ".</b> Earlier frames run and are snapped; the refused step is snapped with its rule, then the run stops.";
      else verdict.innerHTML = "<b>exit 0.</b> " + res.frames + " frame" + (res.frames === 1 ? "" : "s") + ", a sealed snapshot after each (if the tools exist and the clocks and quotas hold).";
      verdict.className = "verdict verdict--" + (res.exit ? "bad" : "ok");
    };

    var t;
    ta.addEventListener("input", function () { clearTimeout(t); t = setTimeout(render, 120); });
    box.querySelectorAll("[data-preset]").forEach(function (b) {
      b.addEventListener("click", function () { ta.value = PRESETS[b.dataset.preset]; render(); ta.focus(); });
    });

    /* share: the script travels in the URL fragment, never to a server */
    var shared = box.querySelector("[data-shared]");
    box.querySelector("[data-share]").addEventListener("click", function () {
      var url = location.href.split("#")[0] + "#s=" + encodeURIComponent(ta.value);
      history.replaceState(null, "", url);
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(function () { shared.textContent = "Link copied."; });
      else shared.textContent = "Link is in the address bar.";
    });
    box.querySelector("[data-download]").addEventListener("click", function () {
      var a = el("a");
      a.href = URL.createObjectURL(new Blob([ta.value.replace(/\n?$/, "\n")], { type: "text/plain" }));
      a.download = "touch.ops";
      document.body.appendChild(a); a.click(); a.remove();
    });
    var m = location.hash.match(/^#s=(.*)$/);
    if (m) { try { ta.value = decodeURIComponent(m[1]); } catch (e) {} }
    render();
  }

  /* ---------- status decoder ---------- */
  var dec = document.querySelector("[data-decoder]");
  if (dec) {
    var inp = dec.querySelector("#statusline"), dl = dec.querySelector("[data-fields]"), lamps = dec.querySelector("[data-lamps]");
    var draw = function () {
      var f = Ops.status(inp.value);
      dl.textContent = "";
      f.forEach(function (x) {
        dl.appendChild(el("dt", null, x.k + (x.v ? " = " + x.v : "")));
        dl.appendChild(el("dd", null, x.m));
      });
      var lit = (f.filter(function (x) { return x.k === "lamps"; })[0] || { v: "" }).v.split(",");
      lamps.textContent = "";
      [["MAIN", ""], ["HOLD", "lamp--hold"], ["BLIND", "lamp--lit"]].forEach(function (L) {
        var s = el("span");
        s.appendChild(el("i", "lamp " + (lit.indexOf(L[0]) >= 0 ? L[1] || "lamp--lit" : "")));
        s.appendChild(document.createTextNode(L[0]));
        lamps.appendChild(s);
      });
    };
    inp.addEventListener("input", draw);
    draw();
  }
})();
