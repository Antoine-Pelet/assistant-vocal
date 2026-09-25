"""Capture déterministe sur la durée des échantillons, indépendante du CPU."""
import re
import numpy as np
from core.util import sans_accents


def capturer_phrase(lire, tampon, *, taux=16000, seuil=0.004, silence_fin=1.6,
                    attente_debut=4.0, duree_max=25.0, duree_min=0.3, observer=None):
    morceaux = list(tampon)
    tampon.clear()
    # Le prébuffer conserve le début de « Red, ouvre… ». Il ne raccourcit pas
    # le temps laissé pour commencer une demande après le bip.
    nouveaux = 0
    dernier_son = None
    while nouveaux / taux < duree_max:
        bloc = np.asarray(lire(), dtype=np.float32)
        morceaux.append(bloc)
        nouveaux += len(bloc)
        if observer:
            observer(bloc)
        if float(np.sqrt(np.mean(bloc * bloc))) > seuil:
            dernier_son = nouveaux
        if dernier_son is None:
            if nouveaux / taux >= attente_debut:
                break
        elif (nouveaux - dernier_son) / taux >= silence_fin:
            break
    if not morceaux:
        return None
    audio = np.concatenate(morceaux)
    # Refuser le silence réel et les impulsions isolées avant Whisper ; garder
    # 200 ms de marge pour les consonnes faibles, sans les secondes de silence.
    trame = max(1, int(taux * 0.02))
    voix = [i for i in range(0, len(audio), trame)
            if np.sqrt(np.mean(audio[i:i + trame] ** 2)) > seuil]
    if len(voix) * 0.02 < 0.12:
        return None
    marge = int(taux * 0.2)
    audio = audio[max(0, voix[0] - marge):min(len(audio), voix[-1] + trame + marge)]
    return audio if len(audio) >= taux * duree_min else None


def intention_veille(texte):
    """Seul un accord explicite termine l'écoute ; jamais une sous-chaîne."""
    t = sans_accents(str(texte or '')).lower()
    t = ' '.join(re.sub(r'[^a-z0-9 ]', ' ', t).split())
    if not t or t in {'peut etre', 'je ne sais pas', 'hein', 'quoi'}:
        return 'incertain'
    if t in {'oui', 'ouais', 'ouep', 'oui merci', 'oui tu peux', 'oui vas y', 'oui je confirme',
             'oui c est bon', 'oui mets toi en veille', 'oui passe en veille',
             'oui tu peux te mettre en veille',
             'je confirme', 'confirme', 'd accord', 'ok', 'okay', 'vas y',
             'mets toi en veille', 'met toi en veille', 'mes toi en veille', 'passe en veille',
             'tu peux te mettre en veille', 'bonne nuit', 'j ai fini'}:
        return 'veille'
    if t in {'non', 'non merci', 'non pas encore', 'pas encore', 'attends', 'reste a l ecoute',
             'continue', 'j ai encore une question', 'ne te mets pas en veille'}:
        return 'continuer'
    return 'commande'
