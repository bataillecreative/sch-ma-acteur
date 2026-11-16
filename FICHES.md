# Écrire une fiche

Une fiche = un fichier Markdown. En-tête YAML entre deux lignes `---`, puis texte libre (repères, chiffres clés, notes).

## Fiche acteur (`fiches/acteurs/<id>.md`)

```yaml
---
type: acteur
id: casino                 # identifiant court, minuscules, sert de cible aux connexions
nom: Casino
logo: image29.png          # fichier du dossier logos/, ou null
statut: privé              # public | véhicule | privé  → rangée du graphe
régime: bascule            # féodal | hybride | bascule | financier | public → colonne du graphe
légende: cède pour se désendetter
connexions:
- CÉDER icade : 10 sites {39 M€} (Icade et Casino, 2025)
---
```

## Fiche programme (`fiches/programmes/<id>.md`)

Même en-tête, avec `type: programme` et `catégorie` : politique publique, véhicule commun,
programme d'enseigne, offre, opération. Pas de logo.

## Connexions

Une ligne par connexion, écrite depuis la fiche de l'acteur qui agit :

    VERBE cible : détail {flux financier} (Source, année)

- `VERBE` en capitales (DÉTENIR, FINANCER, CÉDER, SE RETIRER…). La couleur en découle : orange pour
  CÉDER, SE RETIRER, LOUER, REPRENDRE ; bleu sinon (`verbes.yaml`).
- `cible` : l'`id` d'une autre fiche.
- `{…}` : montant qui circule. Par défaut l'argent suit la flèche ; pour CÉDER et LOUER il va en sens inverse.
- `(Source, année)` : comme dans le deck. Tout chiffre doit avoir sa source.

Après modification : `python fiches.py` (vérifie les cibles et les vues, écrit `acteurs.json`), puis le générateur.
