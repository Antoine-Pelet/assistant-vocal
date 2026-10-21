# Refonte Red — bilan au 21 octobre 2026

Travail effectué sur la branche `refonte`, à partir de `8a6f605`. Aucun commit ni
publication automatique. L'[audit initial](refonte-audit.md) classe les fichiers
avant intervention. Le socle modulaire est en place et le fonctionnement local
est conservé. Le multi-utilisateur, la reconnaissance du locuteur, Home Assistant
et MQTT ne sont pas implémentés dans cette phase.

## Arborescence et responsabilités

```text
assistant_vocal/        __main__.py, app.py, runtime.py
audio/                 local.py : capture, restitution, interruption sur le PC
conversation/          manager, session, turn, prompt, persona
core/                  configuration, contexte, événements, devices, mémoire
                       module, module_manager, capabilities, tool_registry
security/              authorization, confirmations
services/              contrats AudioData/STT/TTS/LLM, catalogue
  stt/                 faster_whisper.py
  tts/                 factory, chatterbox, piper, windows, profiles, elevenlabs
  llm/                 models, factory, ollama, openai, anthropic
modules/demo/          manifest.json, module.py, __init__.py
devices/               catalog.py : composition et cache des appareils
integrations/          hue.py
transports/
  satellite/           protocol.py, server.py, session.py, audio.py
  iphone/              server.py
interfaces/
  admin/               controller.py, service.py, security.py, memory_api.py
  server.py            application HTTP et cycle de vie
observability/         logging.py, budget.py
tools/                 outils existants et auto-discovery conservés
web/                   panneau.html, memoire.js ; cockpit déprécié
scripts/               installation, diagnostic et worker Chatterbox
satellite_pi/          client existant, dépendances indépendantes du serveur
tests/                 non-régression et nouveaux contrats
```

Les packages restent à la racine du dépôt pour limiter les changements d'import.
`python -m assistant_vocal` et `red-assistant` sont les entrées normales.
`app.py` ne contient plus la boucle audio ni le raisonnement. Le runtime partage
les services paresseux, le catalogue d'appareils, le bus, la sécurité et les modules.
Les confirmations locales et satellites passent par le même gestionnaire, avec
un contexte de session distinct. Le transport satellite ne reconstruit plus sa
propre personnalité ni sa propre boucle LLM.

## Phases réalisées et vérifications

| Phase | Fichiers et décisions principales | Vérification et régressions |
|---|---|---|
| Audit | `docs/refonte-audit.md` : inventaire avant modification, décisions par fichier, migration progressive. | Référence initiale : 306 tests réussis. |
| Entrée et extensions | Création de `assistant_vocal/`, `core/module.py`, `module_manager.py`, `capabilities.py`, `modules/demo/`. `jarvis14.py` devient un raccord de compatibilité. Packaging corrigé. | 311 tests réussis, découverte des outils et du module désactivé, `--check`. |
| Moteurs et configuration | Providers déplacés de `core` vers `services`. Migration YAML v2, validation et remplacement atomique. Chatterbox principal, Piper Tom en secours. Cache des appareils dans `devices/catalog.py`. | 314 tests réussis. Écritures échouées sans corruption, migration idempotente, contrats audio sans périphérique imposé. |
| Conversation et sécurité | `conversation/`, `security/`, `core/tool_registry.py`. Contexte mémoire et confirmations partagés ; isolation des sessions. | 318 tests réussis. La mémoire déverrouillée localement ne devient pas accessible à un satellite. |
| Administration et transports | Contrôleur HTTP séparé du service, serveur et iPhone déplacés, satellite découpé, catalogues backend, protection locale et mot de passe facultatif. | Un test DELETE a été corrigé pour envoyer JSON : la garde rejetait correctement le mauvais Content-Type avant le 405 attendu. Parcours Edge réussi. |
| Finition et installation | `audio/local.py`, dépendances optionnelles, installateur idempotent, logs contextualisés, arrêt des ressources, retrait de `services/existing.py`, documentation. | Les attentes des tests ont été adaptées aux clés canoniques. Un import de l'installateur déclenchait une initialisation SSL : effet de bord déplacé vers son exécution. |
| Tests réels et paquet | WAV Chatterbox/Piper, STT, réveil, Ollama, démarrage borné, construction et installation du wheel dans un environnement isolé. | Le premier chargement Chatterbox a atteint le délai initial de 180 s : ajout de `startup_timeout` distinct. Le module exigeait FastAPI à l'enregistrement de sa route facultative : import différé, test sans FastAPI ajouté. **328 tests réussis** après correction. |

Les anciens chemins déplacés sont pour l'essentiel des alias vers une seule
implémentation, afin de conserver les imports des outils, scripts et tests. Il
n'y a pas deux copies actives des moteurs. Les sauvegardes de chaque application
se trouvent dans `.red-install/refonte-*`. Le retrait de l'adaptateur est sauvegardé
dans `.red-install/refonte-delete-*`. La configuration précédente est conservée
dans `.red-install/refonte-config-*.yaml` ; ces fichiers privés ne sont pas distribués.

La liste détaillée des fichiers créés, modifiés, déplacés et supprimés est dans
[l'inventaire final](refonte-fichiers.md). Les différences de seules fins de ligne
n'y sont pas comptées comme des changements fonctionnels.

## Composants retirés

- `services/existing.py` : supprimé après migration des usages, recherche dans le
  code, scripts, tests et documentation. Les tests utilisent les vrais contrats.
- Implémentation et sélection du moteur Kokoro ; section correspondante retirée
  lors de la migration de configuration.
- Profils Piper `siwis_fr` et `jarvis_fr`, et leur effet de personnage : sélection
  migrée vers `tom_fr`. Les anciens fichiers de modèles présents sur disque ne
  sont pas effacés automatiquement.
- Chargement automatique du HUD et de l'overlay, ouverture automatique du cockpit,
  route cockpit du serveur principal et outils d'affichage overlay dans la découverte.
- Dépendances cloud et intégrations imposées à toute installation : remplacées par
  des extras. Le gros fichier de dépendances exportées est remplacé par un raccord
  vers l'installation locale décrite dans `pyproject.toml`.

Aucun WAV personnel, modèle installé ou contenu mémoire n'a été supprimé par la
refonte. Le profil Chatterbox historique sans WAV et non sélectionné a été retiré
de la configuration de ce PC ; le profil `reddington` actif a été conservé.

## Compatibilités et éléments dépréciés

| Élément | Décision et raison |
|---|---|
| `jarvis14.py`, `jarvis-vocal`, `src/jarvis_vocal/` | DEPRECATED. Raccords pour les anciens imports/lanceurs. Le lancement actuel utilise `assistant_vocal`. |
| `core/llm.py`, `tts.py`, `chatterbox_tts.py`, `voix_locales.py`, `personnalite.py` | DEPRECATED. Alias vers les services et la personnalité partagée. |
| `core/registre.py`, `satellite.py`, `serveur.py`, `panneau.py`, `pont_iphone.py`, `memoire_api.py`, `maison.py`, `journal.py`, `budget.py` | DEPRECATED. Alias conservant les imports externes et les anciens tests. |
| `core/voix.py` | DEPRECATED. Petit raccord des anciens minuteurs/outils à la sortie audio ; aucun moteur propre. |
| `hud.py`, `hud.html`, `overlay.py`, `core/cockpit.py`, `web/cockpit.html`, `tools/reponses.py` | DEPRECATED. Pas de chargement ni serveur au lancement de Red ; restent pour les usages explicites et les tests historiques, avec données financières préservées. Leur suppression définitive est une migration séparée des consommateurs restants. |
| ElevenLabs | DEPRECATED, conservé comme provider optionnel pour une configuration cloud existante. Inutilisé en local et masqué dans le panneau lorsqu'inactif. |
| Personnalités neutre et concise | KEEP. Petits réglages encore accessibles à la voix ; la personnalité par défaut est Red. |

Les références Jarvis restantes ne sont pas toutes supprimées : les noms des
scripts BAT/PowerShell, la tâche Windows `JarvisAutostart`, le profil navigateur
`ChromeJarvis`, le nom MCP enregistré dans Hermes et les en-têtes iPhone restent
compatibles avec les installations existantes. Les renommages de ces identités
externes exigeraient de migrer aussi leurs clients et données.

`hey_jarvis_v0.1.onnx` désigne réellement un modèle openWakeWord pré-entraîné utilisé
par l'ancien client Pi : le renommer ne le ferait pas reconnaître « Red ». Le PC
utilise Vosk et le mot configuré `red`. Des tests contiennent encore les anciens
noms pour vérifier la migration. Les guides historiques sont signalés comme tels ;
le README, le guide Chatterbox et le guide des modules décrivent l'architecture actuelle.

## Voix et configuration conservées

**Chatterbox Multilingual → Piper Tom → SAPI Windows** constitue la chaîne locale.
CUDA est essayé automatiquement ; le worker garde un repli CPU. SAPI est un secours
de restitution sur Windows et ne fournit pas de PCM aux satellites.

Sur ce PC, `tts.engine: chatterbox`, `tts.profile: reddington`, `voices.reddington.name: Red`
et `piper.profile: tom_fr` conservent le WAV et les paramètres existants. Un nouveau
profil se déclare dans `voices`, puis se sélectionne avec `tts.profile` : le panneau
utilise ses métadonnées, sans table JavaScript de noms historiques.

`config_version: 2` centralise la migration des anciennes clés. L'installateur
conserve les choix existants ; les changements depuis le panneau valident une copie
avant remplacement atomique. La mémoire persistante, son chiffrement et ses règles
de confirmation ne sont pas réécrits par cette migration.

## Intégrations

| Intégration | Décision |
|---|---|
| Hue | ACTIVE dans la configuration existante ; adapter local derrière `Devices`. Aucun ordre matériel exécuté pendant les tests. |
| Ollama | ACTIVE, service LLM local. |
| OpenAI, Anthropic | OPTIONAL, SDK chargés à l'usage ; extra `cloud`. |
| Hermes et MCP | OPTIONAL, outils existants conservés ; pas le cœur de Red. |
| Twilio et tunnel ngrok | OPTIONAL, extra `calls`, routes montées seulement si configurées. |
| Discord, Google Agenda/iCal | OPTIONAL, extras `discord` et `agenda`. |
| OBS, Alexa | OPTIONAL, extras `obs` et `alexa` ; aucune connexion nouvelle effectuée. |
| Spotify, Instagram, mail, météo, web, amaran | OPTIONAL, outils existants préservés ; nécessitent leurs appareils/comptes/réseau selon leur fonction. |
| Navigateur/réservations | OPTIONAL, extra `browser`, aucun navigateur ouvert au lancement vocal. |
| Google Home expérimental | OPTIONAL, historique, toujours à valider avec le matériel cible. |
| Home Assistant, MQTT | FUTURE. Interfaces de devices et événements préparées, aucun service ajouté. |

## Administration

Le panneau reste unique, facultatif et administratif. Les routes vérifient
l'adresse de connexion, Host/Origin, les en-têtes de proxy et le Content-Type des
écritures. Un mot de passe unique peut être défini par `--admin-password` : stockage
Argon2id, cookie HttpOnly/SameSite Strict, session de quinze minutes et limitation
des échecs. **Aucun mot de passe n'a été choisi à la place du propriétaire.** Sans
ce verrou, la protection repose sur l'accès local au PC et sa session Windows.

Retraits/masquages : cockpit, montages Docker/Hermes détaillés, moteurs et voix
obsolètes, champs ElevenLabs inactifs, budget cloud et activités Hermes inactives.
Les catalogues vocaux et de modèles sont fournis par le backend.

Les chemins de montages Hermes et l'URL précise du tunnel ne sont plus retournés
par les vues concernées. Les métadonnées vocales contiennent ID, nom, disponibilité
et sélection, sans chemin du WAV. Les mots de passe, clés, hashes d'authentification
et contenus de zones verrouillées ne sont pas exposés par les routes testées.
Les noms de périphériques audio restent affichés pour permettre leur choix.

Le listener LAN satellite existant reste séparé du listener d'administration
loopback : il ne publie que `/satellite`. Ce deuxième port spécialisé conserve la
frontière réseau existante ; aucun serveur HUD concurrent n'est démarré.

## Chargement sans interface graphique

Le lancement normal initialise configuration, sécurité, outils disponibles, mémoire,
bus, appareils et modules activés ; le transport local charge Whisper et Vosk,
ouvre le micro et utilise les services LLM/TTS partagés. Chatterbox charge ses poids
à la première synthèse. L'administration démarre si configurée. Les SDK et modules
facultatifs ne sont pas tous imposés à l'installation.

`--check` vérifie les imports, la configuration et les extensions sans micro ni
modèle lourd. Le test de démarrage a confirmé l'absence de `hud`, `overlay`,
`tkinter`, cockpit et navigateur dans les imports, et l'arrêt du serveur, des
sessions et des ressources partagées. Les anciens outils non convertis peuvent
encore posséder leurs tâches de fond propres : voir la dette restante.

## Résultats et limites des tests

- **328 tests automatisés réussis**, suite finale du 21 octobre 2026 : mémoire,
  chiffrement, confirmation obligatoire, N1/N2/N3, configuration, contexte, events,
  devices/Hue simulé, transports, services, modules et sécurité du panneau.
- Wheel construit puis installé dans un environnement neuf avec le seul socle.
  `--check` fonctionne. `demo_ping`, capacité, événement, santé et arrêt du module
  fonctionnent sans FastAPI, Whisper ni Torch. Les ressources web, le manifeste et
  le worker sont présents ; aucun WAV/base/configuration personnelle n'est embarqué.
  L'outil téléphonique direct est absent de cette installation minimale, faute de
  dépendance `audioop` de l'extra `calls`, sans empêcher le démarrage.
- Parcours Edge réalisés : mémoire proposée puis validée, annulation, modification,
  zone chiffrée, refus du mauvais secret, verrouillage, historique masqué, login/logout
  administrateur, profil vocal dynamique, écriture canonique, repli Piper conservant
  Chatterbox. Aucune erreur JavaScript dans ces parcours.
- Test audio réel conservé : Chatterbox sur **CUDA**, **4,00 s à 24 kHz**, génération
  avec premier chargement **124,12 s** ; retranscription Whisper : « Très bien,
  monsieur. Monsieur, je suis prêt à vous écouter. » La répétition de « Monsieur »
  dans cette synthèse illustre que le contrôle automatique ne garantit pas une
  diction parfaite à chaque génération.
- Piper réel : **9,25 s** avec chargement, phrase correctement transcrite. Référence
  Chatterbox volontairement absente dans un processus de test : repli Piper réel.
  Réveil « Red » détecté sur un signal Piper par Vosk avec validation Whisper.
- Ollama local : réponse « Deux plus deux fait quatre. », **9,75 s** au test.
- Démarrage/arrêt borné validé avec une entrée PCM synthétique, aucun ordre Hue ou
  scène exécuté et mémoire temporaire. Lors de la reprise du 21 octobre, le casque
  configuré est détecté ; Red était déjà en cours d'exécution. Le second démarrage
  a été refusé par le verrou d'instance. **Pas de nouvelle capture réelle du casque**
  ni d'interruption de l'instance existante pour forcer ce test.
- Pas de test matériel de bout en bout sur un Raspberry Pi, une lampe Hue ou les
  services cloud. Leur protocole/contrat est testé, pas leur disponibilité réelle.

Les résultats et WAV de validation se trouvent, sur ce poste, dans
`C:\Users\antoi\Desktop\codex\red-refonte-validation`. Les tests mémoire utilisent
des bases temporaires ; aucune commande n'a demandé d'effacer la mémoire personnelle.

## Dette restante et suites possibles

1. Migrer progressivement les consommateurs des alias `core/*`, scripts historiques
   et intégrations externes, puis retirer les fichiers dépréciés avec leurs tests.
2. Réduire encore `audio/local.py` et le service administratif, qui conservent une
   partie de la logique historique ; découper selon des besoins concrets.
3. Convertir les anciens outils à tâches de fond en modules avec arrêt explicite.
   Le runtime ne connaît pas chaque fonctionnalité et ne peut pas fermer une
   ressource historique qui ne lui déclare pas son cycle de vie.
4. Poursuivre la centralisation des routes prioritaires historiques Astra/Hermes/vision.
   Les nouveaux modules peuvent déjà ajouter leurs outils sans ces routes spécifiques.
5. Réduire la latence de la première voix Chatterbox sur ce matériel ; le délai de
   démarrage séparé évite un abandon trop tôt, mais ne rend pas le modèle plus rapide.
6. Tester avec les appareils réels avant de déployer de nouveaux satellites ; ajouter
   ensuite des adapters Home Assistant/MQTT sans dépendance dans les modules métier.

## Ajouter une fonctionnalité

Créer `modules/<id>/__init__.py`, `manifest.json`, `module.py`, implémenter
`register/start/stop/health`, puis ajouter `modules.<id>.enabled: true` dans la
configuration. `ModuleAPI` expose outils, événements, capacités, nettoyage et
routes administratives. Les outils peuvent déclarer `permission_level="N3"`
sans modifier une liste centrale. Aucun changement spécifique dans le runtime,
le registre, le gestionnaire de conversation ou le panneau n'est nécessaire.
Le [guide des modules](modules.md) donne un exemple complet et les règles de sécurité.
