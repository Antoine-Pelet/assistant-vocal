"""Verrou système : un seul assistant peut écouter pour un même projet."""
import os
from pathlib import Path


class InstanceUnique:
    def __init__(self, chemin):
        self.chemin = Path(chemin)
        self.fichier = None

    def __enter__(self):
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        fichier = self.chemin.open('a+b')
        if fichier.seek(0, 2) == 0:
            fichier.write(b'0')
            fichier.flush()
        fichier.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(fichier.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fichier, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fichier.close()
            return False
        self.fichier = fichier
        return True

    def __exit__(self, *_):
        if self.fichier:
            self.fichier.close()  # Windows et Unix libèrent le verrou, même après un arrêt forcé.
