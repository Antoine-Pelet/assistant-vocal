# Achèvement de la modularisation — 21 octobre 2026

L'inventaire initial reste dans `refonte-audit.md` ; le rapport de la première
phase décrit les 328 tests validés avant cette évolution. Cette seconde lecture
porte sur le dépôt actuellement refactorisé, et non sur la version historique.

## État constaté avant modification

- `assistant_vocal` assure déjà le bootstrap, l'instance unique et l'arrêt.
- `services` isole STT, TTS (Chatterbox, Piper, Windows et ancien ElevenLabs), LLM.
- `conversation` est commun au microphone local et aux satellites ; il contient
  encore trois branches exécutant directement Astra, Vision et Hermes.
- `core/capabilities.py` publie des objets mais ne sait pas exécuter une action.
- `ModuleManager` découvre les manifests JSON et gère le cycle de vie ; seul
  `demo` utilise cette API. Le panneau ne présente pas les modules.
- `core/routage_intentions.py` concentre des heuristiques métier. `audio/local.py`
  démarre directement Hue, Alexa, appels, Discord, présence, gestes et scènes.
- Le HUD et l'overlay sont inactifs au démarrage, mais des appels devenus sans
  effet et quelques imports optionnels persistent.
- Les anciens outils restent découverts automatiquement ; certains SDK cloud
  sont facultatifs. Le contrôle PC, Vision et Hermes dépendent de leur propre
  configuration et ne deviennent pas des moteurs locaux par cette refonte.
- La mémoire persistante, son chiffrement, ses propositions à confirmer et son
  historique de changements de sept jours sont conservés sans migration de données.

## Trajet retenu

`entrée audio/transport → conversation → registre de capacités → contrôle
N1/N2/N3 existant → module ou adaptateur d'outil → résultat conversationnel`.

Le registre publie aussi les contrats techniques déjà utilisés (`home.devices`,
`events.local`). Le module de compatibilité conserve les anciens outils et leurs
heuristiques. Les trois fonctionnalités ciblées possèdent leurs propres routes
et capacités. Une capacité en attente est révoquée si son module s'arrête.

Aucun système multi-utilisateur, aucun nouveau transport réseau et aucune
dépendance de framework ne sont ajoutés. Les références historiques nécessaires
aux imports, modèles et données existantes gardent des alias explicites.
