/* SPDX-License-Identifier: MIT OR Apache-2.0 */
/* site.js — nav toggle, verb explorer, compare filter, copy buttons. No framework, no network.
   Without JS every panel and row stays visible; this only folds and filters. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");

  /* nav: collapses under 640 px (CSS); the button opens it */
  var toggle = document.querySelector(".navtoggle");
  var nav = document.getElementById("nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* verb explorer: five tabs, one panel each */
  var explorer = document.querySelector("[data-explorer]");
  if (explorer) {
    var tabs = explorer.querySelectorAll("[role=tab]");
    var show = function (id) {
      tabs.forEach(function (t) {
        var on = t.getAttribute("aria-controls") === id;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
    };
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { show(t.getAttribute("aria-controls")); });
      t.addEventListener("keydown", function (e) {
        var d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!d) return;
        var n = tabs[(i + d + tabs.length) % tabs.length];
        n.focus();
        show(n.getAttribute("aria-controls"));
      });
    });
    if (tabs.length) show(tabs[0].getAttribute("aria-controls"));
  }

  /* compare: filter rows by layer, and by "sealed per-step snaps" */
  var cmp = document.querySelector("[data-compare]");
  if (cmp) {
    var rows = cmp.querySelectorAll("tbody tr");
    var buttons = cmp.querySelectorAll("[data-layer]");
    var sealed = cmp.querySelector("[data-sealed]");
    var count = cmp.querySelector("[data-count]");
    var layer = "all";
    var apply = function () {
      var n = 0;
      rows.forEach(function (r) {
        var ok = (layer === "all" || r.dataset.layer === layer) &&
                 (!sealed || !sealed.checked || r.dataset.sealed === "true");
        r.hidden = !ok;
        if (ok) n++;
      });
      if (count) count.textContent = n + " of " + rows.length + " shown";
    };
    buttons.forEach(function (b) {
      b.addEventListener("click", function () {
        layer = b.dataset.layer;
        buttons.forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        apply();
      });
    });
    if (sealed) sealed.addEventListener("change", apply);
    apply();
  }

  /* rules: search box + phase filter */
  var rl = document.querySelector("[data-rules]");
  if (rl) {
    var cards = rl.querySelectorAll(".rule"), q = rl.querySelector("[data-q]"),
        phases = rl.querySelectorAll("[data-phase]:not(.rule)"), rc = rl.querySelector("[data-rcount]"), ph = "all";
    var filt = function () {
      var term = (q.value || "").toLowerCase().trim(), n = 0;
      cards.forEach(function (c) {
        var ok = (ph === "all" || c.dataset.phase === ph) && (!term || c.dataset.text.toLowerCase().indexOf(term) >= 0);
        c.hidden = !ok; if (ok) n++;
      });
      rc.textContent = n + " of " + cards.length;
    };
    phases.forEach(function (b) {
      b.addEventListener("click", function () {
        ph = b.dataset.phase;
        phases.forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
        filt();
      });
    });
    q.addEventListener("input", filt);
    if (location.hash.length > 1 && document.getElementById(location.hash.slice(1))) q.value = "";
    filt();
  }

  /* home: one line into the playground */
  var tl = document.querySelector("[data-tryline]");
  if (tl) tl.addEventListener("submit", function (e) {
    e.preventDefault();
    location.href = tl.action + "#s=" + encodeURIComponent(tl.querySelector("input").value);
  });

  /* copy buttons on command blocks marked .copyable */
  document.querySelectorAll(".copyable pre").forEach(function (pre) {
    if (!navigator.clipboard) return;
    var b = document.createElement("button");
    b.type = "button";
    b.className = "copy";
    b.textContent = "Copy";
    b.addEventListener("click", function () {
      var text = pre.innerText.split("\n").map(function (l) { return l.replace(/\s+#.*$/, ""); })
        .filter(function (l) { return l.trim(); }).join("\n");
      navigator.clipboard.writeText(text).then(function () {
        b.textContent = "Copied";
        setTimeout(function () { b.textContent = "Copy"; }, 1500);
      });
    });
    pre.appendChild(b);
  });
})();
