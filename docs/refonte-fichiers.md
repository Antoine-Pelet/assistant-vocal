# Inventaire final des fichiers

Comparaison du contenu de la branche `refonte` avec `8a6f605`, sans les différences
de seules fins de ligne. Les données privées et modèles ne font pas partie de cet
inventaire. Les décisions initiales sont dans [l’audit](refonte-audit.md) ; les
validations, compatibilités et limites sont dans [le rapport](refonte-rapport.md).

## Créés

- [`assistant_vocal/__init__.py`](../assistant_vocal/__init__.py)
- [`assistant_vocal/__main__.py`](../assistant_vocal/__main__.py)
- [`assistant_vocal/app.py`](../assistant_vocal/app.py)
- [`assistant_vocal/runtime.py`](../assistant_vocal/runtime.py)
- [`audio/__init__.py`](../audio/__init__.py)
- [`audio/local.py`](../audio/local.py)
- [`conversation/__init__.py`](../conversation/__init__.py)
- [`conversation/manager.py`](../conversation/manager.py)
- [`conversation/persona.py`](../conversation/persona.py)
- [`conversation/prompt.py`](../conversation/prompt.py)
- [`conversation/session.py`](../conversation/session.py)
- [`conversation/turn.py`](../conversation/turn.py)
- [`core/capabilities.py`](../core/capabilities.py)
- [`core/module.py`](../core/module.py)
- [`core/module_manager.py`](../core/module_manager.py)
- [`core/tool_registry.py`](../core/tool_registry.py)
- [`devices/__init__.py`](../devices/__init__.py)
- [`devices/catalog.py`](../devices/catalog.py)
- [`docs/modules.md`](../docs/modules.md)
- [`docs/refonte-audit.md`](../docs/refonte-audit.md)
- [`docs/refonte-rapport.md`](../docs/refonte-rapport.md)
- [`interfaces/__init__.py`](../interfaces/__init__.py)
- [`interfaces/admin/__init__.py`](../interfaces/admin/__init__.py)
- [`interfaces/admin/controller.py`](../interfaces/admin/controller.py)
- [`interfaces/admin/memory_api.py`](../interfaces/admin/memory_api.py)
- [`interfaces/admin/security.py`](../interfaces/admin/security.py)
- [`interfaces/admin/service.py`](../interfaces/admin/service.py)
- [`interfaces/server.py`](../interfaces/server.py)
- [`modules/__init__.py`](../modules/__init__.py)
- [`modules/demo/__init__.py`](../modules/demo/__init__.py)
- [`modules/demo/manifest.json`](../modules/demo/manifest.json)
- [`modules/demo/module.py`](../modules/demo/module.py)
- [`observability/__init__.py`](../observability/__init__.py)
- [`observability/budget.py`](../observability/budget.py)
- [`observability/logging.py`](../observability/logging.py)
- [`scripts/__init__.py`](../scripts/__init__.py)
- [`security/__init__.py`](../security/__init__.py)
- [`security/authorization.py`](../security/authorization.py)
- [`security/confirmations.py`](../security/confirmations.py)
- [`services/catalog.py`](../services/catalog.py)
- [`services/llm/__init__.py`](../services/llm/__init__.py)
- [`services/llm/anthropic.py`](../services/llm/anthropic.py)
- [`services/llm/factory.py`](../services/llm/factory.py)
- [`services/llm/models.py`](../services/llm/models.py)
- [`services/llm/ollama.py`](../services/llm/ollama.py)
- [`services/llm/openai.py`](../services/llm/openai.py)
- [`services/stt/__init__.py`](../services/stt/__init__.py)
- [`services/stt/faster_whisper.py`](../services/stt/faster_whisper.py)
- [`services/tts/__init__.py`](../services/tts/__init__.py)
- [`services/tts/base.py`](../services/tts/base.py)
- [`services/tts/chatterbox.py`](../services/tts/chatterbox.py)
- [`services/tts/elevenlabs.py`](../services/tts/elevenlabs.py)
- [`services/tts/factory.py`](../services/tts/factory.py)
- [`services/tts/piper.py`](../services/tts/piper.py)
- [`services/tts/profiles.py`](../services/tts/profiles.py)
- [`services/tts/windows.py`](../services/tts/windows.py)
- [`tests/test_admin_boundary.py`](../tests/test_admin_boundary.py)
- [`tests/test_config_migration.py`](../tests/test_config_migration.py)
- [`tests/test_conversation_manager.py`](../tests/test_conversation_manager.py)
- [`tests/test_modules_runtime.py`](../tests/test_modules_runtime.py)
- [`tests/test_refonte_lifecycle.py`](../tests/test_refonte_lifecycle.py)
- [`transports/__init__.py`](../transports/__init__.py)
- [`transports/iphone/__init__.py`](../transports/iphone/__init__.py)
- [`transports/iphone/server.py`](../transports/iphone/server.py)
- [`transports/satellite/__init__.py`](../transports/satellite/__init__.py)
- [`transports/satellite/audio.py`](../transports/satellite/audio.py)
- [`transports/satellite/protocol.py`](../transports/satellite/protocol.py)
- [`transports/satellite/server.py`](../transports/satellite/server.py)
- [`transports/satellite/session.py`](../transports/satellite/session.py)
- [`web/__init__.py`](../web/__init__.py)

## Déplacements et découpages

Le fichier de départ reste un raccord déprécié, sauf indication contraire.

| Départ | Implémentation actuelle |
|---|---|
| `jarvis14.py` | `assistant_vocal/app.py + audio/local.py + conversation/` |
| `core/llm.py` | `services/llm/` |
| `core/tts.py` | `services/tts/` |
| `core/chatterbox_tts.py` | `services/tts/chatterbox.py` |
| `core/voix_locales.py` | `services/tts/profiles.py` |
| `core/personnalite.py` | `conversation/persona.py` |
| `core/registre.py` | `core/tool_registry.py + security/` |
| `core/satellite.py` | `transports/satellite/` |
| `core/pont_iphone.py` | `transports/iphone/server.py` |
| `core/serveur.py` | `interfaces/server.py` |
| `core/panneau.py` | `interfaces/admin/controller.py + service.py` |
| `core/memoire_api.py` | `interfaces/admin/memory_api.py` |
| `core/maison.py` | `devices/catalog.py` |
| `core/budget.py` | `observability/budget.py` |
| `core/journal.py` | `observability/logging.py` |

## Modifiés

- [`DEMARRER_RED.md`](../DEMARRER_RED.md)
- [`INSTALL_WITH_AI.en.md`](../INSTALL_WITH_AI.en.md)
- [`INSTALL_WITH_AI.md`](../INSTALL_WITH_AI.md)
- [`README.en.md`](../README.en.md)
- [`README.md`](../README.md)
- [`config.example.yaml`](../config.example.yaml)
- [`core/arbitrage_micro.py`](../core/arbitrage_micro.py)
- [`core/budget.py`](../core/budget.py)
- [`core/chatterbox_tts.py`](../core/chatterbox_tts.py)
- [`core/cloud.py`](../core/cloud.py)
- [`core/cockpit.py`](../core/cockpit.py)
- [`core/config.py`](../core/config.py)
- [`core/gestes.py`](../core/gestes.py)
- [`core/hub_contenu.py`](../core/hub_contenu.py)
- [`core/journal.py`](../core/journal.py)
- [`core/llm.py`](../core/llm.py)
- [`core/maison.py`](../core/maison.py)
- [`core/memoire_api.py`](../core/memoire_api.py)
- [`core/panneau.py`](../core/panneau.py)
- [`core/personnalite.py`](../core/personnalite.py)
- [`core/pont_iphone.py`](../core/pont_iphone.py)
- [`core/registre.py`](../core/registre.py)
- [`core/reveil.py`](../core/reveil.py)
- [`core/routage.py`](../core/routage.py)
- [`core/routage_intentions.py`](../core/routage_intentions.py)
- [`core/satellite.py`](../core/satellite.py)
- [`core/serveur.py`](../core/serveur.py)
- [`core/transactions.py`](../core/transactions.py)
- [`core/tts.py`](../core/tts.py)
- [`core/voix.py`](../core/voix.py)
- [`core/voix_locales.py`](../core/voix_locales.py)
- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/chatterbox.md`](../docs/chatterbox.md)
- [`docs/cockpit.md`](../docs/cockpit.md)
- [`docs/local.md`](../docs/local.md)
- [`docs/overlay.md`](../docs/overlay.md)
- [`docs/panneau.md`](../docs/panneau.md)
- [`gestes/regard.py`](../gestes/regard.py)
- [`gestes/tracker.py`](../gestes/tracker.py)
- [`hud.py`](../hud.py)
- [`jarvis/__init__.py`](../jarvis/__init__.py)
- [`jarvis/mcp_server.py`](../jarvis/mcp_server.py)
- [`jarvis14.py`](../jarvis14.py)
- [`overlay.py`](../overlay.py)
- [`pyproject.toml`](../pyproject.toml)
- [`requirements-red.txt`](../requirements-red.txt)
- [`requirements.txt`](../requirements.txt)
- [`satellite_pi/calibrer_wake.py`](../satellite_pi/calibrer_wake.py)
- [`satellite_pi/jarvis_satellite.py`](../satellite_pi/jarvis_satellite.py)
- [`scripts/alexa_login.py`](../scripts/alexa_login.py)
- [`scripts/demarrer_jarvis_complet.ps1`](../scripts/demarrer_jarvis_complet.ps1)
- [`scripts/doctor.py`](../scripts/doctor.py)
- [`scripts/installer_chatterbox.ps1`](../scripts/installer_chatterbox.ps1)
- [`scripts/lancer_red.ps1`](../scripts/lancer_red.ps1)
- [`scripts/preparer_red.py`](../scripts/preparer_red.py)
- [`scripts/satellite_test.py`](../scripts/satellite_test.py)
- [`scripts/setup.py`](../scripts/setup.py)
- [`scripts/setup_gestes.py`](../scripts/setup_gestes.py)
- [`scripts/setup_musique.py`](../scripts/setup_musique.py)
- [`scripts/spotify_login.py`](../scripts/spotify_login.py)
- [`scripts/tester_chatterbox.py`](../scripts/tester_chatterbox.py)
- [`services/__init__.py`](../services/__init__.py)
- [`src/jarvis_vocal/__init__.py`](../src/jarvis_vocal/__init__.py)
- [`tester_instagram.py`](../tester_instagram.py)
- [`tests/test_architecture_distribuee.py`](../tests/test_architecture_distribuee.py)
- [`tests/test_panneau_switches.py`](../tests/test_panneau_switches.py)
- [`tests/test_red_chatterbox.py`](../tests/test_red_chatterbox.py)
- [`tests/test_red_dialogue.py`](../tests/test_red_dialogue.py)
- [`tests/test_red_memoire.py`](../tests/test_red_memoire.py)
- [`tests/test_red_panneau.py`](../tests/test_red_panneau.py)
- [`tools/agenda.py`](../tools/agenda.py)
- [`tools/alexa.py`](../tools/alexa.py)
- [`tools/amaran.py`](../tools/amaran.py)
- [`tools/appel_direct.py`](../tools/appel_direct.py)
- [`tools/appels.py`](../tools/appels.py)
- [`tools/apps.py`](../tools/apps.py)
- [`tools/astra_pc.py`](../tools/astra_pc.py)
- [`tools/budget.py`](../tools/budget.py)
- [`tools/contenu.py`](../tools/contenu.py)
- [`tools/deleguer_a_hermes.py`](../tools/deleguer_a_hermes.py)
- [`tools/ecran.py`](../tools/ecran.py)
- [`tools/factures.py`](../tools/factures.py)
- [`tools/google_home.py`](../tools/google_home.py)
- [`tools/instagram.py`](../tools/instagram.py)
- [`tools/loopstr.py`](../tools/loopstr.py)
- [`tools/navigateur.py`](../tools/navigateur.py)
- [`tools/notes.py`](../tools/notes.py)
- [`tools/panneau.py`](../tools/panneau.py)
- [`tools/personnalite.py`](../tools/personnalite.py)
- [`tools/reponses.py`](../tools/reponses.py)
- [`tools/reservation.py`](../tools/reservation.py)
- [`tools/scenes.py`](../tools/scenes.py)
- [`tools/souris.py`](../tools/souris.py)
- [`tools/spotify.py`](../tools/spotify.py)
- [`tools/suivi.py`](../tools/suivi.py)
- [`voices/README.md`](../voices/README.md)
- [`web/panneau.html`](../web/panneau.html)

## Supprimés

- `services/existing.py`

Le retrait de `services/existing.py` a été précédé d’une recherche des usages
directs, dynamiques, scripts, tests et documentation. Sa copie antérieure est
conservée dans `.red-install/refonte-delete-*`. Les anciens moteurs/profils retirés
à l’intérieur d’autres fichiers sont décrits dans le rapport.
