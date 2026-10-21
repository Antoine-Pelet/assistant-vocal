# Audit réel de la branche refonte — 25 septembre 2026

Base : `8a6f605` (`ajout memoire`), arbre Git propre avant ce travail. L’intégration utilisateurs préparée hors dépôt n’est pas appliquée. Ni comptes ni reconnaissance de locuteur dans cette phase.

## Constat et périmètre

Les 306 tests existants passent avant modification (19,3 s). Le point d’entrée réel est jarvis14.py (plus de 1 700 lignes), le transport satellite conserve son propre prompt et ses actions en attente. Le package déclaré ne contient qu’un lanceur runpy vers un fichier extérieur. Il n’existe pas encore de ModuleManager ni de CapabilityRegistry. Les contrats AudioData, ExecutionContext, Devices et EventBus sont déjà exploitables.

Configuration observée sans recopier de secrets : mode local, Whisper base CPU, Chatterbox profil reddington avec WAV présent, Piper Tom installé comme secours ; anciens identifiants jarvis_fr et jarvis_sarcastique. Overlay actif, cockpit inactif, serveur actif. Aucun utilisateur enrôlé. La mémoire existante et ses clés ne doivent pas être réinitialisées.

## Décisions transversales

- Chatterbox ACTIVE ; Piper Tom KEEP ; SAPI Windows KEEP (lecture confidentielle sans cache et ultime secours). Kokoro DELETE après retrait du catalogue, des imports et migration de sa clé. ElevenLabs DEPRECATED : non actif, compatibilité isolée temporaire, hors interface locale.
- Hue ACTIVE et encapsulé ; Alexa configuré ; Home Assistant/MQTT non implémentés. Spotify, Discord, OBS, appels/Twilio, Hermes/MCP, cloud OpenAI/Anthropic OPTIONAL : ne pas retirer une intégration au seul motif qu’elle est inactive ici.
- HUD/overlay/cockpit DEPRECATED, aucune initialisation en mode normal headless. Les données finances restent intactes. Le panneau d’administration reste l’unique interface pérenne.
- Aucune suppression de modèles, WAV, bases, logs utilisateurs ou environnements installés. Les téléchargements de reconnaissance préparés précédemment restent inertes, hors chargement et hors package.
- Les wrappers d’import utiles restent marqués DEPRECATED ; leur retrait est conditionné aux consommateurs directs, dynamiques, scripts, tests et outils MCP.

## Plan appliqué progressivement

1. Packaging réel, point d’entrée technique et démarrage headless ; validation imports, discovery et tests.
2. Runtime léger, manifeste explicite, cycle des modules, capabilities et module de démonstration ; tests activation/désactivation/arrêt.
3. Séparer sécurité/confirmations, conversation et transport ; un stockage des actions en attente, contexte conservé.
4. Providers STT/TTS/LLM, configuration versionnée et atomique, profils et personnalité Red, cache devices.
5. Administration optionnelle, catalogue backend et protection locale, retrait des détails inutiles ; dépendances et observabilité.
6. Tests complets, démarrage headless et génération réelle ; rapport des limites matérielles et de la compatibilité conservée.

## Inventaire fichier par fichier

Les lignes et consommateurs ci-dessous proviennent de la branche avant modification. KEEP pour un outil signifie conserver sa fonction ; la découverte dynamique par pkgutil reste un consommateur même en l’absence d’import statique. DELETE n’est pas déduit d’un compteur à zéro.

| Fichier | Lignes | Décision | Responsabilité / migration |
|---|---:|---|---|
| `Chrome + Jarvis.bat` | 3 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `Chrome + Red.bat` | 3 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `Chrome-Jarvis.ps1` | 31 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `config.example.yaml` | 514 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `contenus.example.yaml` | 18 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/__init__.py` | 1 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/arbitrage_micro.py` | 89 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/budget.py` | 262 | MOVE | Observabilité des coûts, pas infrastructure conversationnelle. |
| `core/chatterbox_tts.py` | 207 | MOVE | Service TTS actif ; préserver worker local isolé et référence Reddington. |
| `core/cloud.py` | 250 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/cockpit.py` | 237 | DEPRECATED | Seconde interface ; ne plus la monter par défaut, conserver données et fonctions finances. |
| `core/commandes_vocales.py` | 60 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/confidentialite.py` | 37 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/config.py` | 47 | REWORK | Écriture directe non atomique, pas de version ni validation ; migration centralisée. |
| `core/contexte.py` | 62 | KEEP | Contrat de domaine sain et indépendant du transport. |
| `core/conversation_audio.py` | 59 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/devices.py` | 122 | KEEP | Contrat de domaine sain et indépendant du transport. |
| `core/evenements.py` | 73 | KEEP | Contrat de domaine sain et indépendant du transport. |
| `core/fonctionnalites.py` | 99 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/gestes.py` | 592 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/hub_contenu.py` | 511 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/instance.py` | 33 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/interruption_vocale.py` | 42 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/journal.py` | 22 | MOVE | Logging technique assistant.* avec contexte. |
| `core/llm.py` | 371 | SPLIT | Providers indépendants et fabrique dans services/llm. |
| `core/maison.py` | 53 | MOVE | Composition Hue hors domaine ; catalogue mis en cache avec invalidation. |
| `core/memoire.py` | 51 | KEEP | Stockage/chiffrement/validation existants, sans refonte des données. |
| `core/memoire_api.py` | 97 | KEEP | Stockage/chiffrement/validation existants, sans refonte des données. |
| `core/memoire_crypto.py` | 293 | KEEP | Stockage/chiffrement/validation existants, sans refonte des données. |
| `core/memoire_crypto_legacy.py` | 21 | DEPRECATED | Lecture des anciennes empreintes nécessaire à migration de données ; ne pas supprimer. |
| `core/memoire_store.py` | 656 | KEEP | Stockage/chiffrement/validation existants, sans refonte des données. |
| `core/memoire_vocale.py` | 98 | KEEP | Stockage/chiffrement/validation existants, sans refonte des données. |
| `core/panneau.py` | 1077 | SPLIT | Contrôleur HTTP, catalogue, diagnostics et réglages mélangés. |
| `core/personnalite.py` | 40 | REWORK | Source unique persona Red et aliases de lecture transitoires. |
| `core/playwright_partage.py` | 15 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/pont_iphone.py` | 240 | MOVE | Transport facultatif ; garder authentification propre et restrictions N3. |
| `core/registre.py` | 318 | SPLIT | Découverte, niveaux et actions en attente mélangés ; isoler sécurité/confirmation. |
| `core/reveil.py` | 127 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/routage.py` | 177 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/routage_intentions.py` | 219 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/satellite.py` | 796 | SPLIT | Transport, modèle Whisper, prompt, boucle LLM et confirmation concurrente. |
| `core/serveur.py` | 178 | MOVE | Composition HTTP optionnelle et arrêt explicite, routes montées selon besoins. |
| `core/transactions.py` | 194 | MOVE | Fonctions métier finances existantes ; préserver données. |
| `core/tts.py` | 272 | SPLIT | Services TTS ; retirer Kokoro non installé ; ElevenLabs facultatif explicitement déprécié. |
| `core/util.py` | 47 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `core/voix.py` | 17 | DEPRECATED | Pont vers la sortie vocale locale ; garder le contrat utilisé par les outils. |
| `core/voix_locales.py` | 62 | REWORK | Un seul fallback Piper Tom ; aliases anciens migrés dans la configuration. |
| `finances/abonnements.example.yaml` | 41 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `gestes/regard.py` | 733 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `gestes/tracker.py` | 943 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `hud.html` | 948 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `hud.py` | 556 | DEPRECATED | Serveur/interface concurrents : désactivés headless ; vérifier consommateurs avant suppression. |
| `installer_chatterbox.bat` | 9 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `installer_red.bat` | 4 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `integrations/__init__.py` | 1 | KEEP | Adapter externe déjà séparé du domaine. |
| `integrations/hue.py` | 122 | KEEP | Adapter externe déjà séparé du domaine. |
| `jarvis/__init__.py` | 1 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `jarvis/mcp_server.py` | 143 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `jarvis14.py` | 1715 | SPLIT | Lanceur legacy uniquement ; extraire application, conversation et adaptateur audio local. |
| `lancer_jarvis.bat` | 2 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `lancer_red.bat` | 7 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `lancer_serveur_mcp.bat` | 12 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `mettre_a_jour_jarvis.bat` | 35 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `musique/reconnaisseur.py` | 68 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `overlay.py` | 490 | DEPRECATED | GUI Windows à désactiver hors compatibilité ; aucun démarrage implicite. |
| `pyproject.toml` | 60 | REWORK | Point d’entrée historique src/runpy ; déclarer le vrai package et séparer les extras. |
| `satellite_pi/calibrer_wake.py` | 93 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `satellite_pi/config.exemple.yaml` | 21 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `satellite_pi/jarvis_satellite.py` | 454 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `sauvegarder_jarvis.bat` | 44 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `scenes.example.yaml` | 42 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `scripts/alexa_login.py` | 302 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/autostart_install.ps1` | 52 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/autostart_uninstall.ps1` | 25 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/bench_memoire_crypto.py` | 54 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/chatterbox_worker.py` | 153 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/demarrer_jarvis_complet.ps1` | 41 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/doctor.py` | 281 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/gestes_calibrer.py` | 51 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/installer_chatterbox.ps1` | 33 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/installer_ollama_red.ps1` | 41 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/installer_red.ps1` | 29 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/lancer_red.ps1` | 36 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/preparer_chatterbox.py` | 31 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/preparer_red.py` | 89 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/regard_tester.py` | 20 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/satellite_test.py` | 167 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/setup.py` | 245 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/setup_gestes.py` | 57 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/setup_musique.py` | 54 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/setup_regard.py` | 23 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/spotify_login.py` | 124 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `scripts/tester_chatterbox.py` | 55 | KEEP | Entrée ou installation opérationnelle ; vérifier chemins après migration. |
| `services/__init__.py` | 36 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `services/existing.py` | 43 | DEPRECATED | Trois adaptateurs à remplacer par les services natifs puis retirer les usages. |
| `src/jarvis_vocal/__init__.py` | 11 | DEPRECATED | Lanceur package historique avec chemin cassé après installation wheel. |
| `tester_agenda.py` | 23 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `tester_instagram.py` | 38 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `tests/test_alexa_routing.py` | 133 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_arbitrage_micro.py` | 35 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_architecture_distribuee.py` | 257 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_astra_pc.py` | 78 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_commandes_naturelles.py` | 143 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_confidentialite.py` | 23 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_conversation_red.py` | 172 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_gestes_actions.py` | 48 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_gestes_modes.py` | 393 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_gestes_tools.py` | 131 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_hermes_tasks.py` | 78 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_hud_controls.py` | 91 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_media_routing.py` | 339 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_ollama_local.py` | 33 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_openai_provider.py` | 111 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_panneau_switches.py` | 44 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_chatterbox.py` | 202 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_dialogue.py` | 97 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_fonctions.py` | 50 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_memoire.py` | 418 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_memoire_crypto.py` | 111 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_memoire_vocale.py` | 100 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_red_panneau.py` | 91 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_regard.py` | 132 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_reveil.py` | 68 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_routage_intentions.py` | 71 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_satellite_audio.py` | 44 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_satellite_security.py` | 106 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tests/test_web_routing.py` | 95 | KEEP | Non-régression existante ; adapter uniquement les attentes legacy explicitement migrées. |
| `tools/__init__.py` | 5 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/agenda.py` | 408 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/alexa.py` | 755 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/amaran.py` | 105 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/appel_direct.py` | 413 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/appels.py` | 300 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/apps.py` | 233 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/astra_pc.py` | 289 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/audio.py` | 71 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/brief.py` | 36 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/budget.py` | 101 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/contenu.py` | 162 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/deleguer_a_hermes.py` | 505 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/discord_bot.py` | 185 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/ecran.py` | 141 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/factures.py` | 79 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/finances.py` | 421 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/fonctionnalites.py` | 9 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/gestes.py` | 201 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/google_home.py` | 177 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/instagram.py` | 316 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/loopstr.py` | 160 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/lumieres.py` | 117 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/mail.py` | 260 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/media.py` | 264 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/memoire.py` | 59 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/meteo.py` | 104 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/modes.py` | 88 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/musique.py` | 262 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/navigateur.py` | 486 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/notes.py` | 140 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/obs.py` | 147 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/panneau.py` | 35 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/personnalite.py` | 29 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/presence.py` | 102 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/reponses.py` | 120 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/reservation.py` | 349 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/scenes.py` | 219 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/souris.py` | 158 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/spotify.py` | 576 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/stats.py` | 44 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/suivi.py` | 353 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/systeme.py` | 201 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/temps.py` | 56 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `tools/web.py` | 34 | KEEP | Fonctionnalité découverte par pkgutil et @outil ; conserver contrat et contrôles. |
| `web/cockpit.html` | 164 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `web/memoire.js` | 181 | KEEP | Conserver comportement ; contrôler noms et imports lors des phases concernées. |
| `web/panneau.html` | 675 | REWORK | Administration uniquement : options conditionnelles, profils dynamiques, données minimales. |
