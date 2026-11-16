#!/usr/bin/env python3
"""Construit site/index.html : page autonome (données + logos embarqués) à partir de acteurs.json.

    python fiches.py && python site/build.py
"""
import base64, io, json, os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
data = json.load(open(os.path.join(ROOT, "acteurs.json"), encoding="utf8"))
logos = {}
for n in data["noeuds"]:
    f = n.get("logo")
    if f and f not in logos:
        im = Image.open(os.path.join(ROOT, "logos", f)).convert("RGBA")
        im.thumbnail((420, 420))
        buf = io.BytesIO(); im.save(buf, "PNG", optimize=True)
        logos[f] = {"src": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(), "ratio": im.width / im.height}
data["logos"] = logos
tpl = open(os.path.join(HERE, "template.html"), encoding="utf8").read()
out = tpl.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
open(os.path.join(HERE, "index.html"), "w", encoding="utf8").write(out)
print(f"site/index.html : {len(out)/1024:.0f} Ko, {len(data['noeuds'])} fiches, {len(data['liens'])} connexions")
