# Achèvement de la refonte modulaire — 22 octobre 2026

Cette phase poursuit le travail documenté dans `refonte-rapport.md`. Elle ne crée
aucun compte, profil utilisateur, reconnaissance de locuteur ni permission par
utilisateur. L'analyse préalable est dans `refonte-capabilities-audit.md`.

## Changements livrés

- `CapabilityRegistry` exécute des actions avec schéma, propriétaire, alias,
  intentions et N1/N2/N3. `LegacyToolAdapter` préserve les anciens outils.
- `modules/computer`, `vision`, `hermes` possèdent leurs routes et capacités.
  La conversation et le runtime n'importent plus ces outils et ne testent plus
  `decision.type`. Les autres heuristiques vivent dans `modules/legacy_tools`.
- `demo.hello` valide l'ajout d'une fonctionnalité par dossier et configuration.
  Un test crée aussi un module neuf dans un dossier temporaire et vérifie route,
  exécution et apparition dans les données du panneau sans changement central.
- Les capacités appliquent la politique existante. La prise de contrôle Astra
  explicite demande désormais la confirmation N3 que son ancienne route sautait.
  Arrêter un module invalide aussi ses actions en attente ; un alias ne diminue
  jamais le niveau de sécurité. La mémoire garde son propre mécanisme de validation.
- `RedApplication` orchestre démarrage et arrêt ; `jarvis14.py` reste un alias.
  `audio/local.py` ne démarre plus directement les intégrations métier. Le contrat
  `LocalAudioEndpoint` et un événement local permettent de brancher les hooks.
- Le panneau existant possède l'onglet **Modules**, alimenté génériquement : nom,
  version, état, santé et nombre de capacités. L'activation reste dans le YAML,
  avec redémarrage. Les protections locales et le mot de passe facultatif restent.
- Le HUD permanent et l'overlay ne sont pas chargés. Le retour Hermes n'importe
  plus ces interfaces ; le suivi de ses tâches et leurs annonces sont conservés.
- `mettre_a_jour_red.bat`, `sauvegarder_red.bat`, `Chrome-Red.ps1` remplacent les
  noms historiques ; les anciens lanceurs redirigent vers eux. Les nouvelles
  sessions Hermes portent Red. Le profil Chrome historique conserve son chemin
  pour préserver les sessions existantes ; les alias et noms de modèles nécessaires
  ne sont pas renommés aveuglément.
- Journalisation partagée ; les textes de conversation ne sont pas ajoutés au
  journal technique par la boucle audio. Arrêt déclaré des hooks, des raccourcis
  gestes, du service présence et du bot Discord. Les retours vocaux d'un ancien
  travail Hermes sont invalidés à l'arrêt du module.

## Validation

- **343 tests réussis en 11,25 s**, dans une configuration et une base temporaires.
  Résultat final dans `red-refonte-validation/capabilities-tests-final.log` sur ce poste.
- Panneau testé dans Edge headless avec mot de passe temporaire : onglet Modules,
  voix dynamiques, réglage du secours vocal et connexion/déconnexion ; zéro erreur JS.
- Paquet wheel construit et installé hors du dépôt, dans un environnement minimal
  sans FastAPI, Torch ou Whisper. Les manifests et ressources sont inclus, aucun
  WAV personnel, aucune configuration personnelle et aucune base mémoire.
- Démarrage réel des composants sur **PCM synthétique** : huit blocs, réveil chargé,
  serveur arrêté, flux fermé, modèles libérés, aucun module GUI importé. Les actions
  domotiques étaient neutralisées et la mémoire isolée. Ce n'est pas un test de
  reconnaissance depuis le casque réel.
- Les générations Chatterbox/Piper et la latence d'Ollama ont été mesurées lors
  de la phase précédente. Leurs moteurs ne sont pas réécrits dans cette phase.
  Aucune prise de contrôle du PC ni délégation cloud réelle n'est déclenchée par
  les tests de routage ; leurs interfaces sont testées avec des doublures.

Les scripts et résultats de validation se trouvent dans
`C:/Users/antoi/Desktop/codex/red-refonte-validation` et dans les scripts
`validate_modules_*` du dossier de travail. Les fichiers remplacés sont sauvegardés
sous `.red-install/refonte-<date>-<heure>`. Aucun commit n'est créé automatiquement.

## Limites conservées volontairement

`legacy_tools` est un pont de migration : ses fonctions restent dans `tools/`.
Les clients MCP/iPhone historiques conservent leur frontière de sécurité et leurs
outils ; leur protocole n'est pas remplacé. Le module de compatibilité contient
encore plusieurs initialisations techniques historiques, à répartir progressivement
si ces intégrations ont besoin de devenir des modules indépendants.

Les travaux externes déjà soumis à Hermes ne sont pas annulés côté serveur à
l'arrêt de Red ; leur suivi peut finir, mais leur annonce vocale est révoquée.
Les opérations ponctuelles de démarrage déjà engagées restent bornées par leurs
clients respectifs. Il n'y a pas de gestion distribuée de tâches ou de hot reload.

La santé ACTIVE signifie que le module est chargé. La disponibilité d'Astra,
d'Hermes, de la vision cloud et des appareils dépend de leur configuration et de
leurs services. Le mode vocal local conserve Ollama/Whisper/Chatterbox/Piper/SAPI.
Le contrôle PC et la vision cloud ne deviennent pas hors ligne par cette refonte.

La boucle audio locale et le service administratif restent assez volumineux.
Leur découpage supplémentaire doit répondre à un besoin réel ; le bootstrap,
la conversation et les modules sont désormais séparés. Home Assistant, MQTT et
les futurs appareils peuvent utiliser les contrats de contexte/devices/événements
existants, sans être ajoutés à ce chantier.

Pour prendre en compte les fichiers installés, fermer normalement Red puis relancer
`lancer_red.bat`. Le [guide des modules](modules.md) décrit l'API et la migration.
