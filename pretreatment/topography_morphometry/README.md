# Topographie, morphométrie et cratères

Forme du terrain de chaque cellule H3 (résolution 5) sur **la Terre, Mars et la Lune, à toutes les
latitudes** : la distribution des pentes, la part de terrain plat, la rugosité, le dénivelé, la
courbure et la densité de cratères.

Une pente dépend de la taille du pixel sur lequel on la mesure. Le module calcule donc tout à une
**base** fixe, la même pour les corps comparés : **500 m** pour les trois corps (c'est celle de Mars) et
**100 m** pour la Terre et la Lune. On compare la Terre et Mars à la base 500, la Terre et la Lune à la
base 100 (ou 500).

## Fichiers

```
run.sh                        point d'entrée (./pipeline run topography_morphometry)
requirements.txt, inputs.txt  dépendances ; dossiers pour déposer un fichier si un téléchargement échoue
crateres_terre.csv            structures d'impact confirmées de la Terre (Earth Impact Database, 189)
scripts/pretraitement.py      le prétraitement des trois corps
```

## Sources

Tout est téléchargé automatiquement, sans compte.

| Corps | Source | Sert à | Téléchargement |
|---|---|---|---|
| Terre | **Copernicus DEM GLO-90** (ESA), pixels de 3″ (~90 m), tuiles de 1° | relief | ~26 000 tuiles sur AWS Open Data, lues une par une puis effacées (plusieurs dizaines de Go transférés, quelques dizaines de Mo sur le disque) |
| Terre | **Earth Impact Database** (PASSC, University of New Brunswick) | cratères | dans le dépôt (`crateres_terre.csv`) |
| Mars | **MOLA MEGDR** (Mars Global Surveyor), mosaïque globale USGS de 463 m | relief | 2 Go, gardé dans `cache/` |
| Mars | **Catalogue de Robbins et Hynek (2012)**, ~384 000 cratères de 1 km et plus | cratères | service USGS (pygeoapi), gardé dans `cache/` |
| Lune | **LOLA LDEM** (Lunar Reconnaissance Orbiter), mosaïque globale USGS de 118 m | relief | 8 Go, gardé dans `cache/` |
| Lune | **Catalogue de Robbins (2018)**, ~1,3 million de cratères | cratères | USGS Astropedia (~90 Mo), gardé dans `cache/` |

Si un téléchargement échoue (pare-feu, serveur en panne), déposer le fichier à la main dans le dossier
indiqué par `inputs.txt` : le script le prend en priorité.

- MNT de Mars : <https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif>
- MNT de la Lune : <https://planetarymaps.usgs.gov/mosaic/Lunar_LRO_LOLA_Global_LDEM_118m_Mar2014.tif>
- Cratères de Mars : [Mars Crater Database (Robbins 2012)](https://astrogeology.usgs.gov/search/map/mars_crater_database_robbins_2012),
  le fichier `.tsv` dans `inputs/topography_morphometry/crateres_mars/`
- Cratères de la Lune : [Moon Crater Database v1 (Robbins 2018)](https://astrogeology.usgs.gov/search/map/moon_crater_database_v1_robbins),
  le fichier `.csv` dans `inputs/topography_morphometry/crateres_lune/`

Le script reconnaît les colonnes de latitude, de longitude et de diamètre des deux catalogues de Robbins
et les affiche.

## Lancer

```bash
./pipeline check topography_morphometry
./pipeline run topography_morphometry --corps mars       # ~10 min après le téléchargement de 2 Go
./pipeline run topography_morphometry --corps moon       # ~30 min à 1 h après le téléchargement de 8 Go
./pipeline run topography_morphometry --corps earth      # quelques heures, surtout le téléchargement
./pipeline run topography_morphometry                    # les trois, l'un après l'autre
```

Les trois corps peuvent tourner en parallèle dans trois terminaux (`--corps earth`, `--corps mars`,
`--corps moon`) : ils n'écrivent pas dans les mêmes fichiers. Compter ~3 Go de RAM par corps.

| Option | Effet |
|---|---|
| `--corps earth mars moon` | corps à traiter (défaut : les trois) |
| `--resolution 5` | résolution H3 |
| `--bases 500 100` | bases de calcul en mètres (défaut : les deux ; Mars n'a que 500) |
| `--crateres-seulement` | recalculer seulement `densite_crateres` dans les résultats déjà écrits (quelques secondes) |
| `--zone O S E N` | Terre : ne télécharger et ne traiter que les tuiles de cette boîte (degrés), pour un essai |
| `--telechargements 6` | Terre : tuiles téléchargées en parallèle |
| `--mnt-mars`, `--mnt-lune` | MNT déjà téléchargés (fichier ou dossier) |
| `--crateres-mars`, `--crateres-lune` | catalogues de cratères déjà téléchargés |
| `--echelle-lune 0.5` | mètres par unité du MNT lunaire, si le fichier ne l'indique pas |

Essai rapide sur la Terre (Meteor Crater, 4 tuiles) :
`./pipeline run topography_morphometry --corps earth --zone -112 34 -110 36`.

Résultats dans `pretreatment_data/topography_morphometry/` : un fichier par corps et par base,
`topography_morphometry_{corps}_h3_5_b{500,100}.parquet`, et les tables du même nom dans
`{earth,mars,moon}.duckdb`.

## Colonnes

`body`, `resolution`, `h3`, puis :

| Colonne | Définition |
|---|---|
| `base_m` | base de calcul nominale (500 ou 100 m) ; ne comparer que des lignes de même base |
| `base_effective_m` | côté réel des pixels de calcul (Terre 463 et 93 m, Mars 463 m, Lune 474 et 118 m) |
| `resolution_source_m` | pixel du MNT d'origine (90, 463 ou 118 m) |
| `pente_p10` … `pente_p90` | déciles de la pente (°) dans la cellule : la distribution, pour la distance de Wasserstein |
| `pente_moy` | pente moyenne (°) |
| `part_pente_inf_5` | part des pixels de pente inférieure à 5° (terrain où se poser) |
| `rugosite_rms` | écart quadratique moyen entre l'altitude d'un pixel et la moyenne des 3 × 3 pixels autour (m) : les bosses à l'échelle de la base |
| `denivele_p5_p95` | écart entre les 5e et 95e centiles d'altitude de la cellule (m) |
| `courbure_moy` | courbure moyenne (−laplacien de l'altitude, 1/km) : > 0 la cellule est bombée, < 0 elle est en creux |
| `courbure_abs_moy` | moyenne de la valeur absolue de la courbure (1/km) : la quantité de creux et de bosses |
| `densite_crateres` | cratères de 1 km de diamètre et plus par 1 000 km², comptés sur la cellule et ses voisines (voir Méthode) |
| `n_pixels` | pixels de calcul utilisés (un sur 9 pour la Terre en base 100, voir Méthode) |
| `couverture` | part de la cellule où le MNT a une altitude (Terre : la mer et les tuiles absentes comptent comme vides) |
| `fiabilite` | = `couverture` (provisoire, même règle que les autres modules) |

## Méthode

- **Base** : les pixels du MNT sont moyennés par blocs pour atteindre la base (Terre 5 × 5 pixels de 3″
  pour 500 m, Lune 4 × 4 pour 500 m). En allant vers les pôles, un degré de longitude rétrécit : on
  regroupe alors aussi les colonnes pour que les pixels restent à peu près carrés. C'est ce qui permet
  de calculer jusqu'aux pôles avec les mêmes formules.
- **Pente** : différences centrées sur les pixels voisins, en mètres sur la sphère du corps ;
  `atan(|∇z|)`. La courbure est le laplacien discret ; la rugosité, l'écart à la moyenne 3 × 3.
- **Cellules** : chaque pixel va à la cellule H3 qui contient son centre (calculé par petits blocs
  d'environ 1/8 de cellule). Les déciles sont exacts : le MNT est lu du nord au sud et une cellule est
  calculée dès que tous ses pixels sont passés. Terre en base 100 : ~29 000 pixels par cellule, on en
  garde un sur 3 dans chaque direction (~3 000), ce qui ne change pas les déciles.
- **Terre** : un pixel d'altitude 0 est de la mer (Copernicus met la mer à 0 et n'a pas de tuile en
  pleine mer). Les cellules sont celles qui ont au moins un pixel de terre.
- **Cratères** : à la résolution 5, une cellule de la Lune ne fait que 19 km² (Mars 72 km², Terre
  253 km²) et contient rarement un cratère. On compte donc les centres des cratères de 1 km et plus
  sur la cellule et les anneaux de cellules voisines, jusqu'à une fenêtre d'au moins 1 000 km² (Terre :
  1 anneau, ~1 800 km² ; Mars : 2 anneaux, ~1 400 km² ; Lune : 4 anneaux, ~1 100 km²).

## Limites

- Une même pente n'a pas la même stabilité partout : la gravité de Mars (0,38 g) et de la Lune (0,17 g)
  change la tenue des talus.
- `denivele_p5_p95` dépend de la taille de la cellule, qui n'est pas la même sur les trois corps à la
  résolution 5 (la grille H3 est définie sur une sphère unité) : comparer le dénivelé avec prudence. Les
  pentes, la rugosité et la courbure sont mesurées à la même base et se comparent.
- Les cratères terrestres sont rares et érodés : 167 structures confirmées de 1 km et plus.
  `densite_crateres` est donc presque partout 0 sur Terre ; elle sert à trouver les rares sites d'impact
  (Meteor Crater, Haughton, Ries…).
- Les lacs sont plats dans Copernicus (altitude constante) : ils augmentent `part_pente_inf_5`.
- Mars au-delà de ±88° et la Lune près des pôles : le MNT y est interpolé entre les traces de
  l'altimètre ; les valeurs sont calculées mais moins sûres.
- Affinage plus fin (30 m, MNT locaux CTX, HiRISE, SLDEM, LOLA polaire à 5 m) : pas dans ce module ; il
  se fera sur les meilleures cellules, après la comparaison.
