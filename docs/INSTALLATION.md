# 📥 Installation — le guide complet

Deux façons d'installer, au choix. Les deux donnent **exactement la même
traduction**.

| | 🖥️ **Avec le Hub** | 📁 **À la main** |
|---|---|---|
| Pour qui | ceux qui veulent le plus simple | ceux dont l'antivirus râle, ou qui préfèrent ne rien exécuter |
| Comment | double-clic, un bouton | extraire un zip |
| Mises à jour | **en un clic** (et l'appli se met à jour toute seule) | re-télécharger le zip |
| Vérifier / désinstaller | **un bouton pour chaque** | à la main (tout est expliqué plus bas) |

## 📁 À la main (2 minutes, que des fichiers)

### **[⬇ Télécharger `AscensionFR_manuel.zip`](../../../releases/latest/download/AscensionFR_manuel.zip)**

C'est une traduction : rien que des fichiers d'addon (`.lua` / `.xml`), du
texte que tu peux ouvrir dans le Bloc-notes et lire. **Aucun programme, aucun
`.exe`, rien ne s'exécute.** Ce lien pointe toujours sur la dernière version.

1. **Télécharge le zip** (le lien ci-dessus).
2. **Extrais-le dans le dossier de ton jeu Ascension.** C'est le dossier qui
   contient **`Ascension.exe`** et les dossiers **`Data`** et `Interface` —
   souvent `…\resources\ascension-live`.
   **⚠️ Surtout pas dans `Interface\AddOns`.** C'est l'erreur n°1 : le zip
   apporte déjà l'arborescence `Interface\AddOns\…`, alors si tu l'extrais
   dans `Interface\AddOns` tu obtiens
   `Interface\AddOns\Interface\AddOns\AscensionFR`, que le jeu ne lira
   jamais.
   Windows te demande de **fusionner le dossier `Interface`** → dis **oui**
   (ça n'efface aucun de tes autres addons, ça ajoute les nôtres à côté).
3. Lance le jeu jusqu'à l'écran de **sélection des personnages**. En bas à
   gauche, clique sur **« AddOns »**, puis :
   - coche **« Allow Non-Launcher AddOns »** — la case **juste au-dessus** de
     « Load out of date AddOns », en bas à droite du panneau. Sans elle, le
     jeu refuse de charger AscensionFR, quoi que tu fasses ;
   - vérifie qu'**AscensionFR** est coché dans la liste ;
   - puis **Applique**.
4. Connecte-toi, tape **`/afr`** et vérifie que **« Activer la traduction »**
   est cochée. **C'est en français !** 🎉

> ✅ Tu dois obtenir `Interface\AddOns\AscensionFR`,
> `Interface\AddOns\AscensionFR_Repliques` et `Interface\PTRXML`.
> L'extraction place tout au bon endroit toute seule.
>
> 🔎 Si la ligne AscensionFR affiche **« Not a Launcher AddOn »**, c'est que
> la case « Allow Non-Launcher AddOns » n'est pas cochée.

## 🖥 Avec le Hub

1. **[Télécharge `AscensionFR_Compagnon.exe`](../../../releases/latest)** et
   pose-le où tu veux (bureau, dossier du jeu…).
2. Double-clique dessus : il **trouve ton jeu tout seul**.
3. Clique sur **« Installer la traduction »**, puis sur **« Vérifier mon
   installation »**. C'est fini. 🎉

> 🛡️ Au premier lancement, Windows peut afficher un écran bleu « Windows a
> protégé votre ordinateur » : c'est le lot de tout programme non signé d'un
> petit projet. Clique **« Informations complémentaires » → « Exécuter quand
> même »**. Le [code source est public](../compagnon/) si tu veux vérifier ce
> qu'il fait.
>
> 🦠 **Ton antivirus supprime le fichier**, même en le relançant ? Ne te bats
> pas avec lui : prends [le zip](#-à-la-main-2-minutes-que-des-fichiers)
> ci-dessus, tu auras exactement la même traduction. (Le faux positif est
> signalé à Microsoft ; en attendant, le zip est la solution.)
>
> 🔐 Si ton jeu est dans `C:\Program Files`, Windows protège ce dossier :
> le Hub te proposera un bouton **« Relancer en administrateur »**,
> accepte et tout se déroulera normalement.

### Les petits plus du Hub

- **« Vérifier mon installation »** : il contrôle le dossier du jeu, la
  présence de l'addon, qu'il est bien coché et que la traduction est activée —
  et il **répare** ce qui peut l'être, d'un bouton.
- **« Tout désinstaller »** : il liste **tout** ce qu'il va retirer, te laisse
  décocher ce que tu veux garder, puis nettoie pour de bon.
- **À la fermeture du jeu**, il envoie tes découvertes (voir
  [Contribuer](CONTRIBUER.md)) — désactivable dans l'onglet Contribuer.
- **Un catalogue d'addons** français, installés et mis à jour d'un bouton.

## 🔄 Mettre à jour

- **Hub** : il te prévient et tout se fait en un clic.
- **À la main** : extrais le nouveau zip par-dessus (dis « oui » pour
  remplacer), puis `/reload` en jeu ou reconnecte-toi. Tes réglages sont
  conservés.
- ⚠️ Quand une version ajoute de **nouveaux fichiers** à l'addon, un simple
  `/reload` ne suffit pas : **relance le jeu complètement**. Le patch-note le
  précise quand c'est le cas.

## 🗑 Désinstaller — la liste complète

**Avec le Hub** : onglet Traduction → **« Tout désinstaller »**. Il affiche
tout ce qu'il va supprimer *avant* de le faire, et te dit ce qui n'a pas pu
partir.

**À la main**, ferme le jeu puis supprime, dans le dossier de ton jeu :

| Quoi | Où | Pourquoi |
|---|---|---|
| `AscensionFR`, `AscensionFR_Repliques` | `Interface\AddOns\` | la traduction |
| **`PTRXML`** | **`Interface\`** | les écrans de connexion et de création de personnage. **C'est celui qu'on oublie** : sans lui, le jeu reste partiellement en français |
| `AscensionFR*.lua` (et `.bak`) | `WTF\Account\<compte>\SavedVariables\` | tes réglages de l'addon |
| `Sound\` (ou `Sound_off\`) | à la racine du jeu | les voix françaises, si tu les avais installées. Les sons d'origine reviennent tout seuls : ils sont dans `Data\` |
| `Wow.ini` (`Language=fr`) | à la racine du jeu | posé par le pack de voix. Sans les voix il ne fait plus rien — tu peux le laisser |

Et, en dehors du jeu : le dossier `%APPDATA%\AscensionFR` (les réglages du
Hub).

> ⚠️ Vider `%APPDATA%` **ne remet pas** le jeu en anglais : il n'y a là que
> les réglages du Hub. Tout ce qui traduit le jeu est **dans le dossier du
> jeu**, dans la liste ci-dessus.

**100 % réversible** : aucun fichier d'origine du jeu n'est modifié.

## 🚑 Dépannage express

| Symptôme | Remède |
|---|---|
| **Tout est resté en anglais** | Les trois causes, dans l'ordre : ① le zip a été extrait au mauvais endroit (tu dois avoir `Interface\AddOns\AscensionFR`, **pas** `Interface\AddOns\Interface\AddOns\AscensionFR`) ; ② la case **« Allow Non-Launcher AddOns »** n'est pas cochée à l'écran des personnages ; ③ **« Activer la traduction »** est décochée dans `/afr`. Le Hub vérifie les trois d'un bouton. |
| La ligne AscensionFR dit « Not a Launcher AddOn » | Coche **« Allow Non-Launcher AddOns »** (juste au-dessus de « Load out of date AddOns ») |
| C'était en français, ça ne l'est plus d'un coup | Un clic **droit** sur le bouton de la minicarte coupe la traduction. Retape `/afr` et recoche « Activer la traduction » |
| C'était en français, un texte précis ne l'est plus | Le jeu a été mis à jour — envoie ton rapport, ce sera dans la prochaine version |
| J'ai désinstallé et c'est toujours en français | Il te reste `Interface\PTRXML` et/ou le dossier `Sound\` — voir le tableau ci-dessus |
| Le Hub dit « sauvegarde illisible » | Lance le jeu une fois, puis déconnecte-toi (ou `/reload`) : le jeu n'écrit sa sauvegarde qu'à ce moment-là |
| DragonUI dit « module des options non installé » | Réinstalle DragonUI depuis le Hub (version 3.3.2+) : il pose maintenant les **deux** dossiers, `DragonUI` et `DragonUI_Options` |
| Autre chose | Passe sur le [Discord](https://discord.gg/kFJGDJbeay) 💬 |
