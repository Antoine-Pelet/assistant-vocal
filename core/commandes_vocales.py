"""Intentions locales, avec phrases complètes et sans correspondance partielle."""
import re
from core.util import sans_accents


def normaliser(texte):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', sans_accents(str(texte or ''))).split())


def demande_directe(texte):
    from core.reveil import retirer_activation
    t = normaliser(retirer_activation(str(texte or '')))
    # Préfixes/suffixes de politesse seulement : on ne retire ni négation ni
    # contexte cité (« explique comment… », « ne te mets pas… »).
    for _ in range(3):
        t = re.sub(r'^(?:s il te plait|stp|peux tu|pourrais tu|tu peux|'
                   r'est ce que tu peux|je voudrais que tu|je veux que tu|'
                   r'j aimerais que tu|j aimerais savoir|je voudrais savoir) ', '', t)
        t = re.sub(r' (?:s il te plait|stp|merci|maintenant)$', '', t)
    return t.strip()


def commande_assistant(texte):
    t = demande_directe(texte)
    # Variantes réellement transcrites par Whisper base sur les phrases françaises.
    if re.fullmatch(r'(?:(?:mets?|mes|mette|mettez) (?:toi|vous)|mettoy|mettoi|passe|passer|va|aller|te mettes|te mettre) en veille', t):
        return 'veille'
    if re.fullmatch(r'(?:mets?|mes) (?:red|l assistant) en veille', t):
        return 'veille'
    if t in {'mode veille', 'active le mode veille'}:
        return 'veille'
    if t == 'arrete de red':
        return 'quitter'
    if re.fullmatch(r'(?:arret(?:e|er)?|stopp(?:e|er)|ferm(?:e|er)|quitt(?:e|er)|eteins|eteindre) (?:red|l assistant|le programme red)', t):
        return 'quitter'
    if t in {'quitte', 'quitter', 'ferme toi', 'arrete de fonctionner'}:
        return 'quitter'
    if re.fullmatch(r'(?:arrete|stop)(?: (?:arrete|stop))+', t):
        return 'silence'
    if t in {'stop', 'arrete', 'arrete toi', 'tais toi', 'chut', 'silence',
             'arrete de parler', 'arrete ta reponse', 'coupe ta voix',
             'stoppe ta voix', 'fais silence', 'ne parle plus', 'attends', 'attend'}:
        return 'silence'
    return None


def demande_fonctionnalites(texte):
    t = demande_directe(texte)
    t = re.sub(r'^(?:me dire|dis moi|me montrer|me donner|savoir|j aimerais connaitre|je voudrais connaitre) ', '', t)
    t = re.sub(r' (?:actuellement|aujourd hui)$', '', t)
    if t in {'fonction', 'fonctions', 'fonctionnalite', 'fonctionnalites',
             'que peux tu faire', 'qu est ce que tu peux faire',
             'qu est ce que tu sais faire', 'tu sais faire quoi',
             'tu peux faire quoi', 'dis moi ce que tu sais faire',
             'dis moi ce que tu peux faire', 'ce que tu sais faire'}:
        return True
    objet = r'(?:les|tes|vos) (?:fonctions?|fonctionnalites?|capacites?)'
    precision = r'(?: (?:actuels?|actuelles?|disponibles?|de red|de l assistant|que tu proposes|que tu as))*'
    debut = r'(?:(?:quels?|quelles?) (?:sont|est) |(?:liste|donne|montre|affiche|presente|rappelle|explique)(?: moi)? |dis moi |connaitre )?'
    return bool(re.fullmatch(debut + objet + precision, t))
