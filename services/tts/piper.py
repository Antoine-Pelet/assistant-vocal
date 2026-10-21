from pathlib import Path
from core.config import reglage
from services.tts.base import ProviderTTS

_RACINE = Path(__file__).resolve().parents[2]


class PiperProvider(ProviderTTS):
    nom = "Piper"

    def __init__(self, profil=None):
        self.modele = reglage("piper.modele", "")
        from core.voix_locales import PROFILS, selection

        self.profil = selection() if profil is None else profil
        if self.profil:
            self.modele = PROFILS[self.profil]["modele"]
        self._voix = None

    def _sortie(self, audio, frequence):
        from core.voix_locales import appliquer_effet

        return appliquer_effet(audio, frequence, self.profil)

    def _chemin(self):
        if not self.modele:
            # a defaut, prend le premier .onnx trouve dans voix/
            trouves = list((_RACINE / "voix").glob("*.onnx"))
            return trouves[0] if trouves else None
        p = Path(self.modele)
        return p if p.is_absolute() else (_RACINE / p)

    def disponible(self):
        c = self._chemin()
        return bool(c and c.exists())

    def synthetiser(self, texte):
        try:
            import numpy as np
            from piper import PiperVoice
        except ImportError:
            print("  [Piper] librairie piper-tts absente.")
            return None
        chemin = self._chemin()
        if chemin is None or not chemin.exists():
            print("  [Piper] aucun modele de voix (.onnx) dans voix/. Voir docs.")
            return None
        try:
            if self._voix is None:
                self._voix = PiperVoice.load(str(chemin))

            # Ancienne API (piper-tts <= 1.2.x) : synthesize_stream_raw() -> PCM brut.
            if hasattr(self._voix, "synthesize_stream_raw"):
                brut = b"".join(self._voix.synthesize_stream_raw(texte))
                return self._sortie(
                    np.frombuffer(brut, dtype=np.int16), self._voix.config.sample_rate
                )

            # Nouvelle API (piper-tts >= 1.3.0, réécriture OHF-Voice/piper1-gpl) :
            # synthesize() renvoie des AudioChunk (int16 + sample_rate). C'est le
            # cas de la version par défaut de requirements.txt (issue NOVON82).
            morceaux, freq = [], None
            for chunk in self._voix.synthesize(texte):
                octets = getattr(chunk, "audio_int16_bytes", None)
                if octets is None:  # repli : tableau float
                    arr = getattr(chunk, "audio_float_array", None)
                    if arr is not None:
                        octets = (np.asarray(arr) * 32767).astype(np.int16).tobytes()
                if octets:
                    morceaux.append(octets)
                if freq is None:
                    freq = getattr(chunk, "sample_rate", None)
            brut = b"".join(morceaux)
            if not brut:
                return None
            if not freq:
                freq = getattr(
                    getattr(self._voix, "config", None), "sample_rate", 22050
                )
            return self._sortie(np.frombuffer(brut, dtype=np.int16), freq)
        except Exception as e:
            print(f"  [Piper] echec ({e}), repli voix Windows.")
            return None
