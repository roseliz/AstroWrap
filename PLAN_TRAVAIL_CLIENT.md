# Plan de travail — client AstroWrap

Ce plan répartit le travail entre deux personnes en gardant les changements cohérents et en limitant les conflits. Il part de l'état actuel : `ui/` contient l'installation et les scripts de démarrage, mais pas encore l'interface.

## Règles de travail communes

1. `main` contient le travail intégré. Ne travaillez pas directement dessus.
2. Une fonctionnalité = une branche `feature/...` et une PR vers `main`.
3. Avant de créer une branche, récupérez le `main` à jour :

   ```powershell
   git switch main
   git pull
   git switch -c feature/nom-fonctionnalite
   ```

4. Faites des commits courts, avec un seul sujet par commit. Poussez la branche et ouvrez une PR quand la fonctionnalité est cohérente.
5. La personne qui possède un fichier partagé est la seule à le modifier pour cette étape. Les autres lui demandent les ajouts ou attendent le merge.
6. Travaillez dans deux clones distincts si vous développez en même temps. Ne changez pas de branche dans le même dossier pendant que l'autre personne y a des changements.
7. Après le merge d'une PR, chacune met son `main` à jour avant de commencer la prochaine branche. Si une branche est déjà en cours, intégrez le nouveau `main` avant de demander son merge.

## Étape 1 — accueil et navigation

Ces deux tâches peuvent commencer en parallèle, car elles utilisent des fichiers différents. Convenez d'abord du point d'intégration : l'accueil contient `<header id="navigation"></header>` et le script de navigation l'utilise.

### Personne A — accueil

Branche : `feature/client-accueil`

Fichiers attribués :

- `ui/index.html`
- `ui/css/accueil.css`
- `ui/js/accueil.js`

Responsabilités : créer la page d'accueil minimale, charger ses styles et son script, et réserver l'emplacement `<header id="navigation"></header>` pour la navigation. Ne créez pas ici la logique de navigation.

Commit suggéré : `Ajouter la page d'accueil du client`

### Personne B — navigation

Branche : `feature/client-navigation`

Fichiers attribués :

- `ui/css/navigation.css`
- `ui/js/navigation.js`

Responsabilités : créer une navigation autonome qui s'insère dans `#navigation`. Pendant que la branche accueil n'est pas mergée, travaillez selon le contrat convenu sans modifier `index.html`. Une fois l'accueil mergé, vérifiez l'intégration et demandez à la personne A d'ajouter les liens vers `navigation.css` et `navigation.js` dans `index.html`, ou faites cette petite intégration dans une PR dédiée.

Commit suggéré : `Ajouter la navigation du client`

Ordre des merges : accueil d'abord, navigation ensuite. La PR navigation ne doit pas contenir de copie ou de modification concurrente de `index.html`.

## Étape 2 — pages de sélection des astres

Après l'étape 1, créez des branches à partir du `main` mis à jour. Une personne possède les pages et leur logique; l'autre peut travailler sur la documentation ou les styles partagés, sans modifier les mêmes fichiers.

### Personne A — page Lune

Branche : `feature/client-lune`

Fichiers principaux :

- `ui/lune.html`
- `ui/css/lune.css`
- `ui/js/globe-lune.js`

### Personne B — page Mars

Branche : `feature/client-mars`

Fichiers principaux :

- `ui/mars.html`
- `ui/css/mars.css`
- `ui/js/globe-mars.js`

Les deux pages doivent partager le même contrat de navigation et de chargement des dépendances. Si elles ont besoin d'un nouveau fichier commun, convenez de son propriétaire avant de le créer.

## Étape 3 — sélection de zone et vue Terre

Faites cette étape après les pages Lune et Mars afin de réutiliser leur format de zone.

### Personne A — sélection de zone

Branche : `feature/client-selection-zone`

Fichiers :

- `ui/js/selection-zone.js`
- `ui/css/selection.css`
- intégration dans `ui/lune.html` et `ui/mars.html` (coordonnée avec la personne B si elle modifie encore ces pages)

### Personne B — globe terrestre

Branche : `feature/client-globe-terre`

Fichiers :

- `ui/js/globe-terre.js`
- `ui/css/terre.css` (à créer si nécessaire)
- `ui/terre.html` (à créer si une page distincte est retenue)

Avant de commencer, décidez si la Terre sera une page séparée ou une vue de `index.html`. Une seule personne modifie le fichier HTML choisi.

## Étape 4 — résultats et fiche d'un site

À faire après que l'API et le format de réponse sont connus. Écrivez ce contrat dans la PR ou dans la documentation avant de coder l'interface.

### Personne A — résultats et classement

Branche : `feature/client-resultats`

Fichiers suggérés :

- `ui/js/analogues.js`
- `ui/css/analogues.css`

### Personne B — fiche et bilan

Branche : `feature/client-fiche-bilan`

Fichiers suggérés :

- `ui/bilan.html`
- `ui/js/bilan.js`
- `ui/css/bilan.css`
- fichiers dédiés à la fiche, à créer si nécessaire (par exemple `ui/js/fiche-site.js` et `ui/css/fiche-site.css`)

Si classement et fiche nécessitent tous deux un changement dans `index.html`, attribuez cette intégration à une seule personne ou faites-la dans une PR d'intégration après leurs merges.

## Étape 5 — finitions et documentation

Branche : `docs/client-guide` ou `feature/client-finitions` selon le contenu.

- `ui/README.md` : commandes d'installation et de démarrage, parcours utilisateur, configuration de l'API.
- `ui/images/` et `ui/textures/` : uniquement les assets réellement utilisés par une fonctionnalité mergée.
- `ui/css/style.css` : styles globaux partagés; une seule personne en est responsable à la fois.

Ne remplissez pas `pipeline/` dans le cadre de l'interface : le pipeline de prétraitement doit avoir ses propres tâches et branches.

## Checklist avant une PR

- La branche part du `main` récent et ne contient que la fonctionnalité annoncée.
- Les fichiers touchés correspondent à la répartition ci-dessus; tout fichier partagé est coordonné.
- Le parcours est décrit dans la PR, avec les limites connues et des captures si l'interface a changé.
- La personne qui relit vérifie les liens entre HTML, CSS et JavaScript ainsi que l'intégration avec les fonctionnalités déjà mergées.
- Après merge, les deux personnes récupèrent `main` avant de commencer la prochaine étape.

## Convention de nommage

- Branches : `feature/client-accueil`, `feature/client-navigation`, `feature/client-lune`, etc.
- Commits : verbes courts en français, par exemple `Ajouter la page Mars` ou `Afficher le classement des sites`.
- PR : une fonctionnalité, une description courte, et les fichiers principaux concernés.
