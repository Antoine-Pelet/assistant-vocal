"""Orchestration de haut niveau, indépendante des fonctionnalités."""
from pathlib import Path


class RedApplication:
    def __init__(self, runtime=None, audio_runner=None):
        if runtime is None:
            from assistant_vocal.runtime import runtime as default_runtime
            runtime = default_runtime
        self.runtime = runtime
        self.audio_runner = audio_runner

    def start(self):
        from core.instance import InstanceUnique
        from observability.logging import obtenir
        logger = obtenir()
        with InstanceUnique(Path(__file__).resolve().parents[1] / ".red-install/red.lock") as first:
            if not first:
                logger.info("Red est déjà lancé. Aucun second microphone n'est démarré.")
                return
            try:
                self.runtime.start()
                runner = self.audio_runner
                if runner is None:
                    from audio.local import _main
                    runner = _main
                runner()
            finally:
                self.runtime.stop()


def main():
    RedApplication().start()
