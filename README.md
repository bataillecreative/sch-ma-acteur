# graphe-acteurs

Générateur de graphes d'acteurs pour les diapositives « entrées de ville ».
La figure est **calculée** à partir de `acteurs.json` : aucune position n'est saisie à la main.

## Commande

```
python graphe.py <vue> --w <px> --h <px> [options]
```

Écrit `sorties/<vue>.html` (page autonome, logos lus dans `logos/`) puis `sorties/<vue>.png`
(Chromium headless via Playwright, `device_scale_factor` 3, fond blanc). Les tailles sont en px CSS
(96 px = 1 po). Le terminal affiche les choix faits et le résultat du contrôle automatique
(chevauchements texte/texte, texte/logo, texte/trait, marges ≥ 0,1 po).

Exemples (rendus actuels) :

```
python graphe.py global        --w 1118 --h 394 --agreger bdt,cdch   # zone de diapo 11,65 × 4,1 po
python graphe.py frey          --w 605  --h 300                      # colonne droite 6,3 × 3,1 po
python graphe.py mousquetaires --w 605  --h 300
```

Dépendances : Python 3, Pillow, Playwright (Chromium), police Inter installée
(`/usr/share/fonts/opentype/inter/`).

## Options

| option | effet |
|---|---|
| `--agreger [ids]` | absorbe des nœuds dans le centre de la vue ; leurs liens passent au centre, leurs noms s'ajoutent sous lui. Sans valeur : tout ce que le centre DÉTIENT ou DIRIGE. |
| `--liens tous\|interface\|auto` | `interface` masque les cessions et locations (liens orange) entre deux acteurs privés à régime ; `auto` = interface au-delà de 10 nœuds. |
| `--detail complet\|chiffre\|auto` | `chiffre` ne garde du détail que la partie chiffrée (après « : », segments contenant un chiffre) ; `auto` = chiffre au-delà de 8 nœuds ou de 1 lien pour 40 000 px². |
| `--legendes oui\|non\|auto` | légendes grises des nœuds ; `auto` = non au-delà de 12 nœuds (le centre garde la sienne). |
| `--sans-vehicules` | n'ajoute pas les véhicules absents de la vue (voir règle 5). |
| `--sans-contraction` | ne contracte pas les chemins A → X → B (voir règle 6). |
| `--legende-max <px>` | largeur maximale des légendes (130 par défaut). |
| `--sortie <nom>` | nom de base des fichiers produits. |
| `--scale <n>` | facteur de résolution du PNG (3 par défaut). |

Variable d'environnement `GRAPHE_DEBUG=1` : détaille les étiquettes qui n'ont pas trouvé de place libre.

## Règles de placement

1. **Colonne = régime** : féodal 0, hybride 1, bascule 2, financier 3. Régime `public` → colonne 1,5
   (milieu de l'axe). Véhicules et nœuds sans régime (promoteur) → barycentre des colonnes des
   nœuds auxquels ils sont liés dans la vue.
2. **Bande = statut** : PUBLIC en haut, PARTENARIAT (véhicules) au milieu, PRIVÉ en bas.
   Dans une bande, sous-rangée « extérieure » (en tête de la bande publique, en pied de la bande
   privée) pour les programmes ; un acteur qui émet vers au moins deux nœuds de sa bande sans en
   recevoir (encadrement, ex. l'État) monte en tête de bande. Le centre de la vue ne monte jamais.
3. **Ordre dans une case** (même sous-rangée, même colonne) : permutation de coût minimal —
   voisins liés côte à côte, chaque nœud du côté de ses liens externes, pas d'enjambement d'un
   gros logo, centre de la vue au milieu. Calcul exhaustif (≤ 7 nœuds), donc déterministe.
4. **Colonnes** : position idéale proportionnelle au régime (le centre de la vue au milieu de la
   largeur), puis écartement minimal pour qu'aucune case ne chevauche sa voisine (passes
   gauche → droite et droite → gauche). Si la largeur manque : légendes plus étroites, puis
   noms longs coupés sur deux lignes (d'emblée sur une figure de moins de 800 px).
5. **Véhicule ajouté** : un véhicule absent de la vue mais relié à au moins deux de ses nœuds est
   ajouté (il est le lieu du partenariat).
6. **Contraction** : un nœud X absent de la vue sur un chemin A → X → B devient un lien A → B
   (verbe et détail de X → B, mention « via X » dans le détail complet).
7. **Liens** : segment droit ; s'il traverse un nœud, courbe d'écart croissant de part et d'autre.
   Liens de même sens entre deux mêmes nœuds fusionnés (une ligne d'étiquette par verbe).
8. **Étiquettes** : posées le long de leur lien, à la première place libre (milieu d'abord, de part
   et d'autre, à distance croissante, puis en version empilée) ; les liens les moins libres sont
   servis d'abord. En dernier recours, l'étiquette se pose sur son propre trait, qui s'interrompt
   (seulement si le trait reste visible de part et d'autre).
9. **Axe** : en pied, les régimes portés par au moins un acteur, alignés sur leurs colonnes
   (masqué s'il y en a moins de deux). À gauche, PUBLIC / PARTENARIAT / PRIVÉ alignés sur les
   bandes (un seul libellé en haut à gauche si la vue n'a qu'une bande).

Même entrée, même image : aucune part d'aléatoire.

## Grammaire graphique

- **Acteur** : logo (ou nom en gras s'il n'y en a pas ; nom écrit sous les logos-symboles, cf.
  `LOGOS_SYMBOLES`) + régime en petites capitales (bleu, orange pour BASCULE ; omis pour
  `public`) + légende grise. Le centre de la vue est agrandi.
- **Programme** : nom en italique demi-gras, plus petit + catégorie en petites capitales grises
  + légende grise. Pas de logo.
- **Lien** : trait fin à pointe simple, bleu `#3B38F5` ou orange `#FF5B23` (champ `couleur`), avec
  le VERBE en petites capitales de la même couleur et le détail en gris.
- **Flux financier** (`flux`) : montant en demi-gras noir, précédé d'une petite flèche orientée dans
  le sens où circule l'argent (le long du lien si `flux_sens` = `direct`, à rebours si `inverse`).
- **Source** : dans l'infobulle (`<title>`) du lien dans la page HTML, jamais sur l'image.
- Typographie Inter ; texte `#202125`, gris `#686870`, filets `#C9C9D2` ; espaces insécables à la
  française ajoutés au rendu.

## Fichiers

- `graphe.py` : sélection de la vue, mise en page, page HTML.
- `render.py` : capture PNG et contrôle automatique (utilisable seul :
  `python render.py page.html page.png --w … --h …`).
- `sorties/` : pages et images produites.
