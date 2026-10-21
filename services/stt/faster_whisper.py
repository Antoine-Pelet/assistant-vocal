import os
from pathlib import Path

_DLL_HANDLES = []


def _ajouter_dll_nvidia():
    """Rend les DLL cuBLAS et cuDNN visibles pour faster-whisper."""
    racines = []
    try:
        import nvidia

        racines = [Path(p) for p in getattr(nvidia, "__path__", [])]
    except ImportError:
        pass

    if not racines:
        import sysconfig

        base = Path(sysconfig.get_paths()["purelib"]) / "nvidia"
        if base.exists():
            racines = [base]

    dossiers = []
    for racine in racines:
        dossiers.extend(racine.glob("*/bin"))
        dossiers.extend(racine.glob("*/lib"))

    for dossier in dossiers:
        chemin = str(dossier)
        if chemin not in os.environ["PATH"]:
            os.environ["PATH"] = chemin + os.pathsep + os.environ["PATH"]
        try:
            _DLL_HANDLES.append(os.add_dll_directory(chemin))
        except (OSError, AttributeError):
            pass


from threading import RLock
from core.contexte import use
from services import AudioData


class WhisperService:
    def __init__(self, model):
        self.model = model

    def transcribe(self, audio, context):
        import numpy as np

        if audio.sample_rate != 16000 or audio.channels != 1:
            raise ValueError("Whisper attend du PCM mono à 16 kHz.")
        samples = np.frombuffer(audio.pcm, dtype="<i2").astype(np.float32) / 32768.0
        try:
            with _LOCK, use(context):
                segments, _ = self.model.transcribe(samples, language="fr", beam_size=1)
                return " ".join(segment.text for segment in segments).strip()
        finally:
            samples.fill(0)


_MODEL = None
_LOCK = RLock()


def model():
    """Une instance partagée par le micro local et les transports."""
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            from core.config import reglage

            if reglage("whisper.device", "auto") != "cpu":
                _ajouter_dll_nvidia()
            from faster_whisper import WhisperModel

            name = reglage("whisper.modele", "base")
            local_path = Path(__file__).resolve().parents[2] / name
            if local_path.is_dir():
                name = str(local_path)
            device = reglage("whisper.device", "auto")
            try:
                _MODEL = WhisperModel(
                    name,
                    device=device,
                    compute_type="int8" if device == "cpu" else "default",
                )
            except Exception:
                if device == "cpu":
                    raise
                _MODEL = WhisperModel(name, device="cpu", compute_type="int8")
        return _MODEL


def service():
    return WhisperService(model())


def close():
    global _MODEL
    with _LOCK:
        _MODEL = None
