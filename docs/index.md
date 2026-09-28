---
title: Bench
nav: home
wide: true
description: A custody kernel for agent work — five verbs, sealed snaps. Not an agent.
---
<section class="board" aria-labelledby="board-title">
  <p class="board__lamps" aria-label="Lamps as bench status shows them">
    <span><i class="lamp" aria-hidden="true"></i>MAIN</span>
    <span><i class="lamp lamp--hold" aria-hidden="true"></i>HOLD</span>
    <span><i class="lamp lamp--lit" aria-hidden="true"></i>BLIND</span>
  </p>
  <h1 id="board-title">Bench</h1>
  <p class="board__line">custody kernel — five verbs, sealed snaps. Not an agent.</p>
  <p class="status" aria-label="bench status --line">1790488197-8946 <b>ok</b> n=5/8 snap=005-79f0fe07 lamps=HOLD,BLIND hold=+0/65536 files=+1/256 armed=yes helper=v0 lock=free</p>
  <ul class="chips" aria-label="The five verbs, and nothing else">
    <li class="chip">READ</li><li class="chip">WRITE</li><li class="chip">EXEC</li><li class="chip">TEST</li><li class="chip">WAIT</li>
  </ul>
  <p>An agent loop thinks, calls a model and decides what to try. Bench is the room it works in:
  it frames each step under a clock and quotas, seals a content-hashed snapshot after every
  step, and lets only the owner crown work into the main tree. There is no model in the tree.</p>
  <div class="cta">
    <a class="btn" href="{{ '/architecture/' | relative_url }}">See the layers</a>
    <a class="btn btn--ghost" href="{{ '/start/' | relative_url }}">Clone and <code>make ledger-test</code></a>
  </div>
</section>

<form class="tryline" action="{{ '/playground/' | relative_url }}" data-tryline>
  <label class="sr" for="tryop">Try a line</label>
  <input id="tryop" class="ops ops--one" value="WRITE fs main/app.py fixed it" spellcheck="false" autocapitalize="off" autocomplete="off">
  <button class="btn" type="submit">Would bench take it?</button>
</form>

<div class="doors">
  <section class="door" aria-labelledby="door-human">
    <p class="door__who">for people</p>
    <h3 id="door-human">Run it on a Linux box</h3>
    <ul>
      <li><a href="{{ '/start/' | relative_url }}">Start</a> — clone, <code>make env &amp;&amp; make ledger-test</code>, arm, lamps</li>
      <li><a href="{{ '/playground/' | relative_url }}">Playground</a> — check a script before a run</li>
      <li><a href="{{ '/rules/' | relative_url }}">Rules</a> — what each refusal means and how to fix it</li>
    </ul>
  </section>
  <section class="door" aria-labelledby="door-agent">
    <p class="door__who">for agents</p>
    <h3 id="door-agent">Read the machine side</h3>
    <ul>
      <li><a href="{{ '/agents/' | relative_url }}">Agents</a> — grammar, session protocol, what not to do</li>
      <li><a href="{{ '/llms.txt' | relative_url }}"><code>/llms.txt</code></a> — the whole site as plain text</li>
      <li><a href="{{ '/api/index.json' | relative_url }}"><code>/api/*.json</code></a> — rules, verbs, truth table, timings</li>
    </ul>
  </section>
</div>

<h2>Who starts whom</h2>
<figure class="figure figure--scroll">
  <div class="figure__frame">
    <a class="figure__open" href="{{ '/assets/diagrams/process.svg' | relative_url }}" aria-label="Open the diagram full size">
    <picture>
      <source media="(max-width: 640px)" srcset="{{ '/assets/diagrams/process-tall.svg' | relative_url }}">
      <img src="{{ '/assets/diagrams/process.svg' | relative_url }}" width="1138" height="647"
       alt="The owner arms the token and starts bench run. The intern hands bench one of five verbs per step. Bench re-checks the token before every frame, holds sessions/LOCK for the run, talks to bench-helper over a parent-only mailbox, forks one worker child per EXEC or TEST, reads its output through a pipe, and writes a sealed snapshot, out-n and a log line after every step.">
    </picture>
    </a>
  </div>
  <p class="figure__hint">Swipe sideways to read · tap to open full size</p>
  <figcaption>The intern only hands <code>bench</code> lines of text. It has no path to the helper, the token, the lock or the log.</figcaption>
</figure>

<h2>Measured, not promised</h2>
<div class="stats">
  {% for s in site.data.perf.headline %}
  <div class="stat">
    <span class="stat__num">{{ s.value }}</span><span class="stat__unit">{{ s.unit }}</span>
    <span class="stat__label">{{ s.label }}</span>
    <span class="stat__note">{{ s.note }}</span>
  </div>
  {% endfor %}
</div>
<p class="caption">Medians on one machine: {{ site.data.perf.machine }}. Source:
<a href="{{ site.repo }}/blob/HEAD/docs/PERF_AND_MAP.md">PERF_AND_MAP.md</a> · all classes on
<a href="{{ '/measure/' | relative_url }}">Measure</a>.</p>

<div class="cols">
  <div class="card">
    <h3>Sealed after every step</h3>
    <p>Each step writes <code>snap-k/</code> — made read-only on landing, content-hashed. <code>bench verify</code> re-hashes; <code>restore</code> and <code>fork</code> check before they move anything.</p>
  </div>
  <div class="card">
    <h3>The owner holds the key</h3>
    <p>A token file arms the run and is re-checked before every frame. Remove it and the next step does not run. The intern cannot mint it.</p>
  </div>
  <div class="card">
    <h3>Refusals you can act on</h3>
    <p>Every rejection names a stable rule and a fix: <code>rule=write-ring fix: write under hold/ or proposed/</code>.</p>
  </div>
</div>
