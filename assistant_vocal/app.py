"""Démarrage et arrêt de l’instance locale de Red."""

from pathlib import Path


def main():
    from core.instance import InstanceUnique

    with InstanceUnique(
        Path(__file__).resolve().parents[1] / ".red-install/red.lock"
    ) as premiere:
        if not premiere:
            print(
                "Red est déjà lancé. Utilise l'instance ouverte ou son panneau ; aucun second micro ne sera démarré."
            )
            return
        from assistant_vocal.runtime import runtime

        runtime.start()
        try:
            from audio.local import _main

            _main()
        finally:
            runtime.stop()
