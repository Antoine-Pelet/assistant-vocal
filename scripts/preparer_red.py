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

truststore.inject_into_ssl()
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
    for voix in ("siwis", "tom"):
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
    fichier = RACINE / "config.yaml"
    sauvegarde = RACINE / ".red-install/config-avant-red.yaml"
    sauvegarde.parent.mkdir(parents=True, exist_ok=True)
    if fichier.exists() and not sauvegarde.exists():
        shutil.copy2(fichier, sauvegarde)
    conf = yaml.safe_load((fichier if fichier.exists() else RACINE / "config.example.yaml").read_text(encoding="utf-8"))
    valeurs = {
        "mode": "local", "assistant.nom": "Red", "assistant.mot_activation": "red",
        "assistant.moteur_reveil": "vosk", "assistant.modele_reveil": "models/vosk-model-small-fr-0.22",
        "assistant.stabilite_reveil": 3, "assistant.personnalite": "neutre", "assistant.piece_nuit": "",
        "ollama.hote": "http://127.0.0.1:11434", "ollama.modele": "qwen3.5:2b",
        "ollama.num_ctx": 4096, "ollama.num_predict": 256, "ollama.think": False,
        "whisper.modele": "models/whisper-base", "whisper.device": "cpu",
        "tts.moteur": "piper", "piper.modele": "voix/fr_FR-siwis-medium.onnx",
        "serveur.actif": True,
        "scenes.au_demarrage_actif": False, "scenes.spotify": False,
    }
    for chemin, valeur in valeurs.items():
        noeud = conf
        cles = chemin.split(".")
        for cle in cles[:-1]:
            noeud = noeud.setdefault(cle, {})
        noeud[cles[-1]] = valeur
    profil = conf.setdefault("tts", {}).setdefault("voix_locale", "siwis_fr")
    if profil in ("tom_fr", "jarvis_fr"):
        conf.setdefault("piper", {})["modele"] = "voix/fr_FR-tom-medium.onnx"
    for fournisseur in ("openai", "anthropic"):
        if conf.get(fournisseur, {}).get("cle") in ("sk-proj-...", "sk-ant-..."):
            conf[fournisseur]["cle"] = ""
    fichier.write_text(yaml.safe_dump(conf, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print("Configuration locale prête ; original conservé dans .red-install/.", flush=True)


if __name__ == "__main__":
    modeles()
    # Les réglages ne sont appliqués qu'une fois les modèles disponibles.
    configurer()
