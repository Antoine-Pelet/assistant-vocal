"""Détection locale configurable du mot d'activation, en PCM mono 16 kHz."""
import json
import re
from collections import deque
from pathlib import Path

from core import config

RACINE = Path(__file__).resolve().parent.parent
MODELE_VOSK = "models/vosk-model-small-fr-0.22"


def mot_activation():
    mot = str(config.reglage("assistant.mot_activation", "red") or "").strip().lower()
    if not mot or not re.fullmatch(r"\w+(?:\s+\w+)*", mot):
        raise ValueError("assistant.mot_activation doit contenir un mot ou une expression.")
    return mot


def retirer_activation(texte):
    """Retire uniquement le préfixe complet, jamais 'red' dans 'redémarre'."""
    mot = re.escape(mot_activation()).replace(r"\ ", r"\s+")
    return re.sub(r"^\s*(?:(?:hey|hé|eh)\s+)?" + mot + r"\b[\s,.:;!?…-]*",
                  "", texte, count=1, flags=re.IGNORECASE).strip()


class ReveilVosk:
    """Vosk propose un réveil, Whisper confirme le mot réellement prononcé.

    Une grammaire avec [unk] laisse rejeter les bruits et les autres paroles.
    La confirmation évite de confondre 'redémarre' ou 'arrête' avec 'red'.
    predict/reset gardent l'interface utilisée par la boucle audio existante.
    """

    def __init__(self, chemin, mot, stabilite=3, verifier=None):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        if not chemin.is_dir():
            raise FileNotFoundError(
                f"Modèle Vosk absent : {chemin}. Lance installer_red.bat.")
        SetLogLevel(-1)
        self.mot = mot
        self.stabilite = max(1, int(stabilite))
        self._expression = re.compile(r"\b" + re.escape(mot) + r"\b", re.IGNORECASE)
        self._modele = Model(str(chemin))
        for terme in mot.split():
            if self._modele.vosk_model_find_word(terme) == -1:
                raise ValueError(f"Le modèle de réveil ne connaît pas le mot {terme!r}.")
        self._reconnaissance = KaldiRecognizer(
            self._modele, 16000, json.dumps([mot, "[unk]"], ensure_ascii=False))
        self._reconnaissance.SetWords(True)
        self._verifier = verifier
        self._audio = deque(maxlen=38)  # 3 secondes en blocs de 80 ms
        self._attente_verif = 0
        self._consecutifs = 0
        self._declenche = False

    def predict(self, audio):
        self._audio.append(audio.copy())
        self._attente_verif = max(0, self._attente_verif - 1)
        final = self._reconnaissance.AcceptWaveform(audio.tobytes())
        resultat = json.loads(self._reconnaissance.Result() if final
                              else self._reconnaissance.PartialResult())
        texte = resultat.get("text" if final else "partial", "")
        trouve = bool(self._expression.search(texte))
        self._consecutifs = self._consecutifs + 1 if trouve else 0
        score = 0.0
        if (not self._declenche and trouve and not self._attente_verif
                and (final or self._consecutifs >= self.stabilite)):
            accepte = True
            if self._verifier is not None:
                import numpy as np
                accepte = self._verifier(np.concatenate(self._audio))
                self._attente_verif = 7  # éviter de retranscrire chaque bloc
            if accepte:
                score = 1.0
                self._declenche = True
        return {self.mot: score}

    def reset(self):
        self._reconnaissance.Reset()
        self._consecutifs = 0
        self._declenche = False
        self._audio.clear()
        self._attente_verif = 0


def charger_reveil(whisper=None):
    moteur = str(config.reglage("assistant.moteur_reveil", "vosk")).lower()
    if moteur == "vosk":
        chemin = Path(config.reglage("assistant.modele_reveil", MODELE_VOSK))
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        mot = mot_activation()
        if whisper is None:
            from faster_whisper import WhisperModel
            modele = config.reglage("whisper.modele", "base")
            if (RACINE / modele).is_dir():
                modele = str(RACINE / modele)
            whisper = WhisperModel(modele, device="cpu", compute_type="int8")

        expression = re.compile(r"\b" + re.escape(mot) + r"\b", re.IGNORECASE)

        def verifier(pcm):
            import numpy as np
            audio = np.pad(pcm.astype(np.float32) / 32768, (0, 3200))
            segments, _ = whisper.transcribe(
                audio, language="fr", beam_size=1, condition_on_previous_text=False,
                initial_prompt=f"{mot.capitalize()}, assistant vocal.")
            return bool(expression.search(" ".join(s.text for s in segments)))

        return ReveilVosk(chemin, mot_activation(),
                          config.reglage("assistant.stabilite_reveil", 3), verifier)
    if moteur == "openwakeword":
        # Un nom de fichier ne change pas le mot appris par un réseau neuronal.
        import openwakeword
        from openwakeword.model import Model
        chemin = config.reglage("assistant.modele_reveil", "")
        if not chemin:
            if mot_activation() != "hey jarvis":
                raise ValueError("openWakeWord exige un modèle entraîné pour le mot choisi.")
            chemin = Path(openwakeword.__file__).parent / "resources/models/hey_jarvis_v0.1.onnx"
        chemin = Path(chemin)
        if not chemin.is_absolute():
            chemin = RACINE / chemin
        return Model(wakeword_model_paths=[str(chemin)])
    raise ValueError(f"Moteur de réveil inconnu : {moteur}")
