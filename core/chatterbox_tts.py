"""Client TTS local : Chatterbox vit dans son environnement Python isolé.

Le processus reste chargé entre les phrases. Aucune dépendance Torch n'est
importée dans Red et aucune requête réseau n'est faite pendant la synthèse.
"""
import atexit
import base64
import json
import logging
import math
import os
from pathlib import Path
import queue
import subprocess
import threading

from core.config import reglage

LOG = logging.getLogger("jarvis")
RACINE = Path(__file__).resolve().parent.parent
FICHIERS_MODELE = (
    "ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json", "Cangjie5_TC.json",
)


def chemin_local(valeur):
    if not isinstance(valeur, str) or not valeur.strip() or "://" in valeur:
        raise ValueError("Un chemin de fichier local est attendu.")
    chemin = Path(valeur).expanduser()
    # Les références et modèles restent sur ce PC, pas sur un partage réseau.
    if str(chemin).startswith(("\\\\", "//")):
        raise ValueError("Choisis un fichier sur ce PC, pas un partage réseau.")
    return (chemin if chemin.is_absolute() else RACINE / chemin).resolve()


def nombre(valeur, nom, bas, haut):
    if isinstance(valeur, bool):
        raise ValueError(f"{nom} doit être un nombre entre {bas} et {haut}.")
    valeur = float(valeur)
    if not math.isfinite(valeur) or not bas <= valeur <= haut:
        raise ValueError(f"{nom} doit être entre {bas} et {haut}.")
    return valeur


def configuration(profil=None):
    """Valide le profil sans importer Chatterbox ni charger les poids."""
    profil = profil or reglage("tts.profil", "jarvis")
    profils = reglage("voices", {})
    voix = profils.get(profil) if isinstance(profils, dict) and isinstance(profil, str) else None
    if not isinstance(voix, dict):
        raise ValueError(f"Profil Chatterbox inconnu : {profil!r} (section voices).")
    reference = chemin_local(voix.get("reference"))
    if reference.suffix.lower() != ".wav" or not reference.is_file():
        raise ValueError(f"Référence WAV absente : {reference}")
    appareil = reglage("chatterbox.device", "auto")
    if appareil not in {"auto", "cpu", "cuda"}:
        raise ValueError("chatterbox.device doit valoir auto, cpu ou cuda.")
    return {
        "profil": profil, "reference": str(reference),
        "exaggeration": nombre(voix.get("exaggeration", 0.5), "exaggeration", 0, 2),
        "cfg_weight": nombre(voix.get("cfg_weight", 0.5), "cfg_weight", 0, 1),
        "temperature": nombre(voix.get("temperature", 0.8), "temperature", 0.05, 2),
        "device": appareil,
        "modele": str(chemin_local(reglage("chatterbox.modele", "models/chatterbox"))),
        "threads": int(nombre(reglage("chatterbox.threads", 4), "threads", 1, 32)),
    }


class ChatterboxProvider:
    nom = "Chatterbox Multilingual"

    def __init__(self, profil=None):
        self.profil = profil
        self._processus = None
        self._journal = None
        self._verrou = threading.RLock()
        self._repli = None
        self._erreur = None
        self.dernier_appareil = None

    def _python(self):
        defaut = ".venv-chatterbox/Scripts/python.exe" if os.name == "nt" else ".venv-chatterbox/bin/python"
        return chemin_local(reglage("chatterbox.python", defaut))

    def verifier(self):
        conf = configuration(self.profil)
        if not self._python().is_file():
            raise ValueError("Chatterbox absent : lance installer_chatterbox.bat.")
        manquants = [f for f in FICHIERS_MODELE if not (Path(conf["modele"]) / f).is_file()]
        if manquants:
            raise ValueError("Modèle Chatterbox incomplet : lance installer_chatterbox.bat.")
        return conf

    def disponible(self):
        try:
            self.verifier()
            return True
        except (ValueError, TypeError, OSError):
            return False

    def _demarrer(self):
        if self._processus is not None and self._processus.poll() is None:
            return
        self.fermer()
        env = dict(os.environ, PYTHONUTF8="1", HF_HUB_OFFLINE="1",
                   TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                   DO_NOT_TRACK="1", HF_HOME=str(RACINE / "models/chatterbox-cache"))
        (RACINE / "logs").mkdir(exist_ok=True)
        self._journal = (RACINE / "logs/chatterbox.log").open("a", encoding="utf-8")
        self._processus = subprocess.Popen(
            [str(self._python()), "-u", str(RACINE / "scripts/chatterbox_worker.py")],
            cwd=str(RACINE), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._journal, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        atexit.register(self.fermer)
        self._reponses = queue.Queue()
        # La file appartient à CE processus : une réponse tardive ne peut pas
        # être prise pour celle d'un worker relancé après expiration du délai.
        def lire(flux, file):
            try:
                for ligne in flux:
                    file.put(ligne)
            finally:
                file.put(None)
        threading.Thread(target=lire, args=(self._processus.stdout, self._reponses),
                         daemon=True, name="chatterbox-sortie").start()

    def generer(self, texte):
        """Synthèse stricte, sans repli : utilisée aussi par le test WAV."""
        import numpy as np
        if not isinstance(texte, str) or not texte.strip():
            raise ValueError("Le texte à prononcer est vide.")
        with self._verrou:
            conf = self.verifier()
            delai = nombre(reglage("chatterbox.timeout", 180), "timeout", 5, 1800)
            try:
                self._demarrer()
                self._processus.stdin.write(json.dumps(dict(conf, texte=texte), ensure_ascii=False) + "\n")
                self._processus.stdin.flush()
                ligne = self._reponses.get(timeout=delai)
                if ligne is None:
                    raise RuntimeError("Le moteur Chatterbox s'est arrêté. Voir logs/chatterbox.log.")
                resultat = json.loads(ligne)
                if not resultat.get("ok"):
                    raise RuntimeError(resultat.get("erreur", "Échec de la génération Chatterbox."))
                audio = np.frombuffer(base64.b64decode(resultat["pcm"], validate=True), dtype="<i2").copy()
                frequence = int(resultat["frequence"])
                if not audio.size or not 8000 <= frequence <= 96000:
                    raise ValueError("Audio Chatterbox vide ou fréquence invalide.")
                self.dernier_appareil = resultat["device"]
                return audio, frequence
            except queue.Empty as exc:
                self.fermer()
                raise TimeoutError(f"Chatterbox a dépassé {delai:g} s ; processus arrêté.") from exc
            except Exception:
                self.fermer()
                raise

    def synthetiser(self, texte):
        try:
            audio = self.generer(texte)
            self._erreur = None
            return audio
        except Exception as exc:
            # Le repli ne contacte jamais un service cloud, quel que soit le mode.
            if str(exc) != self._erreur:
                LOG.warning("Chatterbox indisponible (%s), repli Piper puis Windows.", exc)
                self._erreur = str(exc)
            if self._repli is None:
                from core.tts import PiperProvider
                self._repli = PiperProvider()
            return self._repli.synthetiser(texte)

    def fermer(self):
        with self._verrou:
            atexit.unregister(self.fermer)
            processus, self._processus = self._processus, None
            if processus is not None:
                if processus.poll() is None:
                    # Sous Windows, le python d'un venv est un lanceur : arrêter
                    # aussi son interpréteur enfant pour libérer réellement CUDA.
                    import psutil
                    try:
                        enfants = psutil.Process(processus.pid).children(recursive=True)
                    except psutil.NoSuchProcess:
                        enfants = []
                    for enfant in reversed(enfants):
                        try:
                            enfant.kill()
                        except psutil.NoSuchProcess:
                            pass
                    processus.terminate()
                    try:
                        processus.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        processus.kill()
                        processus.wait(timeout=3)
                    if enfants:
                        psutil.wait_procs(enfants, timeout=3)
                for flux in (processus.stdin, processus.stdout):
                    if flux:
                        flux.close()
            if self._journal:
                self._journal.close()
                self._journal = None
