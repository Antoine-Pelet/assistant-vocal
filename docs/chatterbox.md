# Voix personnalisées locales avec Chatterbox

Red propose **Chatterbox Multilingual TTS 0.1.7**, en français, à partir d'une
référence WAV. La voix dépend du fichier fourni : les noms `jarvis` et
`reddington` sont des profils, pas des voix livrées avec le projet.
Les fichiers de référence ne sont pas inclus.

## Installation Windows

Après l'installation normale de Red, double-clique sur `installer_chatterbox.bat`.
Le premier téléchargement nécessite Internet et plusieurs Go de disque :
Python 3.11, PyTorch 2.6 / CUDA 11.8, Chatterbox et les poids Multilingual.
Tout est placé dans le projet. L'environnement `.venv-chatterbox` est séparé
de `.venv-red` : les dépendances et les voix actuelles de Red sont conservées.

Pour une installation plus légère, exclusivement CPU :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/installer_chatterbox.ps1 -Cpu
```

Le script peut être relancé après un téléchargement interrompu. Il ne remplace
pas `config.yaml` et n'active pas automatiquement le nouveau moteur.

Après installation, **la synthèse fonctionne hors ligne** : chargement par
`from_local`, aucun appel à une API TTS, aucun WAV envoyé à un serveur.
Les poids officiels sont figés à la révision indiquée dans
`scripts/preparer_chatterbox.py`, avec le modèle Multilingual V2 attendu par
Chatterbox 0.1.7. Le filigrane audio PerTh de Chatterbox est conservé.
La version compatible de `setuptools` nécessaire à PerTh est fixée dans les
dépendances. Un adaptateur limité au tokenizer français évite l'initialisation
du segmentateur chinois de Chatterbox 0.1.7 ; le processus vocal bloque aussi
les connexions réseau pour détecter tout téléchargement imprévu.

## Ajouter les références

Place les fichiers dans le dossier `voices/` (distinct de `voix/`, réservé à Piper) :

```text
voices/
  jarvis_reference.wav
  reddington_reference.wav
```

Utilise environ **10 secondes de voix seule**, en français, avec une seule
personne, sans musique ni réverbération marquée. Un WAV PCM 16 bits mono est
un bon choix. Chatterbox rééchantillonne lui-même l'audio si nécessaire.
Une référence en français aide à conserver une prononciation française.
Les WAV de `voices/` sont exclus de Git.

Dans `config.yaml`, complète les sections existantes (ne crée pas deux clés
`tts:` dans le même fichier) :

```yaml
tts:
  moteur: chatterbox
  profil: jarvis
  voix_locale: jarvis_fr       # voix Piper conservée pour le secours

chatterbox:
  modele: "models/chatterbox"
  python: ".venv-chatterbox/Scripts/python.exe"
  device: auto
  threads: 4
  timeout: 180

voices:
  jarvis:
    reference: "voices/jarvis_reference.wav"
    exaggeration: 0.20
    cfg_weight: 0.45
    temperature: 0.8
  reddington:
    reference: "voices/reddington_reference.wav"
    exaggeration: 0.40
    cfg_weight: 0.35
    temperature: 0.8
```

Les chemins relatifs partent toujours du dossier du projet, même si le lancement
se fait depuis un autre dossier. Les chemins absolus locaux sont acceptés.
Pour changer de voix, remplace simplement `tts.profil: jarvis` par
`tts.profil: reddington`, puis redémarre Red. Ajoute autant de profils que voulu
dans `voices`, sans modifier le code.

Dans **`/panneau` → Réglages**, le profil Chatterbox et le moteur sont également
sélectionnables. Les changements via le panneau s'appliquent à la prochaine
réponse. Les profils ajoutés manuellement à YAML apparaissent après redémarrage.
Le panneau explique quel WAV manque et refuse l'activation d'un profil incomplet.
La liste « Voix Piper » et son bouton « Écouter » restent propres à Piper.

## Paramètres

| Réglage | Rôle |
| --- | --- |
| `exaggeration` | Expressivité, de 0 à 2 ; commencer autour de 0.2–0.5. |
| `cfg_weight` | Guidage du modèle, de 0 à 1 ; essayer 0.3–0.5 pour le débit. |
| `temperature` | Variabilité, de 0.05 à 2 ; facultatif, défaut 0.8. |
| `device: auto` | Essaie CUDA si utilisable, sinon CPU. |
| `device: cpu` | Force le CPU, même en présence d'une carte NVIDIA. |
| `device: cuda` | Demande CUDA ; conserve un secours CPU si indisponible ou en échec. |
| `threads` | Threads CPU, de 1 à 32 ; défaut 4. |
| `timeout` | Délai total de synthèse en secondes, chargement inclus ; défaut 180. |

Le modèle reste chargé entre les phrases. La référence est recalculée lors d'un
changement de fichier ou de paramètres. Les textes longs sont découpés en
phrases courtes pour limiter la mémoire, puis réunis dans un seul audio.
La lecture et son interruption utilisent le système existant de Red.
L'interruption vocale intervient pendant la lecture ; une génération déjà en
cours peut continuer jusqu'à son achèvement ou son délai maximal.

Chatterbox demande davantage de mémoire et de calcul que Piper ; sur CPU, les
réponses peuvent être nettement plus lentes, notamment la première. Un manque
de VRAM entraîne une nouvelle tentative CPU. Si le moteur, le modèle ou le WAV
est absent, ou si le délai expire, Red signale l'erreur dans le journal et utilise
**Piper**, puis **Windows** si nécessaire. Ce secours reste local.
Piper, Kokoro, Windows et ElevenLabs restent sélectionnables comme auparavant ;
le mode local continue d'exclure ElevenLabs.

## Vérifier une génération réelle

Depuis le dossier du projet :

```powershell
.venv-red\Scripts\python.exe scripts\tester_chatterbox.py --profil jarvis
.venv-red\Scripts\python.exe scripts\tester_chatterbox.py --profil reddington --sortie logs/reddington-test.wav
```

Ce test charge réellement Chatterbox, génère la phrase française et écrit un WAV
PCM mono, avec durée, fréquence, appareil utilisé et temps de génération.
Il **échoue au lieu d'utiliser Piper** si Chatterbox ne fonctionne pas.
Écoute le WAV pour juger le timbre et la diction de ta référence.

Pour tester un autre WAV sans changer la configuration :

```powershell
.venv-red\Scripts\python.exe scripts\tester_chatterbox.py --profil jarvis --reference "C:\Audio\reference.wav" --device cpu --timeout 600
```

Diagnostics du moteur : `logs/chatterbox.log`. Pour revenir à la voix rapide
habituelle : `tts.moteur: piper`.

### Validation sur ce PC, le 22 septembre 2026

La génération a été exécutée avec une référence **synthétique Piper Tom** de
10,87 secondes, les WAV personnels n'étant pas encore disponibles. Les deux
profils ont utilisé cette même référence uniquement pendant les tests ; leurs
chemins dans `config.yaml` restent ceux des futurs fichiers personnels.

| Test réel, réseau bloqué dans le worker | Audio mono 24 kHz | Temps mesuré |
| --- | --- | --- |
| CUDA automatique, RTX 3050 Ti 4 Go, premier chargement inclus | 4,64 s | 149,83 s |
| CPU, profil jarvis, premier chargement inclus | 1,52 s | 100,15 s |
| CPU, passage à reddington dans le même processus | 3,44 s | 92,30 s |

Les fichiers se trouvent dans `logs/chatterbox-validation-*.wav` sur ce PC.
Whisper local a reconnu « Bonjour, monsieur. » et « Très bien. Je suis à votre
disposition. » dans les deux tests CPU. Le test CUDA est également transcrit,
avec un petit mot supplémentaire reconnu. Cela vérifie la génération et une
intelligibilité de base, pas la fidélité à tes futures références ni une qualité
parfaite pour tout texte. Le rendu final sera à écouter avec tes propres WAV.

Les 215 tests du projet passent. Le panneau a aussi été vérifié dans un navigateur,
notamment le refus d'activer un profil sans WAV, en conservant Piper sélectionné.

## Personnalité

Le profil vocal et la personnalité sont indépendants. Le preset existant
`assistant.personnalite: jarvis_sarcastique` donne désormais à **Red** des réponses
brèves, calmes et très polies, avec un humour sec et subtil, parfois « Monsieur »,
des formulations élégantes et légèrement britanniques, sans exclamations inutiles.
Il reste imperturbable et évite l'ironie agressive ou familière.

Sources : [projet officiel](https://github.com/resemble-ai/chatterbox),
[paquet 0.1.7](https://pypi.org/project/chatterbox-tts/0.1.7/),
[poids officiels](https://huggingface.co/ResembleAI/chatterbox).
