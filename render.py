#!/usr/bin/env python3
"""render.py -- rend une page HTML de figure en PNG (Playwright / Chromium headless)
et contrôle la page rendue : chevauchements texte/texte, texte/logo, texte/trait,
et marges minimales.

Usage autonome :  python render.py page.html page.png --w 1118 --h 394 [--scale 3]
Utilisé aussi par graphe.py (fonction render()).
"""
import argparse
import os
import sys

from playwright.sync_api import sync_playwright

CHECK_JS = r"""
(margin) => {
  const W = document.getElementById('fig').clientWidth;
  const H = document.getElementById('fig').clientHeight;
  const items = [];
  document.querySelectorAll('#fig .t').forEach(el => {
    const r = document.createRange(); r.selectNodeContents(el);
    const b = r.getBoundingClientRect();
    // boîte d'encre approximative : on retire l'interlignage
    const fs = parseFloat(getComputedStyle(el).fontSize);
    const lh = b.height, ink = fs * 1.02, dy = (lh - ink) / 2;
    items.push({k: 't', id: el.textContent.slice(0, 40), g: el.dataset.g || '', ko: el.dataset.ko || '',
                b: [b.left, b.top + dy, b.right, b.bottom - dy]});
  });
  document.querySelectorAll('#fig img').forEach(el => {
    const b = el.getBoundingClientRect();
    items.push({k: 'i', id: el.getAttribute('alt'), g: el.dataset.g || '',
                b: [b.left, b.top, b.right, b.bottom]});
  });
  const paths = [];
  document.querySelectorAll('#fig svg .lk, #fig svg .rule').forEach(p => {
    const L = p.getTotalLength(); const pts = [];
    for (let i = 0; i <= L; i += 1) { const q = p.getPointAtLength(i); pts.push([q.x, q.y]); }
    paths.push({id: p.dataset.id || p.getAttribute('class'), pts});
  });
  const issues = [];
  const inter = (a, b, p) => a[0] < b[2] + p && b[0] < a[2] + p && a[1] < b[3] + p && b[1] < a[3] + p;
  for (let i = 0; i < items.length; i++) {
    const a = items[i];
    if (a.b[0] < margin - 0.5 || a.b[1] < margin - 0.5 || a.b[2] > W - margin + 0.5 || a.b[3] > H - margin + 0.5)
      issues.push(`marge < ${margin}px : ${a.id} ${a.b.map(v => v.toFixed(1))}`);
    for (let j = i + 1; j < items.length; j++) {
      const b = items[j];
      if (inter(a.b, b.b, 1)) issues.push(`chevauchement : « ${a.id} » / « ${b.id} »`);
    }
  }
  // une étiquette posée « sur » son trait masque celui-ci (fond blanc) : on l'exempte pour ce trait seulement
  for (const p of paths) for (const a of items) {
    if (a.ko && a.ko === p.id) continue;
    if (p.pts.some(q => q[0] > a.b[0] - 1.5 && q[0] < a.b[2] + 1.5 && q[1] > a.b[1] - 1.5 && q[1] < a.b[3] + 1.5))
      issues.push(`trait ${p.id} traverse « ${a.id} »`);
  }
  const fontOK = document.fonts.check('600 10px Inter');
  return {issues, fontOK, n: items.length, np: paths.length};
}
"""


def render(html_path, png_path, w, h, scale=3, margin=9.6):
    """Capture la page en PNG et renvoie le rapport de contrôle."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': w, 'height': h}, device_scale_factor=scale)
        page.goto('file://' + os.path.abspath(html_path))
        page.wait_for_load_state('networkidle')
        page.evaluate('document.fonts.ready')
        report = page.evaluate(CHECK_JS, margin)
        page.locator('#fig').screenshot(path=png_path, omit_background=False)
        browser.close()
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('html'); ap.add_argument('png')
    ap.add_argument('--w', type=int, required=True); ap.add_argument('--h', type=int, required=True)
    ap.add_argument('--scale', type=float, default=3)
    a = ap.parse_args()
    r = render(a.html, a.png, a.w, a.h, a.scale)
    print('police Inter :', r['fontOK'], '| textes/logos :', r['n'], '| traits :', r['np'])
    for i in r['issues']:
        print('  !', i)
    sys.exit(1 if r['issues'] else 0)
