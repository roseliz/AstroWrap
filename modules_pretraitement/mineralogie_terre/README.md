# Minéralogie de la Terre (EMIT, 6 familles, seuils de confiance)

Pour chaque cellule H3 (résolution 5) des régions arides : part des pixels où chaque famille de minéraux
est détectée, à trois niveaux de confiance. Remplace la minéralogie Terre de `geology_mineralogy`.

## Sources et licences

| Donnée | Rôle | Licence / conditions |
|---|---|---|
| NASA EMIT L2B MIN v002, fichiers MIN et MINUNCERT (60 m) — [10.5067/EMIT/EMITL2BMIN.002](https://doi.org/10.5067/EMIT/EMITL2BMIN.002) | minéral identifié, profondeur de bande, score d'ajustement, incertitude | données NASA, libres ; citer le DOI |
| NASA EMIT L2A MASK v003 — [10.5067/EMIT/EMITL2AMASK.003](https://doi.org/10.5067/EMIT/EMITL2AMASK.003) | nuages (SpecTf), cirrus, eau | données NASA, libres ; citer le DOI |
| NASA EMIT L3 ASA v002 (0,5°) — [10.5067/EMIT/EMITL3ASA.002](https://doi.org/10.5067/EMIT/EMITL3ASA.002) | emprise de la zone aride | données NASA, libres ; citer le DOI |
| Matrice de regroupement des minéraux EMIT (`donnees/mineral_grouping_matrix_20230503.csv`, dépôt [emit-sds/emit-sds-l2b](https://github.com/emit-sds/emit-sds-l2b)) | entrée de bibliothèque -> 10 minéraux | Apache 2.0 (`donnees/LICENCE_emit-sds-l2b.txt`) |

Accès aux données NASA : compte Earthdata, identifiants dans `.env` à la racine (jamais versionné).

## Fichiers

```
scripts/catalogue.py           recherche CMR de tous les granules EMIT L2B (métadonnées seulement)
scripts/selection.py           granules -> cellules H3, les K meilleurs par cellule (zone aride, nuages <= 30 %)
scripts/granule.py             un granule -> comptes par cellule H3 et par classe de qualité
scripts/lot.py                 boucle sur une liste de granules : téléchargement, comptes, suppression ; reprise possible
scripts/familles.py            les 6 familles et leurs poids par entrée de bibliothèque
scripts/liste_calibration.py   granules des zones de calibration
scripts/calibration.py         choix et validation des seuils
scripts/l3.py                  EMIT L3 (grille du GeoTransform : l'axe lat du fichier est décalé de 0,5°)
scripts/fusion.py              comptes par granule -> table finale
donnees/                       matrice EMIT (+ licence), ajouts pour la bibliothèque v002
zones_calibration.csv          zones de calibration
temoins_calibration.csv        témoins de calibration (présence / absence attendue, avec source)
seuils.csv                     seuils retenus, lus par le traitement
audit.csv                      témoins indépendants pour ./pipeline audit
infra/ (racine du dépôt)       Terraform du traitement mondial sur AWS
```

## Lancer

```bash
./pipeline run mineralogie_terre catalogue     # ~45 min, ~100 Mo dans cache/mineralogie_terre/catalogue/
./pipeline run mineralogie_terre selection     # quelques minutes : liste des granules (selection.parquet)
./pipeline run mineralogie_terre calibration   # optionnel : refait les seuils (~45 min, ~31 Go lus)
# traitement mondial : sur AWS (infra/README.md), puis copie du seau dans cache/mineralogie_terre/resultats/
./pipeline run mineralogie_terre               # fusion -> pretreatment_data/mineralogie_terre/
./pipeline audit mineralogie_terre
```

Traitement mondial : ~38 800 granules, ~5,6 To lus dans les seaux de la NASA (région `us-west-2`), sorties
~1 Go. `lot.py --source https` fait la même chose depuis n'importe où, mais à la vitesse de la connexion.

## Sortie

`pretreatment_data/mineralogie_terre/mineralogie_terre_earth_h3_5.parquet` (+ `earth.duckdb`), ~213 000 lignes,
~26 Mo : chaque cellule de la zone aride d'EMIT (141 442), plus les cellules observées en dehors par les bords des
granules (~72 000). Colonnes : `det_<famille>_faible|moyen|fort`, `bd_<famille>`, `n_valides`, `n_total`,
`n_granules`, `zone_aride`, `couverture`, `ab_l3_<famille>` (abondance L3 à 0,5°, autre grandeur), `source`
(L2B, L3), `resolution_source_m`, `id_case_source`. Détail des colonnes : en tête de `scripts/fusion.py`.
`det_*` mesure la présence et l'étendue d'une famille, pas sa teneur ; sous une végétation couvrante, un pixel
valide sans minéral détecté fait baisser `det_*`. `bd_<famille>` est `NaN` là où la famille n'est pas détectée.

**Filtre de qualité.** La zone aride d'EMIT (masque L3 à 0,5°) n'est pas un critère géologique : elle exclut par
exemple le Hoggar. Hors zone, les granules n'ont pas été choisis pour la cellule (~4,4 par cellule au lieu de
~8,7) : valeurs justes mais plus bruitées. Pour comparer, filtrer sur `couverture >= 0.5` (part de la cellule vue
par le meilleur granule : 96 % des cellules de la zone, 75 % hors zone) et documenter le filtre ; `zone_aride`
permet de s'en tenir au périmètre d'origine.

Aperçu (cartes par colonne, carte interactive lonboard, témoins) : `apercu.ipynb` (`pip install lonboard matplotlib`).

**Échelle** (`scripts/echelle.py`, 5 granules) : avec des pixels de 300 m ou ~1 km (mélange linéaire, bruit d'un
pixel de 60 m : hypothèse pessimiste), la part détectée des familles à 2,2 µm tombe à ~0,7 (300 m) et ~0,6 (1 km)
de sa valeur à 60 m (médiane) ; les phases mineures (< 5 %) disparaissent presque à 1 km ; les oxydes de fer ne
baissent pas. À garder en tête pour comparer à OMEGA (~1 km) ou CRISM (18 à 200 m).

## Transformation

1. **Granules** : v002 seulement (v001 détecte 4 à 25 fois plus de micas, carbonates et argiles sur les mêmes
   cellules) ; zone aride d'EMIT ; nuages annoncés <= 30 % ; les 5 meilleurs granules par cellule.
2. **Minéraux** : seuls les 10 minéraux validés d'EMIT, en 6 familles : `oxyde_fer` (hématite, goethite),
   `argile_al` (kaolinite, montmorillonite), `argile_fe_mg` (chlorite, vermiculite), `mica` (illite, muscovite),
   `carbonate` (calcite, dolomite), `sulfate` (gypse). Une entrée de bibliothèque compte pour une famille si
   elle en contient au moins 10 %.
3. **Pixels valides** : géolocalisés, sans drapeau SpecTf-Cloud, cirrus ni eau. Le drapeau nuage classique
   n'est pas utilisé : il marque les surfaces très claires (≈100 % des dunes de gypse de White Sands par ciel clair).
4. **Détection** à trois niveaux : profondeur de bande ≥ 2 (`faible`), 3 (`moyen`) ou 5 (`fort`) fois son
   incertitude (`seuils.csv`). Seuils fixés d'avance, non réglés sur les témoins ; vérifiés sur
   `temoins_calibration.csv` et sur les témoins indépendants d'`audit.csv`.
5. **Agrégation** : comptes de pixels par cellule (additifs), puis parts. Pas de renormalisation ; `NaN` =
   non observé.
