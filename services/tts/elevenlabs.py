"""DEPRECATED : compatibilité cloud facultative, non chargée en mode local."""

import json
import urllib.request
from pathlib import Path
from core.config import reglage
from services.tts.base import ProviderTTS

_RACINE = Path(__file__).resolve().parents[2]


class ElevenLabsProvider(ProviderTTS):
    nom = "ElevenLabs"

    def __init__(self):
        self.cle = reglage("elevenlabs.cle", "")
        self.voix = reglage("elevenlabs.voix", "")
        self.modele = reglage("elevenlabs.modele", "eleven_flash_v2_5")
        self._voix_resolue = None

    def disponible(self):
        return bool(self.cle)

    def _resoudre_voix(self):
        if self.voix:
            return self.voix
        if self._voix_resolue:
            return self._voix_resolue
        try:
            requete = urllib.request.Request(
                "https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": self.cle}
            )
            with urllib.request.urlopen(requete, timeout=6) as reponse:
                d = json.loads(reponse.read().decode("utf-8"))
            self._voix_resolue = d["voices"][0]["voice_id"]
        except Exception:
            self._voix_resolue = "21m00Tcm4TlvDq8ikWAM"  # Rachel, par defaut
        return self._voix_resolue

    def synthetiser(self, texte):
        try:
            import miniaudio
            import numpy as np
        except ImportError:
            return None
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self._resoudre_voix()}"
        charge = {"text": texte, "model_id": self.modele}
        # Flash/Turbo v2.5 acceptent language_code : on force le francais pour une
        # bonne prononciation des accents (e accent, c cedille...) quelle que soit
        # la voix (sinon la langue est auto-detectee et parfois lue en anglais).
        if any(x in self.modele for x in ("flash", "turbo")):
            charge["language_code"] = reglage("elevenlabs.langue", "fr")
        corps = json.dumps(charge).encode("utf-8")
        requete = urllib.request.Request(
            url,
            data=corps,
            method="POST",
            headers={
                "xi-api-key": self.cle,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
        )
        try:
            with urllib.request.urlopen(requete, timeout=15) as reponse:
                mp3 = reponse.read()
            decode = miniaudio.decode(
                mp3,
                nchannels=1,
                sample_rate=24000,
                output_format=miniaudio.SampleFormat.SIGNED16,
            )
            try:  # N12 : comptabilite voix (au caractere)
                from core import budget

                budget.enregistrer_tts(len(texte or ""))
            except Exception:
                pass
            return np.frombuffer(decode.samples, dtype=np.int16), 24000
        except Exception as e:
            print(f"  [ElevenLabs] indisponible ({e}), repli voix Windows.")
            return None
