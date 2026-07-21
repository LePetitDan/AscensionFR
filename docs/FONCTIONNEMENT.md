# ⚙️ Comment fonctionne la traduction

Pour les curieux — voici ce qui se passe sous le capot, en français simple.

## Un addon, rien qu'un addon

Ascension FR est un **simple addon** — le système officiellement autorisé par
le jeu, le même qui fait vivre les barres d'action ou les cartes améliorées.

- **Aucun fichier du jeu n'est modifié.** L'installation ne fait qu'ajouter
  des fichiers d'addon. Tout supprimer remet le jeu exactement comme avant.
- **Aucune automatisation, aucun contournement.** L'addon ne joue pas à ta
  place et ne triche pas : il ne fait qu'**afficher** du français.

## La traduction « à l'affichage »

Le principe : au moment où le jeu s'apprête à afficher un texte anglais,
l'addon le reconnaît et affiche sa version française à la place.

- **Reconnu → français.** Quêtes et sorts sont reconnus par leur numéro
  (fiable à 100 %), le reste par son texte exact.
- **Pas reconnu → anglais intact.** C'est la règle d'or : jamais de texte
  cassé, jamais de moitié de phrase. Dans le doute, l'anglais s'affiche.
- **Les nombres qui changent** (dégâts selon ton équipement…) sont réinjectés
  dans la phrase française par un moteur d'alignement qui vérifie que tout
  correspond avant d'afficher.

## D'où vient le français ?

- **Le jeu de base** (quêtes, sorts, objets, zones classiques) : les
  traductions **officielles** de l'époque Wrath of the Lich King, croisées
  par identifiant. C'est le même français que le client français officiel.
- **Le contenu custom d'Ascension** (classes, talents, quêtes maison) :
  traduit par notre chaîne (traduction assistée + glossaire World of Warcraft
  + relecture), puis amélioré en continu grâce aux
  [rapports des joueurs](CONTRIBUER.md).

## Et la sécurité ?

Une ancienne traduction communautaire avait été retirée du jeu car elle
provoquait des plantages. Ascension FR a été bâti sur cette leçon :

- chaque texte passe par des **contrôles automatiques** qui refusent tout ce
  qui pourrait perturber le jeu (formats incompatibles, textes que le moteur
  du jeu lit en interne…) ;
- l'addon n'écrit **jamais** dans les variables que le jeu relit pour agir —
  uniquement dans ce qui s'affiche ;
- en cas de doute, le texte reste en anglais. L'anglais, c'est moche ; un
  plantage, c'est pire. 😄

## En chiffres

- **Plus de 340 000 textes** français actifs ;
- **43 fichiers** d'addon, tous en texte lisible ;
- une **base mémoire optimisée** : les plus grosses tables ne se chargent
  qu'à la demande, ta mémoire de jeu reste tranquille.

Des questions plus pointues ? Passe sur le
[Discord](https://discord.gg/kFJGDJbeay) — ou lis le code, il est ouvert. 🔍
