"""Génère un vrai WAV, sans repli Piper/SAPI et sans changer config.yaml."""
import argparse
import json
from pathlib import Path
import sys
import time
import wave

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profil", default=None)
    parser.add_argument("--reference", help="WAV local de test, remplace la référence sans enregistrer la configuration")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--texte", default="Très bien, Monsieur. Tout fonctionne comme prévu.")
    parser.add_argument("--sortie", default="logs/chatterbox-test.wav")
    args = parser.parse_args()
    from core import config
    from core.chatterbox_tts import ChatterboxProvider
    conf = config._charger()
    profil = args.profil or conf.get("tts", {}).get("profil", "jarvis")
    if args.reference:
        voix = conf.setdefault("voices", {}).setdefault(profil, {})
        voix["reference"] = str(Path(args.reference).resolve())
    if args.device:
        conf.setdefault("chatterbox", {})["device"] = args.device
    if args.timeout:
        conf.setdefault("chatterbox", {})["timeout"] = args.timeout
    provider = ChatterboxProvider(profil=profil)
    debut = time.perf_counter()
    try:
        audio, frequence = provider.generer(args.texte)
        if not audio.any():
            raise RuntimeError("Audio silencieux : test échoué.")
        sortie = Path(args.sortie).resolve()
        sortie.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(sortie), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(frequence)
            wav.writeframes(audio.astype("<i2").tobytes())
        print(json.dumps({"fichier": str(sortie), "device": provider.dernier_appareil,
                          "duree_audio": round(len(audio) / frequence, 2),
                          "frequence": frequence, "generation_secondes": round(time.perf_counter() - debut, 2)},
                         ensure_ascii=False))
    finally:
        provider.fermer()


if __name__ == "__main__":
    main()
