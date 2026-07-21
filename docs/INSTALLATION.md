# 📥 Installation — le guide complet

Deux façons d'installer, au choix. Les deux donnent **exactement la même
traduction**.

| | 🖥️ **Avec le Compagnon** | 📁 **À la main** |
|---|---|---|
| Pour qui | ceux qui veulent le plus simple | ceux qui préfèrent ne rien exécuter |
| Comment | double-clic, un bouton | extraire un zip |
| Mises à jour | **en un clic** (et l'appli se met à jour toute seule) | re-télécharger le zip |
| Signaler un souci | **un bouton, ça part tout seul** | copier-coller sur le Discord |

## 🖥️ Avec le Compagnon (le plus simple)

1. **[Télécharge `AscensionFR_Compagnon.exe`](../../../releases/latest)** et
   pose-le où tu veux (bureau, dossier du jeu…).
2. Double-clique dessus : il **trouve ton jeu tout seul** (et si ce n'est pas
   le bon dossier, il t'en propose un — tu confirmes d'un clic).
3. Clique sur **« Installer la traduction »**. C'est fini. 🎉

> 🛡️ Au premier lancement, Windows peut afficher un écran bleu « Windows a
> protégé votre ordinateur » : c'est le lot de tout programme non signé d'un
> petit projet. Clique **« Informations complémentaires » → « Exécuter quand
> même »**. Le [code source est public](../compagnon/) si tu veux vérifier ce
> qu'il fait.
>
> 🔐 Si ton jeu est dans `C:\Program Files`, Windows protège ce dossier :
> le Compagnon te proposera un bouton **« Relancer en administrateur »**,
> accepte et tout se déroulera normalement.

### Les petits plus du Compagnon

- **À la fermeture du jeu**, il te propose d'envoyer tes découvertes (voir
  [Contribuer](CONTRIBUER.md)) — jamais d'envoi sans ton clic.
- **« Démarrer réduit »** : il veille en silence et ne se montre que s'il y a
  du nouveau.
- **« Tout va bien ? »** : un diagnostic en un clic — dossier du jeu, version
  de l'addon, sauvegarde — avec la marche à suivre si quelque chose cloche.

## 📁 À la main (2 minutes, que des fichiers)

C'est une traduction : rien que des fichiers d'addon (`.lua` / `.xml`), du
texte que tu peux ouvrir et lire. **Aucun programme à installer, aucun `.exe`.**

1. **[Télécharge `AscensionFR_manuel.zip`](../../../releases/latest).**
2. **Extrais-le dans le dossier de ton jeu Ascension** — celui qui contient
   déjà un dossier `Interface` (souvent `…\resources\ascension-live`).
   Windows te demande de **fusionner le dossier `Interface`** → dis **oui**
   (ça n'efface aucun de tes autres addons, ça ajoute les nôtres à côté).
3. Lance le jeu jusqu'à l'écran de **sélection des personnages**. En bas à
   gauche, clique sur **« AddOns »**, coche **« Load Out of Date AddOns »**
   (charger les AddOns périmés) en haut, vérifie qu'**AscensionFR** est
   coché, puis **Applique**.
4. Connecte-toi. **C'est en français !** 🎉

> ✅ Tu dois obtenir `Interface\AddOns\AscensionFR`,
> `Interface\AddOns\AscensionFR_Repliques` et `Interface\PTRXML`.
> L'extraction place tout au bon endroit toute seule.
>
> 💡 Le bouton **« AddOns »** à la sélection des personnages est la méthode
> qui marche à tous les coups. Inutile de chercher une case dans le lanceur :
> selon les versions elle change de nom ou n'existe pas.

## 🔄 Mettre à jour

- **Compagnon** : il te prévient et tout se fait en un clic.
- **À la main** : extrais le nouveau zip par-dessus (dis « oui » pour
  remplacer), puis `/reload` en jeu ou reconnecte-toi. Tes réglages sont
  conservés.
- ⚠️ Quand une version ajoute de **nouveaux fichiers** à l'addon, un simple
  `/reload` ne suffit pas : **relance le jeu complètement**. Le patch-note le
  précise quand c'est le cas.

## 🗑️ Désinstaller

Supprime les dossiers `AscensionFR` et `AscensionFR_Repliques` dans
`Interface\AddOns`, et `PTRXML` dans `Interface`. C'est tout — **100 %
réversible**, aucun fichier du jeu n'a été modifié.

## 🚑 Dépannage express

| Symptôme | Remède |
|---|---|
| Tout est resté en anglais | Vérifie que l'addon est coché à l'écran des personnages (bouton **AddOns**, case « Load Out of Date AddOns ») |
| C'était en français, un texte précis ne l'est plus | Le jeu a été mis à jour — envoie ton rapport, ce sera dans la prochaine version |
| Le Compagnon dit « sauvegarde illisible » | Lance le jeu une fois, puis déconnecte-toi (ou `/reload`) : le jeu n'écrit sa sauvegarde qu'à ce moment-là |
| Autre chose | Passe sur le [Discord](https://discord.gg/kFJGDJbeay) 💬 |
