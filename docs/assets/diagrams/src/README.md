# Diagram sources

The site shows pre-rendered SVGs (`../*.svg`) so phones see a picture without any diagram JS.
The Mermaid sources here mirror the blocks in `README.md` and `docs/architecture.md`; edit those
first, copy the block here, then regenerate with mermaid-cli (a dev tool, not vendored):

```
npx -y @mermaid-js/mermaid-cli@11 -c config.json -b '#2a2621' -i process.mmd -o ../process.svg
```

After rendering, `python3 fix_size.py ../*.svg` sets each SVG's width/height from its viewBox
(mermaid writes `width="100%"`, which leaves an `<img>` with no intrinsic size).

`config.json` holds the site palette and turns HTML labels off (plain SVG text renders inside
`<img>` everywhere). This folder is excluded from the site build.
