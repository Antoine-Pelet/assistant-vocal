# Voix personnalisée locale

Le provider principal est Chatterbox Multilingual 0.1.7, en français. Les WAV
restent sur le PC et sont exclus de Git. Le worker interdit les connexions réseau
pendant la synthèse. Le filigrane audio du modèle est conservé.

## Installation

Après `installer_red.bat`, lance `installer_chatterbox.bat`. Cette installation
télécharge Python 3.11, les dépendances figées et les poids du modèle ; elle ne
remplace pas ta configuration. `.venv-chatterbox` est séparé du Python 3.13 de Red.
Pour installer exclusivement le moteur CPU :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/installer_chatterbox.ps1 -Cpu
```

Les modèles sont chargés depuis `models/chatterbox`. L'adaptation existante du
tokenizer français évite le téléchargement du segmentateur chinois, inutile pour
les réponses françaises. Aucun service cloud vocal n'est nécessaire.

## Référence et profils

Place une dizaine de secondes de voix claire dans `voices/`, une seule personne,
sans musique. Un WAV PCM mono est adapté. Le timbre final dépend de la référence.
Le dossier `voix/` est réservé au modèle Piper de secours.

```yaml
config_version: 2
tts:
  engine: chatterbox
  fallback_engine: piper
  profile: red
piper:
  profile: tom_fr
voices:
  red:
    name: Red
    reference: voices/reddington_reference.wav
    exaggeration: 0.25
    cfg_weight: 0.5
    temperature: 0.65
  autre:
    name: Autre voix
    reference: voices/autre_reference.wav
    exaggeration: 0.2
    cfg_weight: 0.45
chatterbox:
  modele: models/chatterbox
  python: .venv-chatterbox/Scripts/python.exe
  device: auto
  threads: 4
  startup_timeout: 600
  timeout: 180
```

Le nom affiché provient de `voices.<id>.name`. L'identifiant est libre ; le profil
déjà installé `reddington` est conservé sur ce PC et porte le nom affiché Red.
Change `tts.profile` puis redémarre, ou utilise le panneau pour appliquer le
changement à la prochaine réponse. Un nouveau WAV se déclare dans la configuration,
sans changer le code. Ne crée pas deux sections `tts` dans le même YAML.

| Paramètre | Utilité |
|---|---|
| `exaggeration` | Expressivité, intervalle accepté 0–2. |
| `cfg_weight` | Guidage, intervalle accepté 0–1. |
| `temperature` | Variabilité, intervalle accepté 0.05–2. |
| `device` | `auto` essaie CUDA, sinon CPU ; `cpu` force le CPU. |
| `threads` | Threads CPU, de 1 à 32. |
| `startup_timeout` | Première synthèse avec chargement du modèle ; 600 s par défaut. |
| `timeout` | Réponses suivantes ; 180 s par défaut. |

Le processus et les poids restent chargés entre les phrases. Un défaut CUDA
déclenche une tentative CPU. Si Chatterbox échoue, Piper Tom prend le relais ; la
lecture locale utilise SAPI Windows si aucun PCM n'est disponible. SAPI constitue
un secours du haut-parleur Windows, pas un moteur PCM pour les satellites.
L'interruption coupe la lecture ; elle ne garantit pas l'annulation instantanée
d'un calcul Chatterbox déjà commencé.

## Test strict, sans repli

```powershell
.venv-red\Scripts\python.exe scripts\tester_chatterbox.py
.venv-red\Scripts\python.exe scripts\tester_chatterbox.py --profil reddington --sortie logs/red-test.wav
```

Le script écrit un WAV, vérifie que l'audio n'est pas silencieux et affiche
l'appareil utilisé ainsi que le temps de génération. Pour une référence provisoire :
`--reference C:\Audio\reference.wav`. `--device cpu` force le CPU ;
`--timeout 600` fixe les deux délais pour ce test uniquement. Les logs du worker
sont dans `logs/chatterbox.log` et les diagnostics Red dans `logs/red.log`.

Kokoro et les anciens profils Piper à effet ont été retirés. Seul Tom est proposé
en secours. ElevenLabs reste un provider cloud déprécié, jamais appelé en mode local.
