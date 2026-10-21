"""Identité authentifiée, tampon PCM et fenêtre de suivi d’une connexion."""

from uuid import uuid4
from core.contexte import ExecutionContext, use


class _Session:
    """État d'une connexion satellite : identité, pièce, audio en cours, et une
    éventuelle action N3 en attente de confirmation vocale."""

    def __init__(self):
        self.session_id = uuid4().hex
        self.satellite = None
        self.piece = ""
        self.audio = bytearray()
        self.historique = []

        self.relances_restantes = 0

    @property
    def en_attente(self):
        from security.confirmations import _attente

        with use(_contexte_session(self)):
            pending = _attente()
            return (pending[0].nom, pending[1]) if pending else None

    @en_attente.setter
    def en_attente(self, value):
        from core import registre

        with use(_contexte_session(self)):
            if value is None:
                registre.annuler_confirme()
            else:
                registre.mettre_en_attente(registre.get(value[0]), value[1])

    def nouveau_reveil(self, maximum):
        """Ouvre un nombre borné de fenêtres sans nouveau wake word."""
        try:
            maximum = int(maximum)
        except (TypeError, ValueError):
            maximum = 2
        self.relances_restantes = max(0, min(maximum, 10))

    def autoriser_relance(self, obligatoire=False):
        """Consomme une relance normale ; les confirmations N3 restent possibles."""
        if obligatoire:
            return True
        if self.relances_restantes <= 0:
            return False
        self.relances_restantes -= 1
        return True

    def mettre_en_veille(self):
        self.relances_restantes = 0


def _contexte_session(session):
    from core.maison import room_for_satellite

    if not getattr(session, "session_id", None):
        session.session_id = uuid4().hex
    satellite_id = session.satellite
    room = (
        room_for_satellite(satellite_id, session.piece or None)
        if satellite_id
        else None
    )
    # Identité matérielle issue de la session authentifiée, jamais un utilisateur admin implicite.
    return ExecutionContext(
        user_id="anonymous",
        session_id=session.session_id,
        room_id=room,
        device_id=satellite_id,
        satellite_id=satellite_id,
        source="satellite",
    )
