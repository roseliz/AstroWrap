# Analogues terrestres

NASA Space Apps Challenge 2026 : trouver sur Terre les endroits qui ressemblent à une zone de la Lune
ou de Mars.

## Parcours

0. **L'accueil** (`index.html` sans zone) : au centre de l'écran, la Lune et Mars en 3D, chacune dans son cadre,
   tournent sur elles-mêmes (plus vite au survol) ; un clic ouvre `lune.html` ou `mars.html`. « ou explorer la
   Terre d'abord » ferme l'accueil, « Choisir un astre » le rouvre, et le nom du site dans la barre de
   navigation y ramène depuis toutes les pages (`js/accueil.js`, `css/accueil.css`, textures réduites dans `textures/accueil.js`).
1. Sur la Lune ou sur Mars, l'utilisateur **peint la zone de référence** avec des tuiles H3.
2. « Comparer avec la Terre » enregistre la zone sur le serveur (`POST /api/zones`) et ouvre
   `index.html#mars/<id>` (12 caractères) : `js/analogues.js` relit la zone et lance la recherche
   (`../server`, http://127.0.0.1:8000 par défaut, ou `?api=…` dans l'adresse).
3. **Le chargement** : le panneau de droite montre un indicateur (« Votre zone est comparée à toute la Terre… »)
   pendant la recherche (1 à 3 s), puis le classement. La recherche part dès l'ouverture de la page, en même
   temps que la liste des critères. L'entonnoir n'est plus rejoué étape par étape (trop long) ; ses étapes
   restent dans la réponse du serveur et le bilan animé les montre.
4. **Le résultat**, à droite : la liste des 10 sites (au moins 300 km entre deux), chacun avec un mot de couleur
   (très proche, proche, partiel, éloigné). Chaque site est jugé sur une surface de même taille que la zone peinte
   (son empreinte, contour blanc sur le globe quand on l'ouvre), et un site dont l'empreinte est à plus de 15 % en
   mer est écarté. En dessous, **l'importance de chaque critère** : un curseur par module
   (0 = ignoré, jusqu'à 3) avec sa part en %, et un menu de préréglages (équilibré, site d'atterrissage,
   géologie...). La liste se recalcule aussitôt dans le navigateur (un critère à 0 n'y filtre plus). Le filtre de végétation et « Votre zone sur Mars » sont
   repliés. Sur le globe, un losange numéroté par site, cliquable, à l'endroit exact du site ; le site ouvert
   montre la surface sur laquelle il est jugé (son empreinte, remplie et cernée de blanc).
5. **La fiche d'un site**, à gauche : nom du lieu (Natural Earth, OpenStreetMap), verdict en un mot, les boutons
   « Play the AstroWrap » et « Compare the terrain », puis deux onglets. **Data** : le tableau côte à côte, une
   ligne par variable (zone de Mars ou de la Lune | site sur Terre | ressemblance) ; la fiche s'élargit. L'impact d'une
   campagne d'essais est dans l'onglet « Responsible testing » du panneau de droite. **Overview** (par défaut) :
   **« Pourquoi ce site ? »** en phrases : ce qui ressemble à la zone (deux ou trois critères) et la plus grande
   différence, avec les deux valeurs. Ensuite une ligne par critère ; un clic montre ses deux valeurs
   principales, Mars à gauche et Terre à droite, sur une même échelle. « En savoir plus sur ce site » (replié) :
   climat, relief, sol, glace, volcans et grottes du site, Wikipédia à proximité, liens OpenStreetMap et
   satellite. ‹ › ou les flèches du clavier passent d'un site à l'autre ; Échap ferme la fiche.
6. **« Comparer les reliefs »** (dans la fiche) : écran partagé, la zone de Mars (ou de la Lune) à gauche, le site
   terrestre à droite, sur le même carré en km (cadré sur la zone peinte). Le **contour blanc** de la zone est
   reporté tel quel autour du site ; en pointillé blanc, l'empreinte jugée sur Terre.
   - **Vue de dessus** : même ombrage, couleur d'altitude relative (du plus bas au plus haut de chaque carré), mer
     en bleu, barre d'échelle ;
   - **Coupe** : le profil des deux zones sur le même graphique (ouest → est ou nord → sud), la partie dans la zone
     surlignée ; un clic sur une carte déplace la coupe ;
   - **Pentes** : la part du terrain par classe de pente, tirée des déciles mesurés à 500 m que compare le critère
     Relief (sinon, calculée sur la grille) ;
   - **3D** : les deux maquettes, caméras liées, exagération réglable, image satellite ou relief seul ; three.js
     (r147, unpkg) n'est chargé qu'à ce moment.
   Le contour de la zone donne le **verdict d'ensemble du relief** (mêmes seuils et couleurs que la liste : vert très
   proche, vert-jaune proche, jaune partiel, rouge éloigné), en 2D comme en 3D, avec le pourcentage à côté du titre :
   moyenne de la ressemblance des coupes (dénivelé du 5e au 95e centile et rugosité, |Δz| moyen d'un point de la
   grille au suivant, sur toutes les lignes et colonnes dans la zone ; rapport du plus petit au plus grand) et de
   celle des pentes (part commune des classes).
   **À l'intérieur de la zone, un dégradé du rouge au vert**, toujours affiché : chaque point a un
   type de terrain, sa pente et sa rugosité (écart-type de l'altitude sur ~1,5 km), rangé dans un histogramme 2D ;
   sa couleur = part de ce type de terrain dans la zone d'en face / sa part dans sa propre zone (plafonnée à 1),
   lissée. Vert : ce terrain se retrouve de l'autre côté ; rouge : il y est rare ou absent. Deux zones identiques
   sont vertes partout. Ce n'est pas une comparaison point par point : rien n'oblige un coin de la zone de Mars à
   ressembler au même coin du site.
   Tout tient sur un écran (cartes, coupe, pentes ; défilement seulement sur téléphone) ; les explications sont
   dans les infobulles (titre « Coupe », « Pentes », pourcentages, barre du dégradé, crédits des données).
   Relief et images viennent du serveur (`GET /api/relief`). Échap ferme la vue.

7. **« ✦ Voir le bilan »** (petit bouton discret dans la fiche) : ouvre `bilan.html` dans un nouvel onglet, un bilan animé
   du site, à la manière d'un « Wrapped » : onze diapositives plein écran, une barre de progression, peu de texte,
   « Mars | Terre » partagé en deux quand la comparaison s'y prête. Dans l'ordre : le score, l'entonnoir (de 613 252
   régions à un site), le radar des critères, le relief en 3D côte à côte (seulement si le relief se ressemble),
   les températures jour et nuit, la composition des roches, ce qui se ressemble, ce qui change, le profil
   d'usage le mieux placé (les préréglages de poids), les limites du site (végétation, données manquantes ou
   partielles, gravité et pression qu'aucun site terrestre ne reproduit) et le résumé. Tout vient du serveur ;
   une diapositive dont la donnée manque est sautée. ‹ › ou flèches : naviguer ; P : pause ; Échap : fermer.
   L'adresse porte la zone (identifiant du serveur), les poids et le score : `bilan.html?w=…&s=…&n=…#mars/<zone>/<cellule>`.

8. **Analogues connus** (sous la liste des sites) : des sites que les scientifiques comparent déjà à Mars ou à la
   Lune (île Devon, Atacama, vallées sèches...), chacun à son **vrai rang** pour la zone peinte : « Top 1 % »,
   263e sur 20 326 candidats, et s'il passe l'entonnoir ou à quelle étape il est écarté. Ils ne sont jamais ajoutés
   au classement ; un losange les montre sur le globe, un clic ouvre leur fiche. Les analogues de minéraux (Rio
   Tinto, lac Salda) sont signalés hors de portée. Le contrôle global sur ces couples reste dans l'API
   (`GET /api/validation`, voir `../server/README.md`).

Le serveur doit tourner (voir `../server/README.md`) ; sinon la page le dit.

## Pages

Une **barre de navigation** (`js/navigation.js`, `css/navigation.css`) est en haut de toutes les pages sauf le bilan :
le nom ramène à l'accueil ; **Lune** et **Mars** ouvrent la page où l'on peint la zone ; **Terre** rouvre les
résultats de la dernière zone comparée (gardée dans le navigateur, un point de couleur le signale), sinon le globe à
explorer (`index.html#terre`, sans la fenêtre d'accueil) ; **À propos** à droite. Sur téléphone,
un bouton ☰ déroule les liens. Le paramètre `?api=…` suit d'une page à l'autre.

- `index.html` : l'accueil (choix de la Lune ou de Mars), puis la Terre en 3D (MapLibre GL), avec bascule vers
  une carte 2D, et les résultats de la comparaison.
- `bilan.html` : l'AstroWrap d'un site, le bilan animé carte par carte (`js/bilan.js`, `css/bilan.css`), ouvert depuis
  la fiche d'un site (« Play the AstroWrap ») ou depuis l'écran « Your AstroWrap is ready » qui suit la première
  recherche d'une zone. Logo et favicon dans `images/` (fond rendu transparent).
- `apropos.html` : ce que fait l'outil, comment, ses limites, les sources des données et leurs crédits, l'équipe.
- `lune.html` : la Lune en 3D (globe.gl), avec bascule vers une carte 2D et sélection de zone.
  Ce globe affiche les pôles, ce que MapLibre ne fait pas au-delà de 85° de latitude.
- `mars.html` : Mars en 3D (globe.gl), mêmes fonctions que la Lune, avec le halo de la fine
  atmosphère martienne.

La grille des coordonnées est toujours affichée. Les cartes 2D de la Lune et de Mars sont en
projection équirectangulaire : latitude et longitude y sont des axes droits, comme dans les cartes de
la NASA. On passe du globe à la carte en gardant la même zone à l'écran.

## Lancer

Depuis `application/client/`, avec Node.js 18 ou plus :

```bash
npm install     # bibliothèques (node_modules) et serveur Python (../server/.venv, requirements.txt)
npm start       # interface sur http://localhost:8080 et serveur de l'application sur le port 8000
```

`npm install` sert aussi à **mettre à jour** : relancez-le après un `git pull` (nouvelles bibliothèques ou
nouvelles dépendances Python). Il crée `../server/.venv` avec le premier Python 3.9+ trouvé (`py -3` sous
Windows, `python3`, `python`) puis y installe `requirements.txt` ; s'il n'y arrive pas, il le dit sans bloquer.
`ANALOGUES_SANS_PYTHON=1` saute cette étape, `ANALOGUES_PYTHON=chemin` choisit le Python.

| Commande | Effet |
|---|---|
| `npm start` | interface + serveur (relancé seulement s'il ne répond pas déjà sur le port 8000) |
| `npm run client` | interface seule (serveur ailleurs : `?api=http://hote:port` dans l'adresse) |
| `npm run api` | serveur seul |

Ports : `PORT` (interface, 8080) et `API_PORT` (serveur, 8000). Les données du serveur viennent de
`pretreatment_data/` à la racine du dépôt (ou `ANALOGUES_DONNEES`, voir `../server/README.md`).

Les bibliothèques (MapLibre GL, globe.gl, Leaflet, h3-js, three.js) sont lues dans `node_modules/` ; si le
dossier manque (page ouverte sans `npm install`), chaque page les prend sur unpkg ou jsDelivr. Il faut de toute
façon Internet pour les images (NASA Trek, Esri) et la police.

| Action | Souris | Clavier | Tactile |
|---|---|---|---|
| Tourner le globe | glisser | flèches | glisser |
| Zoomer | molette, double-clic | + et − | pincer |
| Revenir à la vue entière | | Échap | |

## Repères (Lune et Mars)

Les sites connus sont marqués sur le globe et sur la carte 2D : un rond plein pour un site
d'atterrissage (Apollo, Viking, Curiosity, Perseverance...), un anneau pour un relief (Olympus Mons,
Hellas, Tycho, Shackleton...). Les noms secondaires apparaissent quand on zoome. Survoler un repère
affiche sa description ; cliquer dessus amène la vue. La liste et les coordonnées sont dans
`js/reperes.js`.

## Sélection de la zone de référence (Lune et Mars)

Le panneau « Zone de référence », à droite, sert à peindre la zone à comparer avec la Terre. Il
marche sur le globe comme sur la carte 2D.

| Action | Souris | Clavier |
|---|---|---|
| Peindre des tuiles | outil « Peindre », puis glisser | B |
| Gommer | outil « Gommer », ou Maj en peignant | E |
| Revenir à la navigation | outil « Naviguer » | V |
| Déplacer la vue sans quitter le pinceau | | Espace maintenu + glisser |
| Taille du pinceau | Fin, Moyen, Large | [ et ] |
| Annuler | bouton « Annuler » | Ctrl+Z |

- **Les tuiles sont des cellules H3 de résolution 6** (Mars : ~10 km² ; Lune : ~2,7 km²). Ce sont
  exactement les cellules que le prétraitement utilisera.
- **Le pinceau suit le zoom.** Vu de loin, il pose de grandes cellules, découpées ensuite en tuiles
  de résolution 6 ; de près, il pose des tuiles une par une.
- **Le panneau affiche** la surface, le nombre de tuiles, le nombre de parties séparées et le centre.
  Une zone doit compter au moins 10 tuiles et au plus 60 000.
- **L'adresse ne contient jamais les cellules H3.** Sur Mars ou la Lune, la zone est gardée dans le navigateur
  (`localStorage`) : un rechargement la retrouve. Pour la Terre, elle passe par le serveur (identifiant court,
  `server/cache/zones/`) : ça marche aussi dans les navigateurs qui isolent chaque fichier ouvert en `file://`
  (Firefox), et le lien `index.html#mars/<id>` peut se partager tant que le serveur garde son cache. Serveur
  arrêté : repli sur le navigateur. Les anciennes adresses `#zone=...` sont encore lues, puis nettoyées.
- **« Exporter » télécharge la zone en JSON** (cellules compactées, résolution, surface, centre).
  En Python : `h3.uncompact_cells(cellules_compactees, 6)` donne la liste complète.

## Organisation

```
package.json           npm install, npm start (bibliothèques, scripts)
scripts/demarrer.mjs   npm start : sert l'interface et lance le serveur Python
scripts/installer-api.mjs  après npm install : ../server/.venv et requirements.txt
index.html             accueil et globe terrestre
css/style.css
js/accueil.js          accueil : la Lune et Mars en 3D (three.js), un clic ouvre leur page
css/accueil.css
js/globe-terre.js      globe MapLibre, carte 2D, grille, coordonnées
js/analogues.js        comparaison avec la zone de Mars ou de la Lune (appel au serveur, couches, panneau, analogues connus)
css/analogues.css
apropos.html           à propos : méthode, limites, sources des données (css/pages.css, styles des pages de texte)
js/navigation.js       barre de navigation de toutes les pages (sauf le bilan)
css/navigation.css
lune.html              globe lunaire
css/lune.css
js/globe-lune.js       globe globe.gl : texture, relief, contrôles, coordonnées
mars.html              globe martien
css/mars.css
js/globe-mars.js       globe globe.gl : texture, tuiles NASA Mars Trek, relief, contrôles
js/carte-plane.js      carte 2D (Leaflet) partagée par lune.html et mars.html
js/selection-zone.js   sélection de la zone de référence en tuiles H3 (Lune et Mars)
css/selection.css      panneau « Zone de référence »
js/reperes.js          sites connus (atterrissages, reliefs) affichés comme repères
css/reperes.css
textures/              images de la Lune et de Mars encodées en .js
scripts/construire_textures_lune.py   régénère les textures de la Lune à partir d'images NASA
scripts/construire_texture_mars.py    régénère la texture de Mars intégrée
scripts/construire_textures_accueil.py  régénère textures/accueil.js (textures réduites de l'accueil)
pipeline/              prétraitement des données (modules Python, notebooks Colab)
_ancien_prototype/     première interface, mise de côté
```

`js/cle-carto.js` et `js/cle-carto.exemple.js` ne servent plus : le fond « Plan » a été retiré de la
page Terre. Vous pouvez les supprimer.

## Textures de la Lune

Les images viennent du CGI Moon Kit du NASA Scientific Visualization Studio
(https://svs.gsfc.nasa.gov/4720) : mosaïque couleur LROC et relief LOLA. Elles sont encodées dans
des fichiers `.js` parce que le navigateur refuse d'utiliser une image locale comme texture 3D quand
la page est ouverte par double-clic. La page charge d'abord la version 4096 px, puis la 8192 px si la
carte graphique l'accepte.

Pour plus de détail (par exemple la version 16k), téléchargez les images sur la page de la NASA, puis :

```bash
pip install pillow
python scripts/construire_textures_lune.py --couleur lroc_color_poles_16k.tif --relief ldem_3_8bit.jpg
```

La NASA précise que cette mosaïque est faite pour l'affichage, pas pour la science : les mesures
viendront des données sources (LROC WAC, LOLA).

## Images de Mars

La page affiche tout de suite une carte NASA intégrée de 1440 px (dépôt officiel
NASA-3D-Resources), qui fonctionne même hors ligne. Ensuite, le navigateur assemble une version de
4096 px à partir des tuiles NASA Mars Trek : mosaïque couleur Viking MDIM 2.1 et relief MOLA. Si le
serveur de la NASA refuse ces tuiles, la page le signale et garde la carte intégrée.

En carte 2D, les tuiles Trek s'affichent comme de simples images, sans demander d'autorisation au
serveur : la pleine résolution est disponible (Viking jusqu'à ~232 m/px). La carte 2D de la Lune
tente de même les tuiles Moon Trek (mosaïque LRO WAC, ~100 m/px) par-dessus l'image intégrée.
