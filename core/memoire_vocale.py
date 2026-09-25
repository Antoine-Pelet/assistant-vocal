"""Dialogue de secrets local et déterministe, en dehors du modèle et des transcriptions affichées."""
import re
from core.memoire_store import ErreurMemoire, normaliser


def reconnaitre(phrase):
    p=normaliser(phrase).strip(' .!?')
    p=re.sub(r'^red\s*[, :]?\s*','',p)
    p=p.replace('’',"'")
    if re.match(r'^(ouvre|deverrouille|consulte|verrouille|ferme|change|modifie|definis|configure).*historique',p):
        if p.startswith(('change','modifie')):return ('changer','_historique')
        if p.startswith(('verrouille','ferme')):return ('verrouiller','_historique')
        return ('ouvrir','_historique')
    for prefixe,action in [
        (r'(?:deverrouille|ouvre) (?:la )?zone ', 'ouvrir'),
        (r'(?:verrouille|ferme) (?:la )?zone ', 'verrouiller'),
        (r'(?:cree|ajoute) (?:une |la )?zone (?:protegee )?', 'creer'),
        (r'(?:change|modifie) (?:le )?mot de passe (?:de )?(?:la )?zone ', 'changer'),
        (r'(?:lis|consulte|cherche dans) (?:la )?zone ', 'lire')]:
        m=re.match(prefixe+r'(.+)$',p)
        if m:
            nom=m.group(1).strip()
            if 'mot de passe' in nom or ' avec ' in nom:
                return ('secret_inline','')
            return (action,re.sub(r"\s+s[' ]il te plait$",'',nom))
    if 'mot de passe' in p or 'phrase secrete' in p:
        return ('secret_inline','')
    return None


def traiter(phrase, magasin, secret, confirmer, dire, lire_prive):
    """Callbacks : secret(prompt), confirmer(prompt)->bool. Aucune valeur secrète n'est renvoyée."""
    intention=reconnaitre(phrase)
    if intention is None:return False
    action,nom=intention
    if action=='secret_inline':
        dire("Demande d'abord le déverrouillage d'une zone ou de l'historique. Je demanderai le mot de passe séparément.")
        return True
    valeurs={}
    mot=ancien=second=None
    try:
        zone=None
        if nom!='_historique' and action!='creer':
            zone=next((z for z in magasin.liste_zones() if normaliser(z['nom'])==nom),None)
            if zone is None:
                dire("Je ne trouve pas cette zone.");return True
        identifiant='_historique' if nom=='_historique' else (zone['id'] if zone else None)
        if action=='verrouiller':
            magasin.bloquer(identifiant);dire("L'accès est verrouillé.");return True
        if action=='lire':
            entrees=magasin.consulter(identifiant)
            if entrees:
                # Aucune liste déchiffrée ne rejoint l'historique conversationnel, le HUD ou un LLM.
                lire_prive(identifiant,entrees)
            else:dire("Cette zone ne contient aucun souvenir accessible.")
            return True
        if action=='creer' and not magasin.acces_historique()['initialise']:
            dire("Définis d'abord le mot de passe de l'historique. Tu peux demander d'ouvrir l'historique.")
            return True
        initialiser=(identifiant=='_historique' and not magasin.acces_historique()['initialise'])
        if action=='ouvrir' and not initialiser:
            mot=secret("Quel est le mot de passe ?")
            if mot is None:return True
            magasin.debloquer(identifiant,mot);dire("L'accès est déverrouillé.");return True
        if action=='changer':
            ancien=secret("Quel est le mot de passe actuel ?")
            if ancien is None:return True
            magasin.debloquer(identifiant,ancien)
        mot=secret("Quel nouveau mot de passe souhaites-tu définir ?")
        if mot is None:return True
        second=secret("Répète ce mot de passe pour le vérifier.")
        if second is None:return True
        if mot!=second:
            dire("Les deux saisies ne correspondent pas. Aucun changement n'a été effectué.");return True
        if identifiant=='_historique':
            operation='historique_initialiser' if initialiser else 'historique_mot_de_passe'
            valeurs=dict(mot_de_passe=mot,ancien_mot_de_passe=ancien or '')
        elif action=='creer':
            operation='zone_creer'
            valeurs=dict(nom=nom,mot_de_passe_action='definir',mot_de_passe=mot)
        else:
            operation='zone_modifier'
            valeurs=dict(zone=identifiant,nom=zone['nom'],debut=zone['debut'],fin=zone['fin'],
                         mot_de_passe_action='definir',ancien_mot_de_passe=ancien or '',mot_de_passe=mot)
        p=magasin.preparer(operation,valeurs,origine='voix')
        valeurs.clear();mot=ancien=second=None
        if confirmer(p['resume']+" Tu confirmes ?"):
            dire(magasin.confirmer(p['jeton'],origine='voix'))
        else:
            magasin.annuler(p['jeton'],origine='voix');dire("D'accord, j'annule.")
    except ErreurMemoire as e:
        dire(str(e))
    except Exception:
        # Ne jamais inclure l'exception ou les variables dans un journal.
        dire("Je n'ai pas pu terminer cette opération confidentielle.")
    finally:
        valeurs.clear();mot=ancien=second=None
    return True
