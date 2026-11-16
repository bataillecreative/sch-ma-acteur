#!/usr/bin/env python3
"""graphe.py -- graphe d'acteurs paramétrique (HTML/CSS + SVG -> PNG).

    python graphe.py <vue> --w <px> --h <px> [options]

Lit acteurs.json (compilé par fiches.py), filtre la vue, calcule la mise en page,
écrit sorties/<vue>.html puis sorties/<vue>.png (device_scale_factor 3, fond blanc).
Voir README.md pour les options, les règles de placement et la grammaire graphique.
"""
import argparse
import html
import itertools
import json
import math
import os
import re
import sys

from PIL import Image, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOGOS = os.path.join(HERE, 'logos')
SORTIES = os.path.join(HERE, 'sorties')
FONT_DIR = '/usr/share/fonts/opentype/inter'

BLEU, ORANGE, TEXTE, GRIS, GRIS_CLAIR = '#3B38F5', '#FF5B23', '#202125', '#686870', '#C9C9D2'
COULEURS = {'bleu': BLEU, 'orange': ORANGE}

REGIMES = {'feodal': 'FÉODAL', 'hybride': 'HYBRIDE', 'bascule': 'BASCULE', 'financier': 'FINANCIER',
           'public': 'PUBLIC'}
COLS = {'feodal': 0.0, 'hybride': 1.0, 'bascule': 2.0, 'financier': 3.0}
COL_PUBLIC = 1.5
BANDES = {'public': 0, 'vehicule': 1, 'prive': 2}
BANDE_LIB = {0: 'PUBLIC', 1: 'PARTENARIAT', 2: 'PRIVÉ'}
# Sous-rangées d'une bande. Les programmes (et les nœuds d'encadrement) occupent la
# sous-rangée « extérieure » : en tête de la bande publique, en pied de la bande privée.
SR_EXT_HAUT, SR_ACTEUR, SR_EXT_BAS = 0, 1, 2

# Logos qui ne portent pas le nom de l'acteur : on écrit le nom sous le logo.
# (à remplacer par un champ « logo_avec_nom » dans les fiches)
LOGOS_SYMBOLES = {'image25.png'}

# Typographie (px CSS ; 1 pt = 1,333 px) : (taille, graisse, italique)
TY = {
    'nom': (14, 700, False), 'nom_c': (18, 700, False), 'prog': (12.5, 600, True),
    'prog_c': (15, 600, True), 'regime': (8.5, 700, False), 'categorie': (8, 600, False),
    'legende': (10, 400, False), 'verbe': (8.5, 600, False), 'detail': (10, 400, False),
    'flux': (10, 600, False), 'axe': (8, 600, False), 'rang': (8, 600, False),
}
CAPS = {'regime', 'categorie', 'verbe', 'axe', 'rang'}
LS = 0.11          # interlettrage des capitales (em)
LH = 1.25          # interligne
MARGE = 12         # marge extérieure (px) ; 0,1 po = 9,6 px
ETIQ_MAX = 175     # largeur max d'une étiquette de lien
GOUT = 18          # gouttière entre deux nœuds voisins
GOUT_LIEN = 34     # gouttière entre deux voisins liés (place pour la flèche)
FLECHE_FLUX = 11   # largeur du pictogramme de sens du flux
FONT_FILES = {(400, False): 'Inter-Regular.otf', (600, False): 'Inter-SemiBold.otf',
              (700, False): 'Inter-Bold.otf', (600, True): 'Inter-SemiBoldItalic.otf'}
_fonts = {}


# ---------------------------------------------------------------- typographie
def largeur(txt, style):
    size, wt, it = TY[style]
    if (wt, it) not in _fonts:
        _fonts[(wt, it)] = ImageFont.truetype(os.path.join(FONT_DIR, FONT_FILES[(wt, it)]), 100)
    w = _fonts[(wt, it)].getlength(txt) * size / 100
    if style in CAPS:
        w += LS * size * len(txt)
    return w * 1.02  # marge de sécurité navigateur


def hauteur(style):
    return TY[style][0] * LH


def typo(s):
    """Espaces insécables à la française."""
    if s is None:
        return None
    s = re.sub(r' ([;!?%»])', '\u202f\\1', s)
    s = re.sub(r'« ', '«\u202f', s)
    s = re.sub(r' :', '\u00a0:', s)
    s = re.sub(r'≈ ', '≈\u00a0', s)
    s = re.sub(r'(\d) (M€|Md€|€)', '\\1\u00a0\\2', s)
    s = re.sub(r'(plus de|moins de) (\d)', '\\1\u00a0\\2', s)
    s = s.replace(' · ', '\u00a0· ')  # le point médian reste en fin de ligne
    return s


def _glouton(mots, style, wmax):
    lignes, cur = [], ''
    for m in mots:
        essai = (cur + ' ' + m) if cur else m
        if cur and largeur(essai, style) > wmax:
            lignes.append(cur)
            cur = m
        else:
            cur = essai
    if cur:
        lignes.append(cur)
    return lignes


def couper(txt, style, wmax, tolerance=1.0):
    """Lignes équilibrées (pas de mot orphelin) ; une ligne unique peut déborder
    jusqu'à wmax * tolerance."""
    if largeur(txt, style) <= wmax * tolerance:
        return [txt]
    mots = txt.split(' ')
    k = len(_glouton(mots, style, wmax))
    lo, hi = 20.0, wmax
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if len(_glouton(mots, style, mid)) <= k:
            hi = mid
        else:
            lo = mid
    return _glouton(mots, style, hi)


def chiffre(det):
    """Ne garde du détail que la partie chiffrée (après « : », segments avec un chiffre)."""
    if not det:
        return None
    det = det.split(' : ')[-1]
    segs = [x for x in det.split(', ') if re.search(r'\d', x)]
    return ', '.join(segs) or None


# ---------------------------------------------------------------- données
def charger(data, vue, agreger, vehicules, contraction, liens_mode):
    noeuds = {n['id']: dict(n, ordre=i) for i, n in enumerate(data['noeuds'])}
    v = data['vues'][vue]
    centre = v.get('centre')
    V = list(v['noeuds'])
    notes = []

    # 1. agrégation dans le centre
    absorbe = {}
    if agreger and centre:
        if agreger == 'auto':   # ce que le centre DÉTIENT ou DIRIGE
            cibles = [l['vers'] for l in data['liens'] if l['de'] == centre and l['verbe'] in ('DÉTENIR', 'DIRIGER')]
        else:
            cibles = [x.strip() for x in agreger.split(',') if x.strip()]
        for c in cibles:
            if c != centre:
                absorbe[c] = centre
        V = [i for i in V if i not in absorbe]
        if absorbe:
            notes.append('agrégés dans ' + noeuds[centre]['nom'] + ' : ' + ', '.join(noeuds[i]['nom'] for i in absorbe))
    m = lambda i: absorbe.get(i, i)
    liens = [dict(l, de=m(l['de']), vers=m(l['vers'])) for l in data['liens']]
    liens = [l for l in liens if l['de'] != l['vers']]

    # 2. véhicules absents qui relient au moins deux nœuds de la vue
    if vehicules:
        for nid, n in noeuds.items():
            if n['statut'] == 'vehicule' and nid not in V and nid not in absorbe:
                vois = {l['vers'] if l['de'] == nid else l['de'] for l in liens if nid in (l['de'], l['vers'])}
                if len(vois & set(V)) >= 2:
                    V.append(nid)
                    notes.append(f"véhicule ajouté : {n['nom']}")

    # 3. liens directs
    directs = [l for l in liens if l['de'] in V and l['vers'] in V]
    paires = {frozenset((l['de'], l['vers'])) for l in directs}

    # 4. contraction A -> X -> B (X absent) quand A et B n'ont pas de lien direct
    if contraction:
        for x in noeuds:
            if x in V or x in absorbe:
                continue
            for a in [l for l in liens if l['vers'] == x and l['de'] in V]:
                for b in [l for l in liens if l['de'] == x and l['vers'] in V]:
                    if a['de'] != b['vers'] and frozenset((a['de'], b['vers'])) not in paires:
                        via = f"via {noeuds[x]['nom']}"
                        directs.append(dict(b, de=a['de'], via=via))
                        paires.add(frozenset((a['de'], b['vers'])))
                        notes.append(f"lien contracté : {a['de']} → {b['vers']} {via}")

    # 5. filtre « interface » : on masque le marché entre acteurs privés
    #    (liens orange -- cessions, locations -- entre deux acteurs privés à régime)
    if liens_mode == 'auto':
        liens_mode = 'interface' if len(V) > 10 else 'tous'
    if liens_mode == 'interface':
        marche = lambda i: (noeuds[i].get('type', 'acteur') == 'acteur' and noeuds[i]['statut'] == 'prive'
                            and noeuds[i]['regime'] is not None)
        avant = len(directs)
        directs = [l for l in directs if not (l['couleur'] == 'orange' and marche(l['de']) and marche(l['vers']))]
        if avant - len(directs):
            notes.append(f"mode interface : {avant - len(directs)} cession(s)/location(s) privé–privé masquée(s)")

    # 6. fusion des liens de même sens entre les deux mêmes nœuds
    fus = {}
    for l in directs:
        fus.setdefault((l['de'], l['vers']), []).append(l)
    L = []
    for (de, vers), ls in fus.items():
        coul = 'orange' if all(x['couleur'] == 'orange' for x in ls) else ls[0]['couleur']
        L.append({'de': de, 'vers': vers, 'couleur': coul,
                  'parts': [dict(verbe=x['verbe'], detail=x.get('detail'), flux=x.get('flux'),
                                 sens=x.get('flux_sens', 'direct'), via=x.get('via')) for x in ls],
                  'source': ' ; '.join(x['source'] for x in ls if x.get('source'))})
    N = {i: noeuds[i] for i in V}
    agreges = [noeuds[i]['nom'] for i in absorbe]
    return N, L, centre, agreges, notes, liens_mode


# ---------------------------------------------------------------- nœuds
def logo_aspect(fn):
    im = Image.open(os.path.join(LOGOS, fn))
    bb = im.getchannel('A').getbbox() if im.mode == 'RGBA' else (0, 0) + im.size
    return (bb[2] - bb[0]) / (bb[3] - bb[1])


def piece_nom(nom, st, wmax, couper_noms):
    lignes = couper(nom, st, wmax) if couper_noms else [nom]
    return ('nom', lignes, max(largeur(x, st) for x in lignes), hauteur(st) * len(lignes), st)


def mesurer(n, est_centre, legmax, agreges, W, couper_noms, legendes):
    """Pièces du nœud, empilées et centrées : (type, contenu, w, h, ...).
    acteur    : logo (ou nom en gras) + régime en capitales + légende grise
    programme : nom en italique + catégorie en capitales grises + légende grise"""
    P = []
    k = min(1.0, W / 1118)
    prog = n.get('type') == 'programme'
    if n.get('logo'):
        asp = logo_aspect(n['logo'])
        aire = 2100 * ((1 + 1.6 * k) if est_centre else 1.0)
        h = min(math.sqrt(aire / asp), (40 + 20 * k) if est_centre else 30)
        w = h * asp
        wmax = (96 + 54 * k) if est_centre else 90
        if w > wmax:
            w, h = wmax, wmax / asp
        P.append(('logo', n['logo'], w, h))
        if n['logo'] in LOGOS_SYMBOLES:
            P.append(piece_nom(n['nom'], 'nom', legmax * 1.1, couper_noms))
    else:
        st = ('prog_c' if est_centre else 'prog') if prog else ('nom_c' if est_centre else 'nom')
        P.append(piece_nom(typo(n['nom']), st, legmax * (1.6 if prog else 1.1), couper_noms and not est_centre))
    if prog and n.get('categorie'):
        lib = n['categorie'].upper()
        P.append(('categorie', lib, largeur(lib, 'categorie'), hauteur('categorie')))
    elif not prog and n['regime'] not in (None, 'public'):
        lib = REGIMES[n['regime']]
        P.append(('regime', lib, largeur(lib, 'regime'), hauteur('regime'), n['regime']))
    lignes = []
    if legendes and n.get('legende'):
        lignes = couper(typo(n['legende']), 'legende', legmax, 1.3)
    if est_centre and agreges:
        lignes += couper(typo(' · '.join(agreges)), 'legende', legmax, 1.3)
    for li in lignes:
        P.append(('legende', li, largeur(li, 'legende'), hauteur('legende')))
    return P


ESP = {('logo', 'nom'): 3, ('logo', 'regime'): 5, ('nom', 'regime'): 2, ('logo', 'legende'): 4,
       ('nom', 'legende'): 1, ('regime', 'legende'): 1, ('legende', 'legende'): 0,
       ('nom', 'categorie'): 1, ('categorie', 'legende'): 1}


def empiler(P):
    y, off, prev = 0, [], None
    for p in P:
        if prev:
            y += ESP.get((prev, p[0]), 2)
        off.append(y)
        y += p[3]
        prev = p[0]
    return off, y


# ---------------------------------------------------------------- géométrie
def quad(a, c, b, n=80):
    return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0],
             (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]) for t in (i / n for i in range(n + 1))]


def dans(p, r, pad=0):
    return r[0] - pad <= p[0] <= r[2] + pad and r[1] - pad <= p[1] <= r[3] + pad


def inter(a, b, pad=0):
    return a[0] < b[2] + pad and b[0] < a[2] + pad and a[1] < b[3] + pad and b[1] < a[3] + pad


def densifier(pts, pas=1.5):
    out = [pts[0]]
    for p, q in zip(pts, pts[1:]):
        d = math.dist(p, q)
        k = max(1, int(d / pas))
        out += [(p[0] + (q[0] - p[0]) * i / k, p[1] + (q[1] - p[1]) * i / k) for i in range(1, k + 1)]
    return out


def distances(c, vois):
    d, file = {c: 0}, [c]
    while file:
        x = file.pop(0)
        for y in sorted(vois[x]):
            if y not in d:
                d[y] = d[x] + 1
                file.append(y)
    return d


# ---------------------------------------------------------------- mise en page
def mise_en_page(N, L, centre, agreges, W, H, legmax, couper_noms, legendes, vois_tous, separer=()):
    ids = list(N)
    vois = {i: [] for i in ids}
    for l in L:
        vois[l['de']].append(l['vers'])
        vois[l['vers']].append(l['de'])
    prog = {i: N[i].get('type') == 'programme' for i in ids}

    # colonnes : régime ; public au centre ; véhicules et sans-régime au barycentre
    col = {}
    for i in ids:
        r = N[i]['regime']
        if N[i]['statut'] == 'vehicule' or r is None:
            col[i] = None
        else:
            col[i] = COL_PUBLIC if r == 'public' else COLS[r]
    flottants = [i for i in ids if col[i] is None]
    for i in flottants:
        col[i] = COL_PUBLIC
    for _ in range(30):
        for i in flottants:
            if vois[i]:
                col[i] = round(sum(col[j] for j in vois[i]) / len(vois[i]), 4)

    # bandes et sous-rangées
    bande = {i: BANDES[N[i]['statut']] for i in ids}
    sous = {}
    for i in ids:
        ext = SR_EXT_BAS if bande[i] == BANDES['prive'] else SR_EXT_HAUT
        if prog[i]:
            sous[i] = ext if bande[i] in separer else SR_ACTEUR
            continue
        entrants = [l for l in L if l['vers'] == i and bande[l['de']] == bande[i]]
        sortants = [l for l in L if l['de'] == i and bande[l['vers']] == bande[i]]
        # encadrement (hors centre) : émet vers ≥ 2 nœuds de sa bande sans rien en recevoir -> en tête de bande
        sous[i] = SR_EXT_HAUT if (i != centre and not entrants and len(sortants) >= 2) else SR_ACTEUR
    rang = {i: (bande[i], sous[i]) for i in ids}
    rangs = sorted(set(rang.values()))

    seul = {i: sum(1 for j in ids if rang[j] == rang[i]) == 1 for i in ids}
    pieces = {i: mesurer(N[i], i == centre, 230 if seul[i] else legmax, agreges, W, couper_noms, legendes)
              for i in ids}
    larg = {i: max(p[2] for p in pieces[i]) for i in ids}

    def cle(i):
        bc = [col[j] for j in vois[i]] or [col[j] for j in vois_tous.get(i, []) if j in col]
        b = sum(bc) / len(bc) if bc else col[i]
        return (0 if i == centre else 1, b, N[i]['ordre'])

    cases = {}
    for i in ids:
        cases.setdefault((rang[i], col[i]), []).append(i)
    paires_l = {frozenset((l['de'], l['vers'])) for l in L}

    idx_rang = {r: k for k, r in enumerate(rangs)}

    def cout(perm, c):
        n_ = len(perm)
        pos = {i: k for k, i in enumerate(perm)}
        tot = 0.0
        for i in perm:
            for j in vois[i]:
                if j in pos:      # lien interne : voisins adjacents, sans enjamber
                    tot += 3 * (abs(pos[i] - pos[j]) - 1)
                else:             # lien externe : côté de la colonne du voisin...
                    dc = col[j] - c
                    tot += 0.3 * abs((pos[i] - (n_ - 1) / 2) * 0.4 - dc)
                    # ... sans enjamber les voisins de case (d'autant plus grave que la cible est proche)
                    if abs(dc) > 1e-6:
                        enjambes = perm[:pos[i]] if dc < 0 else perm[pos[i] + 1:]
                        poids = sum(max(1.0, pieces[x][0][3] / 20) for x in enjambes)  # gros logo = gros obstacle
                        tot += poids / (1 + abs(idx_rang[rang[i]] - idx_rang[rang[j]]))
            if not vois[i]:
                tot += 0.1 * abs((pos[i] - (n_ - 1) / 2) * 0.4 - (cle(i)[1] - c))
        if centre in pos:
            tot += 1.5 * abs(pos[centre] - (n_ - 1) / 2)
        return tot

    for k in cases:
        base = sorted(cases[k], key=cle)
        if 1 < len(base) <= 7:
            best = min(itertools.permutations(base), key=lambda p: cout(p, k[1]))
            cases[k] = list(best)
        else:
            cases[k] = base

    lies = {frozenset((l['de'], l['vers'])) for l in L}

    def gouts(k):
        lst = cases[k]
        return [GOUT_LIEN if frozenset((a, b)) in lies else GOUT for a, b in zip(lst, lst[1:])]

    def dims(k):
        ws, gs = [larg[i] for i in cases[k]], gouts(k)
        tot = sum(ws) + sum(gs)
        if centre in cases[k]:
            idx = cases[k].index(centre)
            g = sum(ws[:idx]) + sum(gs[:idx]) + ws[idx] / 2
            return g, tot - g
        return tot / 2, tot / 2

    libs = sorted({BANDE_LIB[r[0]] for r in rangs})
    une_bande = len(libs) == 1
    x0 = MARGE if une_bande else MARGE + max(largeur(t, 'rang') for t in libs) + 18
    x1 = W - MARGE

    cvals = sorted({col[i] for i in ids})
    demi_g = {c: max(dims(k)[0] for k in cases if k[1] == c) for c in cvals}
    demi_d = {c: max(dims(k)[1] for k in cases if k[1] == c) for c in cvals}
    lo = {c: x0 + demi_g[c] for c in cvals}
    hi = {c: x1 - demi_d[c] for c in cvals}
    cmin, cmax = cvals[0], cvals[-1]
    if cmax > cmin and centre and cmin < col[centre] < cmax:
        a, b, mm, cc = lo[cmin], hi[cmax], (x0 + x1) / 2, col[centre]
        ideal = {c: (a + (c - cmin) / (cc - cmin) * (mm - a)) if c <= cc else
                 (mm + (c - cc) / (cmax - cc) * (b - mm)) for c in cvals}
    elif cmax > cmin:
        a, b = lo[cmin], hi[cmax]
        ideal = {c: a + (c - cmin) / (cmax - cmin) * (b - a) for c in cvals}
    else:
        ideal = {cmin: (lo[cmin] + hi[cmin]) / 2}
    contraintes = []
    for r in rangs:
        cs = sorted(c for (rr, c) in cases if rr == r)
        for ca, cb in zip(cs, cs[1:]):
            dmin = dims((r, ca))[1] + dims((r, cb))[0]
            fa, fb = cases[(r, ca)][-1], cases[(r, cb)][0]
            dmin += GOUT_LIEN * 1.3 if frozenset((fa, fb)) in lies else GOUT * 1.5
            contraintes.append((ca, cb, dmin))
    X = dict(ideal)
    for c in cvals:
        X[c] = max([X[c], lo[c]] + [X[a] + d for a, b2, d in contraintes if b2 == c])
    for c in reversed(cvals):
        X[c] = min([X[c], hi[c]] + [X[b2] - d for a, b2, d in contraintes if a == c])
    ok = all(X[b2] - X[a] >= d - 0.5 for a, b2, d in contraintes) and all(lo[c] - 0.5 <= X[c] for c in cvals)
    debord = set()
    for r in rangs:
        cs = sorted(c for (rr, c) in cases if rr == r)
        dem = sum(sum(dims((r, c))) for c in cs) + sum(d for a, b2, d in contraintes if a in cs and b2 in cs) \
            - sum(dims((r, a))[1] + dims((r, b2))[0] for a, b2 in zip(cs, cs[1:]))
        if dem > x1 - x0:
            debord.add(r[0])

    cx = {}
    for k, lst in cases.items():
        g, _ = dims(k)
        x = X[k[1]] - g
        for i, gg in zip(lst, gouts(k) + [0]):
            cx[i] = x + larg[i] / 2
            x += larg[i] + gg

    # vertical
    occ = {c for i, c in col.items() if N[i]['regime'] in COLS and N[i]['statut'] != 'vehicule'
           and not prog[i]}
    axe_prevu = len(occ) >= 2
    tete = {i: pieces[i][0][3] for i in ids}
    offs = {i: empiler(pieces[i]) for i in ids}
    haut = {r: max(tete[i] / 2 for i in ids if rang[i] == r) for r in rangs}
    bas = {r: max(offs[i][1] - tete[i] / 2 for i in ids if rang[i] == r) for r in rangs}
    y_axe = H - MARGE - hauteur('axe')
    ytop = MARGE + (hauteur('rang') + 6 if une_bande else 0)
    ybot = (y_axe - 12) if axe_prevu else (H - MARGE)
    total = sum(haut[r] + bas[r] for r in rangs)
    n = len(rangs)
    ecart = min((ybot - ytop - total) / (n - 1), 90) if n > 1 else 0
    reste = ybot - ytop - total - ecart * (n - 1)
    y = ytop + reste / 2
    ligne = {}
    for r in rangs:
        ligne[r] = y + haut[r]
        y += haut[r] + bas[r] + ecart

    elems, rects = [], {}
    for i in ids:
        y0 = ligne[rang[i]] - tete[i] / 2
        rs = []
        for p, o in zip(pieces[i], offs[i][0]):
            r = (cx[i] - p[2] / 2, y0 + o, cx[i] + p[2] / 2, y0 + o + p[3])
            if p[0] == 'logo':
                rr = r
            else:
                st = p[4] if p[0] == 'nom' else p[0]
                d = (hauteur(st) - TY[st][0] * 1.05) / 2
                rr = (r[0], r[1] + d, r[2], r[3] - d)
            rs.append(rr)
            elems.append((i, p, r))
        rects[i] = rs

    xcols = sorted(X.items())

    def x_de(c):
        if len(xcols) == 1:
            return xcols[0][1]
        for (ca, xa), (cb, xb) in zip(xcols, xcols[1:]):
            if ca <= c <= cb:
                return xa + (c - ca) / (cb - ca) * (xb - xa)
        (ca, xa), (cb, xb) = (xcols[0], xcols[1]) if c < xcols[0][0] else (xcols[-2], xcols[-1])
        return xa + (c - ca) * (xb - xa) / (cb - ca)

    axe = [(REGIMES[reg], x_de(c)) for reg, c in COLS.items() if c in occ] if axe_prevu else []
    rangees = []
    for b in sorted({r[0] for r in rangs}):
        r = [r for r in rangs if r[0] == b][-1]
        rangees.append((BANDE_LIB[b], ligne[r]))
    if une_bande:
        rangees = [(rangees[0][0], MARGE + hauteur('rang') / 2)]
    return dict(elems=elems, rects=rects, axe=axe, y_axe=y_axe, rangees=rangees, ok=ok, prog=prog,
                debord=debord, bandes_prog={bande[i] for i in ids if prog[i]})


# ---------------------------------------------------------------- liens et étiquettes
def router(L, M, W, H, detail_mode):
    rects = M['rects']
    obst_fixes = [r for i in rects for r in rects[i]]
    fixes_txt = []
    for lib, x in M['axe']:
        w = largeur(lib, 'axe')
        fixes_txt.append((x - w / 2 - 4, M['y_axe'] - 2, x + w / 2 + 4, M['y_axe'] + hauteur('axe') + 2))
    for lib, y in M['rangees']:
        fixes_txt.append((MARGE, y - 7, MARGE + largeur(lib, 'rang'), y + 7))

    def centre_tete(i):
        r = rects[i][0]
        return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)

    def couper_aux_noeuds(pts, a, b, pad=5):
        n = len(pts)
        da = [k for k in range(n * 2 // 3) if any(dans(pts[k], r, pad) for r in rects[a])]
        db = [k for k in range(n // 3, n) if any(dans(pts[k], r, pad) for r in rects[b])]
        s = (max(da) + 1) if da else 0
        e = (min(db) - 1) if db else n - 1
        return pts[s:e + 1]

    traces = []
    for l in L:
        a, b = l['de'], l['vers']
        pa, pb = centre_tete(a), centre_tete(b)
        autres = [r for i in rects if i not in (a, b) for r in rects[i]]
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        d = math.hypot(dx, dy) or 1
        nx, ny = -dy / d, dx / d
        choix = None
        for k in (0, 26, -26, 46, -46, 70, -70, 100, -100, 130, -130):
            c = ((pa[0] + pb[0]) / 2 + nx * k * 2, (pa[1] + pb[1]) / 2 + ny * k * 2)
            pts = couper_aux_noeuds(quad(pa, c, pb, 120), a, b)
            if len(pts) < 3:
                continue
            if not any(dans(p, r, 4) for p in densifier(pts, 2) for r in autres + fixes_txt):
                choix = pts
                break
        if choix is None:
            choix = couper_aux_noeuds(quad(pa, ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), pb, 120), a, b)
            print(f"  ? lien {a}→{b} : pas de tracé libre", file=sys.stderr)
        traces.append(choix)

    etiq_max_ = min(ETIQ_MAX, W * 0.25)

    def lignes_etiq(l, emax=None):
        """Lignes de segments (style, texte). Le flux devient un segment ('flux', montant, sens)."""
        etiq_max = emax or etiq_max_
        out = []
        for p in l['parts']:
            det = chiffre(p['detail']) if detail_mode == 'chiffre' else p['detail']
            if p.get('via') and detail_mode != 'chiffre':
                det = (det + ', ' if det else '') + p['via']
            det = typo(det) if det else None
            ligne = [('verbe', p['verbe'])]
            w = largeur(p['verbe'], 'verbe')
            if det:
                if w + 5 + largeur(det, 'detail') <= etiq_max:
                    ligne.append(('detail', det))
                    w += 5 + largeur(det, 'detail')
                else:
                    out.append(ligne)
                    for li in couper(det, 'detail', etiq_max):
                        out.append([('detail', li)])
                    ligne, w = None, 0
            if p.get('flux'):
                fl = ('flux', typo(p['flux']), p['sens'])
                wf = FLECHE_FLUX + 3 + largeur(fl[1], 'flux')
                if ligne is not None and w + 6 + wf <= etiq_max:
                    ligne.append(fl)
                else:
                    if ligne is not None:
                        out.append(ligne)
                    ligne = [fl]
            if ligne:
                out.append(ligne)
        return out

    def larg_seg(s):
        if s[0] == 'flux':
            return FLECHE_FLUX + 3 + largeur(s[1], 'flux')
        return largeur(s[1], s[0])

    def dim_lignes(ls):
        ws, hs = [], []
        for li in ls:
            ws.append(sum(larg_seg(s) for s in li) + 6 * (len(li) - 1))
            hs.append(max(hauteur(s[0]) for s in li) + 1.5)
        return max(ws), hs

    lignes_traits = [densifier(t, 2) for t in traces]
    places = []
    longueur = lambda t: sum(math.dist(p, q) for p, q in zip(t, t[1:]))
    ordre = sorted(range(len(L)), key=lambda k: (longueur(traces[k]), k))
    etiq = [None] * len(L)
    ts = [0.5] + [0.5 + s_ * k * 0.04 for k in range(1, 10) for s_ in (-1, 1)]
    def placer(k, places, compter=False):
        best, bestpen, libres = None, 1e9, 0
        variantes = []
        for emax in (None, 95, 60):
            ls = lignes_etiq(L[k], emax)
            if not any(ls == v[0] for v in variantes):
                variantes.append((ls, 0.25 * len(variantes)))
        for ls, pv in variantes:
          if bestpen < 1 and not compter:
            break
          w, hs = dim_lignes(ls)
          h = sum(hs)
          pts = traces[k]
          for g in (4, 9, 16, 26):
              for t in ts:
                  j = min(len(pts) - 2, max(0, int(t * (len(pts) - 1))))
                  p, q = pts[j], pts[j + 1]
                  plat = abs(q[0] - p[0]) >= abs(q[1] - p[1])
                  A_ = {
                      'dessus': ('c', (p[0] - w / 2, p[1] - g - h)),
                      'dessous': ('c', (p[0] - w / 2, p[1] + g)),
                      'droite': ('l', (p[0] + g, p[1] - h / 2)),
                      'gauche': ('r', (p[0] - g - w, p[1] - h / 2)),
                      'dessus-droite': ('l', (p[0] + g, p[1] - g - h)),
                      'dessus-gauche': ('r', (p[0] - g - w, p[1] - g - h)),
                      'dessous-droite': ('l', (p[0] + g, p[1] + g)),
                      'dessous-gauche': ('r', (p[0] - g - w, p[1] + g)),
                  }
                  ordre_a = (['dessus', 'dessous', 'dessus-droite', 'dessus-gauche', 'dessous-droite', 'dessous-gauche',
                              'droite', 'gauche'] if plat else
                             ['droite', 'gauche', 'dessus-droite', 'dessous-gauche', 'dessus-gauche', 'dessous-droite',
                              'dessus', 'dessous'])
                  A_['sur'] = ('c', (p[0] - w / 2, p[1] - h / 2))
                  # « sur » le trait : seulement si le trait reste bien visible de part et d'autre
                  sur_ok = g == 4 and longueur(pts) >= math.hypot(w, h) + 50
                  for rank, nom in enumerate(ordre_a + (['sur'] if sur_ok else [])):
                      al, (rx, ry) = A_[nom]
                      r = (rx, ry, rx + w, ry + h)
                      pen = 0
                      if r[0] < MARGE or r[1] < MARGE or r[2] > W - MARGE or r[3] > M['y_axe'] - 4:
                          pen += 100
                      pen += 50 * sum(inter(r, o, 3) for o in obst_fixes + fixes_txt)
                      pen += 50 * sum(inter(r, o, 4) for o in places)
                      pen += 50 * sum(any(dans(z, r, 3) for z in lt)
                                      for kk, lt in enumerate(lignes_traits) if not (nom == 'sur' and kk == k))
                      pen += abs(t - 0.5) * 0.6 + g / 60 + rank * 0.03 + pv
                      if nom == 'sur':   # dernier recours : le trait s'interrompt sous l'étiquette
                          pen += 8 + abs(t - 0.5) * 6
                      if pen < 1 + pv:
                          libres += 1
                      if pen < bestpen:
                          ang = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
                          best, bestpen = (r, al, ls, hs, ang, nom == 'sur'), pen
        return best, bestpen, libres

    # les liens les moins libres sont étiquetés d'abord
    liberte = {k: placer(k, [], True)[2] for k in range(len(L))}
    ordre = sorted(range(len(L)), key=lambda k: (liberte[k], longueur(traces[k]), k))
    for k in ordre:
        best, bestpen, _ = placer(k, places)
        if bestpen >= 50:
            print(f"  ? étiquette {L[k]['de']}→{L[k]['vers']} : pas de place libre", file=sys.stderr)
            if os.environ.get('GRAPHE_DEBUG'):
                r = best[0]
                print('    boîte', [round(v) for v in r], 'noeuds', [i for i in rects if any(inter(r, o, 3) for o in rects[i])],
                      'étiquettes', sum(inter(r, o, 4) for o in places),
                      'traits', [f"{L[kk]['de']}→{L[kk]['vers']}" for kk, lt in enumerate(lignes_traits) if any(dans(z, r, 3) for z in lt)],
                      'w,h', round(w), round(h), file=sys.stderr)
        etiq[k] = best
        places.append(best[0])
    return traces, etiq


# ---------------------------------------------------------------- HTML
def esc(s):
    return html.escape(s, quote=True)


def html_page(N, L, M, traces, etiq, W, H):
    out = []
    A = out.append
    css_txt = ''.join(
        f".{k}{{font-size:{v[0]}px;font-weight:{v[1]};font-style:{'italic' if v[2] else 'normal'}}}\n"
        for k, v in TY.items())
    A('<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>graphe</title><style>')
    A(f"""html,body{{margin:0;padding:0;background:#fff}}
#fig{{position:relative;width:{W}px;height:{H}px;overflow:hidden;background:#fff;
 font-family:'Inter',sans-serif;color:{TEXTE};-webkit-font-smoothing:antialiased;text-rendering:geometricPrecision}}
#fig svg.liens{{position:absolute;left:0;top:0}}
.t{{position:absolute;white-space:nowrap;line-height:{LH};margin:0}}
.c{{transform:translateX(-50%);text-align:center}}
{css_txt}.regime,.categorie,.verbe,.axe,.rang{{letter-spacing:{LS}em}}
.legende,.detail,.categorie,.axe,.rang{{color:{GRIS}}}
.nom_c,.prog_c{{letter-spacing:-0.01em}}
.flux{{color:{TEXTE}}}
.fl{{display:inline-block;vertical-align:-1px;margin-right:3px}}
img{{position:absolute;display:block}}
</style></head><body><div id="fig">""")
    A(f'<svg class="liens" width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">')
    A('<defs>')
    for nom, c in COULEURS.items():
        A(f'<marker id="fl-{nom}" viewBox="0 0 8 8" refX="7.6" refY="4" markerWidth="7" markerHeight="7" '
          f'markerUnits="userSpaceOnUse" orient="auto"><path d="M0,0.6 L8,4 L0,7.4 z" fill="{c}"/></marker>')
    A('</defs>')
    for l, pts in zip(L, traces):
        c = COULEURS[l['couleur']]
        d = 'M' + ' L'.join(f'{x:.2f},{y:.2f}' for x, y in pts)
        tip = f"{N[l['de']]['nom']} → {N[l['vers']]['nom']} : " + ' ; '.join(
            p['verbe'] + (' ' + p['detail'] if p['detail'] else '') + (' {' + p['flux'] + '}' if p['flux'] else '')
            + (' ' + p['via'] if p.get('via') else '') for p in l['parts']) + (f" ({l['source']})" if l['source'] else '')
        A(f'<path class="lk" data-id="{l["de"]}→{l["vers"]}" d="{d}" fill="none" stroke="{c}" '
          f'stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#fl-{l["couleur"]})">'
          f'<title>{esc(tip)}</title></path>')
    for l, e in zip(L, etiq):
        if e[5]:
            r = e[0]
            A(f'<rect class="ko" data-id="{l["de"]}→{l["vers"]}" x="{r[0] - 3:.2f}" y="{r[1] - 1:.2f}" '
              f'width="{r[2] - r[0] + 6:.2f}" height="{r[3] - r[1] + 2:.2f}" fill="#fff"/>')
    ya = M['y_axe'] + hauteur('axe') / 2
    ax = M['axe']
    for (la, xa), (lb, xb) in zip(ax, ax[1:]):
        xa2, xb2 = xa + largeur(la, 'axe') / 2 + 8, xb - largeur(lb, 'axe') / 2 - 8
        if xb2 > xa2:
            A(f'<line class="rule" x1="{xa2:.1f}" y1="{ya:.1f}" x2="{xb2:.1f}" y2="{ya:.1f}" '
              f'stroke="{GRIS_CLAIR}" stroke-width="0.8"/>')
    A('</svg>')

    for i, p, r in M['elems']:
        cx = (r[0] + r[2]) / 2
        g = f' data-g="{i}"'
        if p[0] == 'logo':
            A(f'<img alt="{esc(N[i]["nom"])}"{g} src="../logos/{p[1]}" '
              f'style="left:{r[0]:.2f}px;top:{r[1]:.2f}px;width:{p[2]:.2f}px;height:{p[3]:.2f}px">')
        elif p[0] == 'nom':
            for kk, li in enumerate(p[1]):
                A(f'<div class="t c {p[4]}"{g} style="left:{cx:.2f}px;top:{r[1] + kk * hauteur(p[4]):.2f}px">{esc(li)}</div>')
        elif p[0] == 'regime':
            col = ORANGE if p[4] == 'bascule' else BLEU
            A(f'<div class="t c regime"{g} style="left:{cx:.2f}px;top:{r[1]:.2f}px;color:{col}">{esc(p[1])}</div>')
        else:
            A(f'<div class="t c {p[0]}"{g} style="left:{cx:.2f}px;top:{r[1]:.2f}px">{esc(p[1])}</div>')

    for l, e in zip(L, etiq):
        r, align, ls, hs, ang, sur = e
        c = COULEURS[l['couleur']]
        y = r[1]
        for li, hh in zip(ls, hs):
            spans = []
            for s in li:
                if s[0] == 'verbe':
                    spans.append(f'<span class="verbe" style="color:{c}">{esc(s[1])}</span>')
                elif s[0] == 'detail':
                    spans.append(f'<span class="detail">{esc(s[1])}</span>')
                else:  # flux : pictogramme orienté dans le sens de l'argent + montant
                    a_ = ang + (180 if s[2] == 'inverse' else 0)
                    fl = (f'<svg class="fl" width="{FLECHE_FLUX}" height="9" viewBox="-5.5 -4.5 11 9">'
                          f'<g transform="rotate({a_:.1f})"><line x1="-4.6" y1="0" x2="2.6" y2="0" stroke="{TEXTE}" '
                          f'stroke-width="1.1"/><path d="M1.2,-2.6 L4.8,0 L1.2,2.6 z" fill="{TEXTE}"/></g></svg>')
                    spans.append(f'<span class="flux">{fl}{esc(s[1])}</span>')
            inner = '<span style="display:inline-block;width:6px"></span>'.join(spans)
            if align == 'l':
                pos, cls = f'left:{r[0]:.2f}px', 't'
            elif align == 'r':
                pos, cls = f'right:{W - r[2]:.2f}px;text-align:right', 't'
            else:
                pos, cls = f'left:{(r[0] + r[2]) / 2:.2f}px', 't c'
            ko = f' data-ko="{l["de"]}→{l["vers"]}"' if sur else ''
            A(f'<div class="{cls}"{ko} style="{pos};top:{y:.2f}px;line-height:{hh:.2f}px;font-size:10px">{inner}</div>')
            y += hh

    for lib, x in M['axe']:
        A(f'<div class="t c axe" style="left:{x:.2f}px;top:{M["y_axe"]:.2f}px">{esc(lib)}</div>')
    for lib, y in M['rangees']:
        A(f'<div class="t rang" style="left:{MARGE}px;top:{y - hauteur("rang") / 2:.2f}px">{esc(lib)}</div>')
    A('</div></body></html>')
    return '\n'.join(out)


# ---------------------------------------------------------------- programme principal
def main():
    global REGIMES
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('vue')
    ap.add_argument('--w', type=int, required=True, help='largeur en px CSS (96 px = 1 po)')
    ap.add_argument('--h', type=int, required=True, help='hauteur en px CSS')
    ap.add_argument('--agreger', nargs='?', const='auto', default=None,
                    help="absorber des nœuds dans le centre : sans valeur, ce que le centre DÉTIENT ou DIRIGE ; "
                         "ou une liste d'id séparés par des virgules")
    ap.add_argument('--liens', choices=['auto', 'tous', 'interface'], default='auto',
                    help="interface : masque les cessions/locations entre acteurs privés (auto : au-delà de 10 nœuds)")
    ap.add_argument('--detail', choices=['auto', 'complet', 'chiffre'], default='auto',
                    help="chiffre : ne garder que la partie chiffrée du détail (auto : chiffre au-delà de 8 nœuds ou de 1 lien pour 40 000 px²)")
    ap.add_argument('--legendes', choices=['auto', 'oui', 'non'], default='auto',
                    help="légendes grises des nœuds (auto : non au-delà de 12 nœuds ; le centre garde la sienne)")
    ap.add_argument('--sans-vehicules', action='store_true', help="ne pas ajouter les véhicules absents de la vue")
    ap.add_argument('--sans-contraction', action='store_true', help="ne pas contracter A→X→B")
    ap.add_argument('--legende-max', type=int, default=130, help="largeur max des légendes (px)")
    ap.add_argument('--sortie', default=None, help="nom de base des fichiers (défaut : la vue)")
    ap.add_argument('--scale', type=float, default=3, help="device_scale_factor du PNG")
    a = ap.parse_args()

    data = json.load(open(os.path.join(HERE, 'acteurs.json'), encoding='utf-8'))
    REGIMES = dict(REGIMES, **data.get('regimes', {}))
    if a.vue not in data['vues']:
        sys.exit(f"vue inconnue « {a.vue} » ; vues : {', '.join(data['vues'])}")
    if a.w < 800:   # figure étroite (colonne de diapo) : noms un peu plus petits
        TY['nom'], TY['nom_c'] = (13, 700, False), (16, 700, False)
    vois_tous = {}
    for l in data['liens']:
        vois_tous.setdefault(l['de'], []).append(l['vers'])
        vois_tous.setdefault(l['vers'], []).append(l['de'])
    N, L, centre, agreges, notes, mode = charger(data, a.vue, a.agreger, not a.sans_vehicules,
                                                 not a.sans_contraction, a.liens)
    dense = len(N) > 8 or (L and a.w * a.h / len(L) < 40000)
    detail = a.detail if a.detail != 'auto' else ('chiffre' if dense else 'complet')
    legendes = a.legendes == 'oui' or (a.legendes == 'auto' and len(N) <= 12)

    lm = a.legende_max
    essais = [(lm, False), (lm - 10, False), (lm - 20, False), (lm, True), (lm - 20, True), (lm - 40, True)]
    if a.w < 800:   # figure étroite : on coupe d'emblée les noms longs (hors centre)
        essais = [(lm - 20, True), (lm - 40, True)]
    separer = set(BANDES.values())   # programmes sur la sous-rangée extérieure de leur bande
    for legmax, cn in essais:
        while True:
            M = mise_en_page(N, L, centre, agreges, a.w, a.h, legmax, cn, legendes, vois_tous, separer)
            nouv = (M['debord'] & M['bandes_prog']) - separer
            if M['ok'] or not nouv:
                break
            separer |= nouv
        if M['ok']:
            break
    if not M['ok']:
        print('  ? largeur insuffisante : chevauchements possibles entre colonnes', file=sys.stderr)
    traces, etiq = router(L, M, a.w, a.h, detail)
    os.makedirs(SORTIES, exist_ok=True)
    base = os.path.join(SORTIES, a.sortie or a.vue)
    with open(base + '.html', 'w', encoding='utf-8') as f:
        f.write(html_page(N, L, M, traces, etiq, a.w, a.h))
    for n_ in notes:
        print('  ·', n_)
    print(f"  · {len(N)} nœuds, {len(L)} liens ; liens {mode}, détail {detail}, légendes {'oui' if legendes else 'non'}, "
          f"légendes ≤ {legmax}px, noms coupés {'oui' if cn else 'non'}, "
          f"programmes à part : {', '.join(BANDE_LIB[b] for b in sorted(separer)) or 'non'}")
    sys.path.insert(0, HERE)
    from render import render
    rep = render(base + '.html', base + '.png', a.w, a.h, a.scale)
    print(f"  · {os.path.relpath(base, HERE)}.png (police Inter : {rep['fontOK']})")
    for i in rep['issues']:
        print('  !', i)
    return 0 if not rep['issues'] else 1


if __name__ == '__main__':
    sys.exit(main())
