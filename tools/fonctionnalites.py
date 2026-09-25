"""Aide vocale exacte, indépendante des réponses générées par le modèle."""
from core.registre import outil


@outil(nom="fonctions_red", description="Liste les fonctionnalités actuelles de Red et leur disponibilité.",
       mcp_expose=True, affichage="toujours")
def fonctions_red():
    from core.fonctionnalites import resume_vocal
    return resume_vocal()
