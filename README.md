# Red — assistant vocal local

Dis « Red », puis ta demande. Red utilise Vosk pour le réveil, Whisper pour la
transcription, Ollama pour les réponses et Chatterbox Multilingual pour la voix.
Piper Tom puis la voix Windows servent de secours. La personnalité par défaut
est calme, concise et polie, avec un humour discret.

## Lancer sur ce PC

Double-clique sur `lancer_red.bat`. Pour une nouvelle installation Windows,
utilise `installer_red.bat`, puis `installer_chatterbox.bat` pour la voix personnalisée.
Les modèles nécessitent un téléchargement initial ; la conversation locale et
la synthèse utilisent ensuite les modèles de ce PC.

```powershell
.venv-red\Scripts\python.exe -m assistant_vocal --check
.venv-red\Scripts\python.exe -m assistant_vocal
.venv-red\Scripts\python.exe -m assistant_vocal --admin-only
```

Le démarrage est sans interface graphique. Le panneau facultatif se consulte
sur `http://127.0.0.1:8790/panneau` (port configurable). Aucun navigateur ne
s'ouvre automatiquement. `admin.enabled: false` supprime les routes administratives.
Le panneau refuse le LAN, les tunnels, les origines étrangères et les écritures
sans JSON. Pour ajouter son mot de passe administrateur unique sur ce PC :

```powershell
.venv-red\Scripts\python.exe -m assistant_vocal --admin-password
```

Sans ce mot de passe, l'accès est réservé aux processus locaux et à la session
Windows. Avec le mot de passe, une connexion expire après quinze minutes.
Ce verrou ne crée aucun compte utilisateur.

## Utilisation

- « Quelles sont les fonctionnalités actuelles ? » donne les fonctions disponibles.
- « Mets-toi en veille » demande confirmation, sans réciter des réponses possibles.
- « Stop » interrompt la parole ; « arrête Red » ferme l'assistant, pas Windows.
- Les changements de mémoire demandent toujours validation. Les souvenirs n'ont
  pas de durée d'expiration. L'historique concerne les changements, conserve
  sept jours et ne se modifie pas. Les zones protégées gardent leurs conditions
  d'accès et leur chiffrement. Voir les [détails mémoire](docs/memoire.md).

## Configuration et extensions

Copie `config.example.yaml` vers `config.yaml` seulement sur une nouvelle installation.
La configuration actuelle est conservée par l'installateur. Les clés historiques
sont migrées par `core/config.py`, puis écrites atomiquement au prochain changement.
Ne versionne ni cette configuration, ni les WAV personnels, ni les bases mémoire.

- [Voix WAV et paramètres Chatterbox](docs/chatterbox.md)
- [Ajouter un module sans modifier les composants centraux](docs/modules.md)
- [Rapport de refonte, décisions et limites](docs/refonte-rapport.md)
- [Audit initial de la branche refonte](docs/refonte-audit.md)
- [Contexte, appareils et événements](docs/architecture.md)
- [Protocole des satellites existants](docs/satellite.md)

Les moteurs techniques vivent dans `services/`, la conversation dans
`conversation/`, les adaptateurs réseau dans `transports/`, et le panneau dans
`interfaces/admin/`. Les modules peuvent enregistrer des outils, événements,
capacités et routes administratives. Home Assistant et MQTT restent des
intégrations futures ; aucun multi-utilisateur n'est ajouté dans cette phase.

## Dépendances

```powershell
# Depuis le dépôt, dans l'environnement Python 3.13 :
python -m pip install -e ".[local]"
# Installer seulement les intégrations souhaitées, par exemple :
python -m pip install -e ".[cloud,agenda,discord]"
```

Le socle contient configuration, HTTP client et cryptographie. Extras disponibles :
`speech`, `admin`, `desktop`, `local` (les trois précédents), `cloud`, `calls`,
`discord`, `agenda`, `alexa`, `obs`, `browser`, `mcp`, `cuda`, `dev`.
Hue et Spotify utilisent le client HTTP du socle. Chatterbox garde ses dépendances
figées dans `requirements-chatterbox.txt`, avec son Python 3.11 séparé : ne les
installe pas dans `.venv-red`. Un Pi peut utiliser uniquement
`satellite_pi/requirements.txt` et son client existant, sans installer le serveur.

Les intégrations existantes restent facultatives et nécessitent leur propre
configuration. Leur présence dans le registre ne garantit pas que leurs appareils
ou comptes externes sont connectés. Les anciens HUD, overlay et cockpit ne sont
plus chargés au lancement ; leurs fichiers restent temporairement dépréciés.
