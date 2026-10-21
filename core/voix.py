"""DEPRECATED : raccordement des anciens tools à la sortie audio locale.

Permet aux outils (ex. le minuteur) de parler sans dependre de audio.local,
ce qui evite les imports circulaires. audio.local enregistre sa fonction `dire`
via definir_parleur() au demarrage.
"""
_parleur = None


def definir_parleur(fonction):
    global _parleur
    _parleur = fonction


def parler(texte):
    if _parleur is not None:
        _parleur(texte)
