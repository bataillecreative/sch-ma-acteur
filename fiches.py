#!/usr/bin/env python3
"""Compile les fiches acteurs (fiches/*.md) et les vues (vues.yaml) en acteurs.json, lu par graphe.py.

Une fiche = un acteur : en-tête YAML (id, nom, logo, statut, régime, légende, connexions) + texte libre.
Deux sortes de fiches : fiches/acteurs/ (type acteur) et fiches/programmes/ (politiques publiques,
véhicules communs, programmes d'enseigne, opérations).
Une connexion s'écrit sur une ligne :   VERBE cible : détail {flux financier} (Source, année)
    ex.  CÉDER icade : 10 sites {39 M€} (Icade et Casino, 2025)
Détail, flux et source sont facultatifs. La couleur se déduit du verbe ; le sens du flux aussi
(par défaut l'argent suit la flèche ; pour CÉDER et LOUER il va en sens inverse) : voir verbes.yaml.
"""
import glob, json, os, re, sys
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
STAT = {"privé": "prive", "public": "public", "véhicule": "vehicule"}
REG = {"féodal": "feodal", "hybride": "hybride", "bascule": "bascule", "financier": "financier", "public": "public", None: None}
LIGNE = re.compile(r"^(?P<verbe>[A-ZÀÂÇÉÈÊËÎÏÔÛÙÜ' -]+?)\s+(?P<vers>[a-z0-9_]+)\s*:?\s*(?P<reste>.*)$")


def lire(path):
    txt = open(path, encoding="utf8").read()
    m = re.match(r"---\n(.*?)\n---\n?(.*)", txt, re.S)
    if not m:
        sys.exit(f"{path} : en-tête YAML manquant")
    return yaml.safe_load(m.group(1)), m.group(2)


def connexion(de, s):
    m = LIGNE.match(s.strip())
    if not m:
        sys.exit(f"{de} : connexion illisible « {s} » (attendu : VERBE cible : détail (Source, année))")
    reste, source = (m.group("reste") or "").strip(), None
    src = re.search(r"\(([^()]*(?:\d{4}|s\.d\.)[^()]*)\)\s*$", reste)
    if src:
        source, reste = src.group(1), reste[:src.start()].strip()
    flux = re.search(r"\{([^{}]*)\}", reste)
    if flux:
        reste = (reste[:flux.start()] + reste[flux.end():]).strip(" ,")
        reste = re.sub(r"\s{2,}", " ", reste)
    return {"de": de, "vers": m.group("vers"), "verbe": m.group("verbe").strip(), "detail": reste or None, "source": source,
            "flux": flux.group(1).strip() if flux else None}


def compiler():
    V = yaml.safe_load(open(os.path.join(HERE, "verbes.yaml")))
    orange, inverse = set(V["orange"]), set(V.get("flux_inverse", []))
    noeuds, liens = [], []
    for p in sorted(glob.glob(os.path.join(HERE, "fiches", "*", "*.md"))):
        fm, corps = lire(p)
        noeuds.append({"texte": corps.strip(), "id": fm["id"], "nom": fm["nom"], "type": fm.get("type", "acteur"), "categorie": fm.get("catégorie"),
                       "logo": fm.get("logo"), "statut": STAT[fm["statut"]],
                       "regime": REG[fm.get("régime")], "role": fm.get("rôle"), "galaxie": fm.get("galaxie"), "tete": bool(fm.get("tête")), "nom_sous_logo": bool(fm.get("nom_sous_logo")), "legende": fm.get("légende", "")})
        for s in fm.get("connexions") or []:
            l = connexion(fm["id"], s)
            l["couleur"] = "orange" if l["verbe"] in orange else "bleu"
            if l["flux"]:
                l["flux_sens"] = "inverse" if l["verbe"] in inverse else "direct"
            liens.append(l)
    ids = {n["id"] for n in noeuds}
    for l in liens:
        if l["vers"] not in ids:
            sys.exit(f"connexion {l['de']} → {l['vers']} : aucune fiche « {l['vers']} »")
    vues = yaml.safe_load(open(os.path.join(HERE, "vues.yaml")))
    for v, d in vues.items():
        manq = [i for i in d["noeuds"] if i not in ids]
        if manq:
            sys.exit(f"vue {v} : fiches absentes {manq}")
    out = {"noeuds": noeuds, "liens": liens, "vues": vues}
    json.dump(out, open(os.path.join(HERE, "acteurs.json"), "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"{len(noeuds)} fiches, {len(liens)} connexions, {len(vues)} vues → acteurs.json")


if __name__ == "__main__":
    compiler()
