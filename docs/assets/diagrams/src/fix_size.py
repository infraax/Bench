# SPDX-License-Identifier: MIT OR Apache-2.0
"""Give each rendered diagram an intrinsic size: mermaid-cli writes width="100%" and a max-width
style, so inside <img> a browser falls back to ~300 px. Set width/height from the viewBox."""
import re
import sys

for path in sys.argv[1:]:
    s = open(path).read()
    head = s[:s.index(">") + 1]
    vb = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([\d.]+) ([\d.]+)"', head)
    if not vb:
        continue
    w, h = round(float(vb.group(3))), round(float(vb.group(4)))
    new = re.sub(r'\swidth="[^"]*"', "", head)
    new = re.sub(r'\sheight="[^"]*"', "", new)
    new = re.sub(r'\sstyle="[^"]*"', "", new)
    new = new.replace("<svg", f'<svg width="{w}" height="{h}"', 1)
    open(path, "w").write(new + s[len(head):])
    print(path, w, h)
