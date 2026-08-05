# ❓ Foire aux questions

**Je peux être banni ?**
Non. C'est un addon, le système officiellement autorisé par Ascension, qui ne
touche à aucun fichier du jeu et n'automatise rien.

**Ça marche sur la dernière version d'Ascension ?**
Oui. En cas de gros patch du jeu, une nouvelle version est publiée ici — le
Compagnon te prévient tout seul.

**Le Compagnon est-il obligatoire ?**
Non. L'[installation manuelle](INSTALLATION.md) marche exactement pareil, et
rien n'est jamais bloqué derrière l'application.

**Le Compagnon envoie-t-il mes données ?**
Non. Il ne contacte que GitHub (pour les mises à jour) et, si tu cliques sur
« Envoyer mon rapport », le salon du projet — avec **uniquement** des textes
du jeu et des numéros de sorts/objets. Rien d'automatique, rien de personnel :
le [code source](../compagnon/) le montre. Détail dans
[Contribuer](CONTRIBUER.md).

**Windows dit que le Hub est dangereux ?**
C'est SmartScreen : il alerte sur tout programme non signé d'un petit projet
(un certificat coûte plusieurs centaines d'euros par an). « Informations
complémentaires » → « Exécuter quand même ». Si tu préfères, l'installation
manuelle ne demande **aucun** programme.

**Mon antivirus SUPPRIME le fichier, je n'arrive même pas à le lancer.**
Ça arrive depuis la 2.2.1 : Windows Defender classe l'exe non signé en
trojan. C'est un faux positif, il est signalé à Microsoft. En attendant, ne te
bats pas avec ton antivirus — prends le zip, tu auras exactement la même
traduction :
**[⬇️ AscensionFR_manuel.zip](../../../releases/latest/download/AscensionFR_manuel.zip)**
(que des fichiers texte, rien à exécuter). Tu perds seulement la mise à jour
en un clic. Le [pas à pas est ici](INSTALLATION.md).

**J'ai installé et le jeu est toujours en anglais.**
Trois causes, toujours les mêmes : ① le zip a été extrait dans
`Interface\AddOns` au lieu du dossier du jeu ; ② la case **« Allow
Non-Launcher AddOns »** n'est pas cochée à l'écran de sélection des
personnages (bouton « AddOns », la case juste au-dessus de « Load out of date
AddOns ») ; ③ **« Activer la traduction »** est décochée dans `/afr`. Le Hub
vérifie les trois d'un bouton : **« Vérifier mon installation »**. Le détail
est dans le [guide d'installation](INSTALLATION.md#-dépannage-express).

**Un texte est resté en anglais, c'est normal ?**
Sur un jeu de cette taille, oui. Joue avec le Compagnon et
[envoie ton rapport](CONTRIBUER.md) : il sera traduit dans une prochaine
version. Si c'était en français avant, c'est que le jeu a changé ce texte —
même remède.

**Un texte est mal traduit ?**
Dis-le sur le [Discord](https://discord.gg/kFJGDJbeay) ou dans une
[issue](../../../issues) — c'est corrigé vite, et à la source.

**Comment désinstaller ?**
Le plus sûr : dans le Hub, onglet Traduction → **« Tout désinstaller »**. Il
liste tout ce qu'il va retirer avant de le faire.
À la main : supprime `AscensionFR` et `AscensionFR_Repliques` dans
`Interface\AddOns`, **`PTRXML` dans `Interface`** (celui-là s'oublie tout le
temps, et c'est lui qui laisse les écrans de connexion en français), tes
`AscensionFR*.lua` dans `WTF\Account\<compte>\SavedVariables`, et le dossier
`Sound` si tu avais installé les voix. Vider `%APPDATA%` ne sert à rien : il
n'y a là que les réglages du Hub. [La liste complète](INSTALLATION.md#-désinstaller--la-liste-complète).

**Pourquoi ce projet ?**
Ascension proposait un pack de langue français, mais il a été retiré car il
causait des bugs. Je voulais jouer dans ma langue — alors je l'ai refait
proprement : chaque traduction passe par un contrôle qui **refuse tout ce qui
pourrait casser le jeu** (c'est justement ce qui plantait avant). Le résultat
est là, gratuit, et il s'améliore à chaque rapport envoyé.

**Je peux aider autrement qu'en jouant ?**
Bien sûr : relectures et signalements sur le
[Discord](https://discord.gg/kFJGDJbeay), et si tu veux soutenir le temps
passé, [un café fait toujours plaisir](https://buymeacoffee.com/lepetitdan) ☕
— totalement optionnel, la traduction reste gratuite pour tous.
