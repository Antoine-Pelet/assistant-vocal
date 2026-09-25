"""Détection continue des interruptions courtes avec le modèle Vosk déjà chargé."""
import json
import re
from collections import deque
import numpy as np
from core.commandes_vocales import commande_assistant, normaliser


class DetecteurInterruption:
    def __init__(self, modele, mot='red'):
        from vosk import KaldiRecognizer
        self.mot = normaliser(mot)
        phrases = [mot, 'stop', 'arrête', 'arrête de parler', 'tais toi', 'chut',
                   'silence', 'attends', f'{mot} stop', f'arrête {mot}',
                   f'quitte {mot}', 'mets toi en veille', 'passe en veille', '[unk]']
        self.reconnaissance = KaldiRecognizer(modele, 16000, json.dumps(phrases, ensure_ascii=False))
        self.reset()

    def reset(self):
        self.reconnaissance.Reset()
        self.precedent = ''
        self.stables = 0
        self.niveaux = deque(maxlen=10)

    def analyser(self, audio, texte_prononce='', seuil=0.006):
        final = self.reconnaissance.AcceptWaveform(audio.astype(np.int16).tobytes())
        d = json.loads(self.reconnaissance.Result() if final else self.reconnaissance.PartialResult())
        t = normaliser(d.get('text' if final else 'partial', '').replace('[unk]', ' '))
        rms = float(np.sqrt(np.mean((audio.astype(np.float32) / 32768) ** 2)))
        self.niveaux.append(rms)
        candidat = t == self.mot or commande_assistant(t) is not None
        self.stables = self.stables + 1 if candidat and t == self.precedent else int(candidat)
        self.precedent = t
        if not candidat or not (final or self.stables >= 2):
            return None
        # Éviter de s'interrompre en prononçant lui-même une commande dans une
        # explication. Le casque reste préférable pour séparer les deux voix.
        echo = re.search(r'\b' + re.escape(t) + r'\b', normaliser(texte_prononce))
        if echo or max(self.niveaux, default=0) < seuil:
            return None
        self.reset()
        return t
