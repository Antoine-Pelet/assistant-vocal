"""Télécharge les modèles locaux et prépare la configuration Red (sauvegardée)."""
import json
import os
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile

import truststore
import yaml

RACINE = Path(__file__).resolve().parent.parent
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def telecharger(url, destination):
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partiel = destination.with_name(destination.name + ".part")
    print(f"Téléchargement : {destination.name}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as source, partiel.open("wb") as cible:
        shutil.copyfileobj(source, cible)
    partiel.replace(destination)


def modeles():
    modele = RACINE / "models/vosk-model-small-fr-0.22"
    if not (modele / "am/final.mdl").is_file():
        archive = RACINE / ".cache/vosk-fr.zip"
        telecharger("https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip", archive)
        with zipfile.ZipFile(archive) as z:
            destination = (RACINE / "models").resolve()
            for membre in z.namelist():
                if not (destination / membre).resolve().is_relative_to(destination):
                    raise ValueError("Chemin invalide dans le modèle Vosk")
            z.extractall(destination)
    for voix in ("tom",):
        base = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/{voix}/medium/"
        for suffixe in (".onnx", ".onnx.json"):
            nom = f"fr_FR-{voix}-medium{suffixe}"
            telecharger(base + nom, RACINE / "voix" / nom)
        telecharger(base + "MODEL_CARD", RACINE / "voix" / f"fr_FR-{voix}-medium.MODEL_CARD")
    from huggingface_hub import snapshot_download
    print("Préparation de Whisper base (transcription française locale)...", flush=True)
    snapshot_download("Systran/faster-whisper-base", local_dir=RACINE / "models/whisper-base",
                      allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*"])


def configurer():
    sys.path.insert(0,str(RACINE))
    from core import config
    fichier=RACINE/'config.yaml'
    sauvegarde=RACINE/'.red-install/config-avant-red.yaml'
    sauvegarde.parent.mkdir(parents=True,exist_ok=True)
    if fichier.exists():
        if not sauvegarde.exists():shutil.copy2(fichier,sauvegarde)
        raw=yaml.safe_load(fichier.read_text(encoding='utf8')) or {}
    else:
        raw=yaml.safe_load((RACINE/'config.example.yaml').read_text(encoding='utf8'))
    config.FICHIER=fichier
    config._CONFIG=config.validate(config.migrate(raw))
    config.save_migrated()
    print('Configuration préparée ; réglages existants conservés.',flush=True)


if __name__ == "__main__":
    truststore.inject_into_ssl()
    modeles()
    # Les réglages ne sont appliqués qu'une fois les modèles disponibles.
    configurer()
