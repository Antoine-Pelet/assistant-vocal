"""
Assistant vocal local, avec mot d'activation et actions.

Dites « Red », parlez, taisez-vous. Il repond et agit.
Chaine : Vosk/openWakeWord -> faster-whisper -> LLM cloud configurable/Ollama (+ outils)
         -> moteur vocal configurable (Chatterbox/Piper/SAPI)

Architecture : les outils vivent dans tools/ (auto-decouverts via core.registre),
les reglages et secrets dans config.yaml (via core.config).

Usage Windows : lancer_red.bat
"""

import os
import queue
import re
import subprocess
import threading
import time
import wave
from collections import deque
from pathlib import Path

# Magasin de certificats Windows (comme git) au lieu du bundle certifi.
# Indispensable si un antivirus/proxy intercepte le TLS, sinon les appels HTTPS
# (OpenAI, Gmail) echouent avec "certificate verify failed". Avant tout reseau.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass

import numpy as np
import sounddevice as sd

from core import config, journal, memoire, personnalite, registre, voix
from core.contexte import contextual, bind, current
from services.llm.models import ProviderLLM
from core.reveil import charger_reveil, mot_activation, retirer_activation
from core.util import nettoyer_reponse_vocale, sans_accents
from tools.lumieres import allumer_si_nuit, charger_pieces_hue

# ---------------------------------------------------------------- reglages

MICRO = config.reglage(
    "audio.micro", None
)  # None = micro par défaut du système (portable). Mets l'index de TON micro dans config.yaml (voir sounddevice.query_devices()).
# None = sortie audio par defaut de Windows (suit l'enceinte/casque actif).
HAUT_PARLEUR = config.reglage("audio.haut_parleur", None)


def _haut_parleur():
    """Peripherique de sortie TTS COURANT (lu en direct : changeable a la voix via
    l'outil sortie_audio -> config.definir). None = sortie par defaut de Windows."""
    return config.reglage("audio.haut_parleur", None)


# Le choix du LLM (OpenAI/Anthropic/Ollama) et de la voix est gere
# par les providers (core/llm.py, core/tts.py), selon config.yaml
# (mode: local|hybride|qualite).
MODELE_WHISPER = config.reglage("whisper.modele", "medium")

TAUX = 16000  # taux de TRAITEMENT : openWakeWord ET faster-whisper exigent 16 kHz
BLOC = 1280  # 80 ms @ 16 kHz (trame attendue par openWakeWord)

# Taux de CAPTURE du micro. Beaucoup de micros / le mode partagé WASAPI (Windows)
# ne fonctionnent QU'EN 48 kHz : demander 16 kHz échoue alors (« Invalid sample
# rate ») ou sort de l'audio déformé -> wake word et transcription cassés. On
# détecte donc un taux de capture supporté au démarrage (cf. _choisir_taux_capture)
# et on rééchantillonne chaque bloc vers 16 kHz si nécessaire. Définis à 16000 ici
# pour ne rien changer si le micro le supporte (chemin rapide, aucun resample).
CAPTURE_TAUX = TAUX
BLOC_CAPTURE = BLOC

SEUIL_REVEIL = config.reglage(
    "assistant.seuil_reveil", 0.5
)  # sensibilite du mot d'activation
SEUIL_INTERRUPTION = config.reglage(
    "assistant.seuil_interruption", 0.7
)  # couper Red pendant qu'il parle (le micro entend aussi l'enceinte)
# Seuils de NIVEAU (RMS) : dependent du gain du micro. Valeurs par defaut calees
# sur un micro moyen, MAIS auto-calibrees au demarrage selon le bruit ambiant
# (cf. _calibrer_seuils) sauf si tu les fixes toi-meme en config ou desactives
# assistant.auto_calibration. C'est le « regler les niveaux » du retour testeur.
SEUIL_PAROLE_SUR = config.reglage(
    "assistant.seuil_parole", 0.025
)  # au-dessus = parole sure
SEUIL_SILENCE = config.reglage("assistant.seuil_silence", 0.010)  # en-dessous = silence
SILENCE_FIN = config.reglage(
    "assistant.silence_fin", 1.6
)  # s de silence -> fin de phrase
DUREE_MAX = config.reglage("assistant.duree_max", 20)  # s max d'enregistrement
BLOCS_AVANT_VERIF = 5  # 5 x 80 ms = 0,4 s de parole continue
DELAI_ENTRE_VERIFS = 1.0

# Fenetre de suivi : apres une reponse, Red reste a l'ecoute ce nombre de
# secondes pour enchainer une nouvelle demande sans redire "Hey Red".
DUREE_SUITE = config.reglage("assistant.duree_suite", 10)

LOG = journal.obtenir()

# Sentinel renvoye par repondre() quand une action attend une confirmation vocale.
SENTINEL_CONFIRM = "\x00confirmation\x00"
SENTINEL_VEILLE = "\x00veille\x00"


class ArretAssistant(Exception):
    """Sortie normale de Red demandée à la voix (ne concerne pas Windows)."""


# Regles de base (format vocal, outils). La personnalite (persona) est ajoutee
# devant, et la memoire derriere, par _refaire_systeme.
from conversation.prompt import SYSTEME_BASE

# Consigne systeme courante (persona + regles + memoire). Passee a chaque appel
# Claude via le parametre `system`, distinct de la liste des messages.
SYSTEME_COURANT = SYSTEME_BASE
_SIGNATURE_MEMOIRE = None


def _actualiser_memoire(historique, protegees=False):
    """Retire les anciens tours dès qu'un accès, une date ou un souvenir change."""
    global _SIGNATURE_MEMOIRE
    signature, faits = memoire.contexte(protegees=protegees)
    signature = (bool(protegees), signature)
    if _SIGNATURE_MEMOIRE is not None and signature != _SIGNATURE_MEMOIRE:
        dernier = next(
            (
                m
                for m in reversed(historique)
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ),
            None,
        )
        historique[:] = [dernier] if dernier else []
    _SIGNATURE_MEMOIRE = signature
    _refaire_systeme(faits)
    return signature


def _refaire_systeme(memoire_courante):
    from conversation.prompt import build

    global SYSTEME_COURANT
    SYSTEME_COURANT = build(memoire_courante, current())


# ---------------------------------------------------------------- HUD (option)

hud = None  # Interface historique désactivée : fonctionnement vocal headless.
_overlay = None

_dernier_etat_hud = None
_DERNIER_OUTIL = None  # pour la carte overlay
_OUTILS_MUSIQUE = {
    "identifier_musique",
    "identifier_musique_fichier",
    "derniere_musique",
}


_RE_NOMBRE = re.compile(r"\d[\d .,:h]*\d|\d")


def _consultable(texte):
    """Heuristique (mode 'auto') : la reponse contient-elle des donnees a CONSULTER
    (=> fenetre + voix) ou est-ce un simple acquittement ephemere (=> voix seule) ?"""
    t = (texte or "").strip()
    if len(t) > 200:
        return True
    if "\n" in t:  # liste / plusieurs lignes
        return True
    if len(_RE_NOMBRE.findall(t)) >= 2:  # plusieurs nombres (stats, prix, horaires)
        return True
    if "«" in t or '"' in t:  # entite citee (titre, nom, lieu)
        return True
    return False


def _afficher_overlay(texte):
    """Route la reponse vers l'overlay selon un HINT d'outil (affichage: toujours/
    jamais/auto) puis, en 'auto', une heuristique de contenu. Memorise toujours la
    derniere reponse pour la surcharge vocale « affiche-le »."""
    global _DERNIER_OUTIL
    outil_nom = _DERNIER_OUTIL
    _DERNIER_OUTIL = None
    if _overlay is None or not texte:
        return
    typ = "musique" if outil_nom in _OUTILS_MUSIQUE else "reponse"
    try:
        _overlay.memoriser(texte, typ)  # pour « affiche-le »
    except Exception:
        pass
    hint = registre.affichage(outil_nom) if outil_nom else "auto"
    montrer = (hint == "toujours") or (hint != "jamais" and _consultable(texte))
    if montrer:
        try:
            _overlay.afficher(texte, type=typ)
        except Exception:
            pass


def _hud(methode, *args):
    """Relaie un appel au HUD sans jamais interrompre l'assistant."""
    if hud is None or not config.reglage("hud.actif", True):
        return
    global _dernier_etat_hud
    if methode == "etat":
        if args and args[0] == _dernier_etat_hud:
            return
        _dernier_etat_hud = args[0] if args else None
    try:
        getattr(hud, methode)(*args)
    except Exception:
        pass


def _niv_hud(bloc):
    """Convertit le niveau brut du micro en une valeur 0..1 pour le coeur."""
    return min(1.0, niveau(bloc) / 0.2)


def _hud_status():
    """Pousse au HUD le mode de routage et le budget du jour (part Hermes gérée par
    tools.deleguer_a_hermes qui pousse hud.hermes)."""
    try:
        from core.routage import mode_actuel

        _hud("routage", mode_actuel())
    except Exception:
        pass
    try:
        from core import budget

        e = budget.etat()
        _hud(
            "budget",
            round(e["total_jour"], 2),
            e["plafond_jour"],
            round(e["pct_jour"], 3),
        )
    except Exception:
        pass


# ---------------------------------------------------------------- audio


def niveau(bloc_float):
    return float(np.sqrt(np.mean(bloc_float**2)))


def jouer(chemin_wav):
    with wave.open(str(chemin_wav), "rb") as f:
        taux = f.getframerate()
        donnees = f.readframes(f.getnframes())
    audio = np.frombuffer(donnees, dtype=np.int16)
    sd.play(audio, samplerate=taux, device=_haut_parleur())
    sd.wait()


def bip(frequence=880, duree=0.12):
    t = np.linspace(0, duree, int(TAUX * duree), endpoint=False)
    onde = (0.25 * np.sin(2 * np.pi * frequence * t)).astype(np.float32)
    sd.play(onde, samplerate=TAUX, device=_haut_parleur())
    sd.wait()


_PROCESSUS_PAROLE = None
_VERROU_PAROLE = threading.RLock()
_CONTEXTE_REPONSE = threading.local()
_NUMERO_ACCUSE = 0
_TOUR_ACTIF = None
_DETECTEUR_INTERRUPTION = None
_TEXTE_PARLE = ""
_AUDIO_INTERRUPTION = deque(maxlen=25)
_INTERRUPTION = threading.Event()
_PARLE = threading.Event()  # vrai UNIQUEMENT pendant que Red joue de l'audio :
# c'est la seule fenetre ou on ecoute une interruption.
_CAPTURE_MUSIQUE = threading.Event()  # vrai pendant la capture Shazam : la boucle de
# surveillance lache alors flux (le micro est pris).
_MICRO_MUET = threading.Event()  # vrai = wake word coupe (mute micro) : stream/call.


def basculer_micro(force=None):
    """Coupe/reactive l'ecoute du mot d'activation. force=True mute, False reactive,
    None bascule. Feedback bip + HUD. Renvoie True si desormais muet."""
    if force is True or (force is None and not _MICRO_MUET.is_set()):
        _MICRO_MUET.set()
    else:
        _MICRO_MUET.clear()
    muet = _MICRO_MUET.is_set()
    if muet:
        couper_parole()
    try:
        bip(400 if muet else 900, 0.10)
    except Exception:
        pass
    _hud("micro", muet)
    print("  [micro] " + ("coupe (mute)" if muet else "reactive"))
    return muet


def _est_interrompu():
    annulation = getattr(_CONTEXTE_REPONSE, "annulation", None)
    return _INTERRUPTION.is_set() or (annulation is not None and annulation.is_set())


def couper_parole():
    """Arrete immediatement la synthese en cours (ElevenLabs ou SAPI)."""
    _INTERRUPTION.set()
    if _TOUR_ACTIF is not None:
        _TOUR_ACTIF.set()
    try:
        sd.stop()  # coupe la lecture ElevenLabs sur le haut-parleur
    except Exception:
        pass
    processus = _PROCESSUS_PAROLE
    if processus is not None and processus.poll() is None:
        try:
            processus.terminate()
        except OSError:
            pass


def _jouer_audio(audio, frequence):
    """Joue un tableau int16 mono sur le haut-parleur, interruptible."""
    if _est_interrompu():
        return
    sd.play(audio, samplerate=frequence, device=_haut_parleur())
    while not _est_interrompu():
        courant = sd.get_stream()
        if courant is None or not courant.active:
            break
        time.sleep(0.03)
    if _est_interrompu():
        sd.stop()


def dire(texte, interruptible=True):
    # La réponse finale attend son accusé de réception ; toutes les voix sont
    # sérialisées pour ne pas écraser sd.play() ni partager Piper simultanément.
    fil = getattr(_CONTEXTE_REPONSE, "accuse", None)
    if fil is not None and fil is not threading.current_thread():
        fil.join()
    with _VERROU_PAROLE:
        debut = time.monotonic()
        _dire(texte, interruptible)
        LOG.info(
            "voix %.3fs (%s caracteres)", time.monotonic() - debut, len(texte or "")
        )


def _dire(texte, interruptible=True):
    """Prononce un texte via le provider TTS courant (ElevenLabs en cloud, Piper en
    local) ; repli sur la voix Windows (SAPI) si le provider est indisponible.

    interruptible=False : le barge-in est desactive pendant cette phrase (utilise
    pour la question de confirmation : la reponse de l'utilisateur est un oui/non,
    pas une interruption)."""
    if _overlay is not None and _overlay.est_muet():  # mode "silencieux visuel" :
        return  # la reponse s'affiche, pas de TTS.
    if _est_interrompu():
        return
    global _TEXTE_PARLE
    from core.tts import tts

    resultat = tts().synthetiser(texte)
    if _est_interrompu():
        return
    _TEXTE_PARLE = texte
    if interruptible:
        _PARLE.set()  # a partir d'ici Red parle : on peut l'interrompre
    try:
        if resultat is not None:
            _jouer_audio(*resultat)
        else:
            _dire_sapi(texte)
    finally:
        _PARLE.clear()  # fin de la parole : plus d'interruption possible
        _TEXTE_PARLE = ""


def _dire_sapi(texte, confidentiel=False):
    """Synthese vocale Windows (SAPI), voix francaise si disponible.

    Le texte est envoye au script PowerShell par l'entree standard, jamais dans
    -Command : une apostrophe francaise ne peut pas casser le littoral. Le flux
    stdin est lu en UTF-8. L'appel est interruptible via couper_parole().
    """
    global _PROCESSUS_PAROLE

    if _est_interrompu():
        return

    script = (
        "[Console]::InputEncoding = [Text.Encoding]::UTF8; "
        "$t = [Console]::In.ReadToEnd(); "
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$fr = $s.GetInstalledVoices() | "
        "Where-Object { $_.VoiceInfo.Culture.Name -like 'fr*' } | "
        "Select-Object -First 1; "
        "if ($fr) { $s.SelectVoice($fr.VoiceInfo.Name) }; "
        "$s.Rate = 1; "
        "$s.Speak($t)"
    )

    processus = subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    _PROCESSUS_PAROLE = processus
    try:
        if _est_interrompu():
            processus.terminate()
            processus.communicate()
            return
        _, erreurs = processus.communicate(input=texte.encode("utf-8"))
        if processus.returncode and not _est_interrompu():
            details = (
                "Lecture confidentielle interrompue."
                if confidentiel
                else (erreurs or b"").decode("utf-8", "replace").strip()
            )
            print(f"  [SAPI] echec (code {processus.returncode}) : {details}")
    finally:
        _PROCESSUS_PAROLE = None


# ---------------------------------------------------------------- nettoyage

# Ce que Whisper entend a la place de "Hey Red" quand le tampon
# glissant en rattrape la fin.
RESIDUS = (
    "avis",
    "service",
    "jarvis",
    "hey jarvis",
    "harvis",
    "arvis",
    "javis",
    "charvis",
    "chavis",
    "davis",
    "y a vis",
    "a vis",
    "la vis",
    "et vis",
    "ervice",
    "servi",
    "sers vis",
)

# Ce que Whisper invente quand il n'entend que du silence.
HALLUCINATIONS = (
    "amara.org",
    "sous-titres",
    "sous titres",
    "merci d'avoir regarde",
    "abonnez-vous",
    "abonnez vous",
    "a la prochaine video",
    "n'oubliez pas de vous abonner",
    "sous-titrage",
)

# Mots qui coupent la parole PUIS relancent l'ecoute (tu veux redire quelque chose).
MOTS_RELANCE = (
    "attends",
    "attend",
    "arrete",
    "arrete-toi",
    "arrete toi",
    "stop",
    "une seconde",
    "deux secondes",
    "minute",
    "pardon",
    "non non",
)

# Mots qui coupent la parole et terminent (tu as fini, il se tait).
MOTS_FIN = (
    "tais-toi",
    "tais toi",
    "chut",
    "silence",
    "ferme-la",
    "la ferme",
    "c'est bon",
    "ok merci",
    "d'accord merci",
    "laisse tomber",
)

# Mots d'accord pour une confirmation vocale.
MOTS_OUI = (
    "oui",
    "ouais",
    "ouep",
    "vas-y",
    "vas y",
    "confirme",
    "confirmer",
    "d'accord",
    "daccord",
    "ok",
    "okay",
    "envoie",
    "envoi",
    "fais",
    "yes",
    "carrement",
    "bien sur",
    "parfait",
    "valide",
    "valider",
)


def type_arret(texte):
    from core.commandes_vocales import commande_assistant

    return (
        "relance"
        if commande_assistant(texte) in {"silence", "veille", "quitter"}
        else None
    )


def _est_oui(texte):
    """Vrai si la transcription exprime un accord (oui/vas-y/confirme...)."""
    if not texte:
        return False
    plat = sans_accents(texte.replace("’", "'").replace("‘", "'"))
    plat = "".join(c if c.isalnum() or c in " '-" else " " for c in plat)
    return any(m in plat for m in MOTS_OUI)


def _est_toujours(texte):
    """Vrai si l'utilisateur ajoute 'toujours' (memoriser l'autorisation, N2)."""
    return bool(texte) and "toujours" in sans_accents(texte)


def nettoyer(texte):
    """Retire le residu du mot d'activation en tete de transcription."""
    t = retirer_activation(texte)

    plat = sans_accents(t)
    if any(h in plat for h in HALLUCINATIONS):
        return ""

    # Cas "Avis, ouvre YouTube" ou "Red : ouvre YouTube"
    tete = None
    for sep in (",", ":", ".", "!", "?"):
        if sep in t[:20]:
            avant, _, apres = t.partition(sep)
            if len(avant.split()) <= 3:
                tete, reste = avant, apres
                break

    if tete is not None:
        if tete.strip().lower().strip("'’") in RESIDUS:
            t = reste.strip()

    # Cas sans ponctuation : "Red ouvre YouTube"
    mots = t.split()
    if mots and mots[0].lower().strip(",.:;!?") in RESIDUS:
        t = " ".join(mots[1:])

    return t.strip()


# ---------------------------------------------------------------- parole en flux

FIN_PHRASE = re.compile(r"(.+?[.!?…]+[\s ]*|.+?\n)", re.S)


def _parleur(fil):
    """Thread qui lit les phrases au fur et a mesure qu'elles arrivent."""
    while True:
        phrase = fil.get()
        if phrase is None:
            break
        if _est_interrompu():
            continue
        texte = phrase.strip()
        if texte:
            dire(texte)


def dire_en_flux(morceaux):
    """Consomme un generateur de fragments et les dit phrase par phrase."""
    fil = queue.Queue()
    thread = threading.Thread(target=bind(_parleur), args=(fil,), daemon=True)
    thread.start()

    tampon = ""
    complet = []
    try:
        for fragment in morceaux:
            if _est_interrompu():
                break
            if not fragment:
                continue
            tampon += fragment
            complet.append(fragment)
            while True:
                trouve = FIN_PHRASE.match(tampon)
                if not trouve:
                    break
                phrase = trouve.group(1)
                tampon = tampon[len(phrase) :]
                if len(phrase.strip()) >= 2:
                    fil.put(phrase)
        if tampon.strip():
            fil.put(tampon)
    finally:
        fil.put(None)
        thread.join()

    return "".join(complet).strip()


# ---------------------------------------------------------------- dialogue


class _LocalOutput:
    def say(self, text, interruptible=True):
        return dire(text, interruptible=interruptible)

    def event(self, *args):
        return _hud(*args)

    def cancelled(self):
        return _est_interrompu()

    def last_tool(self, name):
        global _DERNIER_OUTIL
        _DERNIER_OUTIL = name

    def execute(self, blocks):
        return _executer_outils(blocks)

    def priority(self, history):
        return _repondre_route_prioritaire_commune(history)


def _executer_outils(blocs):
    from conversation.manager import manager

    return manager.execute_tools(manager.session(), blocs, _LocalOutput())


def _repondre_route_prioritaire_commune(historique):
    from conversation.manager import manager

    return manager.priority(
        manager.session(history=historique), historique, _LocalOutput()
    )


def repondre(historique):
    """Accuse réception dès la transcription, pendant que le modèle travaille."""
    global _NUMERO_ACCUSE
    fil = None
    if config.reglage("assistant.accuse_reception", True):
        phrases = ("Compris.", "Très bien, je regarde ça.", "D'accord, je m'en occupe.")
        phrase = phrases[_NUMERO_ACCUSE % len(phrases)]
        _NUMERO_ACCUSE += 1
        _hud("dire_jarvis", phrase)
        annulation = getattr(_CONTEXTE_REPONSE, "annulation", None)

        def prononcer_accuse():
            _CONTEXTE_REPONSE.annulation = annulation
            dire(phrase)

        fil = threading.Thread(
            target=bind(prononcer_accuse), name="accuse-reception", daemon=True
        )
        _CONTEXTE_REPONSE.accuse = fil
        fil.start()
    try:
        return _repondre_sans_accuse(historique)
    finally:
        if fil:
            fil.join()
        _CONTEXTE_REPONSE.accuse = None


def _repondre_sans_accuse(historique):
    from conversation.manager import manager

    return manager.respond(manager.session(history=historique), _LocalOutput())


# ---------------------------------------------------------------- whisper


def charger_whisper():
    from services.stt.faster_whisper import model

    return model()


def _choisir_taux_capture(device):
    """Taux de capture supporté par le micro. Préfère 16 kHz (aucun resample) ;
    sinon le taux natif du périphérique (souvent 48 kHz). Surchargé par audio.taux."""
    force = config.reglage("audio.taux", None)
    if force:
        return int(force)
    try:
        sd.check_input_settings(
            device=device, samplerate=TAUX, channels=1, dtype="float32"
        )
        return TAUX  # le micro fait du 16 kHz : chemin rapide
    except Exception:
        pass
    try:
        info = sd.query_devices(device, "input")
        tx = int(round(info.get("default_samplerate") or 48000))
        return tx if tx > 0 else 48000
    except Exception:
        return 48000


def _vers_16k(bloc):
    """Rééchantillonne un bloc mono float32 de CAPTURE_TAUX vers 16 kHz (TAUX)."""
    if CAPTURE_TAUX == TAUX:
        return bloc
    from math import gcd
    from scipy.signal import resample_poly

    g = gcd(TAUX, CAPTURE_TAUX)
    return resample_poly(bloc, TAUX // g, CAPTURE_TAUX // g).astype(np.float32)


def lire_bloc(flux):
    """Lit un bloc du micro et renvoie ~80 ms d'audio 16 kHz mono float32,
    en rééchantillonnant si le micro ne capture pas nativement en 16 kHz."""
    bloc, _ = flux.read(BLOC_CAPTURE)
    return _vers_16k(bloc.flatten())


def _calibrer_seuils(flux, secondes=1.0):
    """Mesure le bruit ambiant ~1 s et renvoie (seuil_silence, seuil_parole)
    adaptés au micro et à la pièce. À appeler au démarrage, l'utilisateur ne
    parlant pas. Renvoie None si la mesure échoue.

    Idée : les seuils absolus dépendent du gain du micro ; on les cale au-dessus
    du plancher de bruit mesuré (médiane, robuste aux transitoires)."""
    niveaux = []
    t0 = time.time()
    while time.time() - t0 < secondes:
        try:
            niveaux.append(niveau(lire_bloc(flux)))
        except Exception:
            break
    if len(niveaux) < 4:
        return None
    niveaux.sort()
    fond = niveaux[len(niveaux) // 2]  # médiane = plancher de bruit
    seuil_silence = min(0.05, max(0.004, fond * 2.0))
    seuil_parole = min(0.12, max(0.010, fond * 4.5))
    return seuil_silence, seuil_parole


def capturer(flux, tampon, duree_min=0.3, attente_debut=None):
    from core.conversation_audio import capturer_phrase

    return capturer_phrase(
        lambda: lire_bloc(flux),
        tampon,
        taux=TAUX,
        seuil=SEUIL_SILENCE,
        silence_fin=float(config.reglage("assistant.silence_fin", 1.6)),
        attente_debut=(
            float(config.reglage("assistant.attente_debut", 4.0))
            if attente_debut is None
            else attente_debut
        ),
        duree_max=DUREE_MAX,
        duree_min=duree_min,
        observer=lambda b: _hud("niveau", _niv_hud(b)),
    )


def attendre_suite(flux, tampon, duree=None):
    """Ecoute quelques secondes apres une reponse, sans mot d'activation.

    Renvoie True si l'utilisateur recommence a parler, False si silence.
    """
    _hud("etat", "ecoute")
    tampon.clear()
    duree = (
        float(config.reglage("assistant.duree_suite", 10)) if duree is None else duree
    )
    debut = time.monotonic()
    blocs_voix = 0
    while time.monotonic() - debut < duree:
        if _MICRO_MUET.is_set():
            return False
        try:
            bloc = lire_bloc(flux)
        except Exception:
            return False
        tampon.append(bloc)
        _hud("niveau", _niv_hud(bloc))
        if niveau(bloc) > SEUIL_PAROLE_SUR:
            blocs_voix += 1
            if blocs_voix >= 3:
                return True
        else:
            blocs_voix = 0
    return False


def _dire_en_vidant_micro(texte, flux):
    _INTERRUPTION.clear()
    _hud("etat", "parole")
    _hud("dire_jarvis", texte)
    fil = threading.Thread(target=bind(dire), args=(texte, False), daemon=True)
    fil.start()
    detecteur = _DETECTEUR_INTERRUPTION
    if detecteur:
        detecteur.reset()
    while fil.is_alive():
        try:
            bloc = lire_bloc(flux)
            if detecteur and _TEXTE_PARLE and not _MICRO_MUET.is_set():
                if detecteur.analyser((bloc * 32767).astype(np.int16), _TEXTE_PARLE):
                    couper_parole()
                    break
        except Exception:
            break
    fil.join()
    try:
        disponibles = int(flux.read_available)
        if disponibles > 0:
            flux.read(disponibles)
    except Exception:
        pass


def attendre_apres_reponse(
    flux, tampon, whisper, reveil, delai_initial=None, forcer_confirmation=False
):
    """Retourne (audio, transcription éventuelle), ou None après accord/mute."""
    if not forcer_confirmation and attendre_suite(flux, tampon, duree=delai_initial):
        audio = capturer(flux, tampon)
        if audio is not None:
            return audio, None
    if _MICRO_MUET.is_set() or (
        not forcer_confirmation
        and not config.reglage("assistant.confirmer_veille", True)
    ):
        return None
    _dire_en_vidant_micro("Est-ce que je peux me mettre en veille ?", flux)
    _hud("confirmation", True)
    reveil.reset()
    bip()
    premiere = True
    from core.conversation_audio import intention_veille

    try:
        while not _MICRO_MUET.is_set():
            _hud("etat", "ecoute")
            if not premiere and not attendre_suite(flux, tampon, duree=30.0):
                continue
            premiere = False
            audio = capturer(
                flux,
                tampon,
                duree_min=0.2,
                attente_debut=float(
                    config.reglage("assistant.attente_confirmation", 6.0)
                ),
            )
            if audio is None:
                continue  # le silence ne vaut pas un accord et ne répète pas la question
            texte = transcrire_demande(whisper, audio)
            from core.commandes_vocales import commande_assistant

            controle = commande_assistant(texte)
            if controle == "quitter":
                _arreter_assistant(flux)
            if controle == "silence":
                continue
            intention = "veille" if controle == "veille" else intention_veille(texte)
            _hud("dire_vous", texte)
            if intention == "veille":
                _dire_en_vidant_micro("Très bien, je passe en veille.", flux)
                tampon.clear()
                reveil.reset()
                return None
            if intention == "commande":
                return audio, texte
            if intention == "continuer":
                _dire_en_vidant_micro("Je reste à l'écoute.", flux)
    finally:
        _hud("confirmation", False)
    return None


def repondre_en_ecoutant(historique, flux, reveil, whisper):
    """Surveille les commandes courtes en continu, sans attendre 400 ms de cri."""
    global _TOUR_ACTIF
    _INTERRUPTION.clear()
    _AUDIO_INTERRUPTION.clear()
    annulation = threading.Event()
    _TOUR_ACTIF = annulation
    resultat = {}
    historique_tour = list(historique)
    detecteur = _DETECTEUR_INTERRUPTION
    if detecteur:
        detecteur.reset()

    def travail():
        _CONTEXTE_REPONSE.annulation = annulation
        try:
            resultat["texte"] = repondre(historique_tour)
        except Exception as e:
            resultat["erreur"] = e

    thread = threading.Thread(target=bind(travail), daemon=True)
    thread.start()
    interrompu = False
    tampon = deque(maxlen=25)
    voix = 0
    derniere_verif = 0.0
    while thread.is_alive():
        if annulation.is_set():
            interrompu = True
            break
        if _CAPTURE_MUSIQUE.is_set():
            time.sleep(0.05)
            continue
        try:
            bloc = lire_bloc(flux)
        except Exception:
            if _CAPTURE_MUSIQUE.is_set():
                continue
            couper_parole()
            interrompu = True
            break
        _hud("niveau", _niv_hud(bloc))
        if _MICRO_MUET.is_set() or not _PARLE.is_set():
            tampon.clear()
            voix = 0
            if detecteur:
                detecteur.reset()
            continue
        tampon.append(bloc)
        pcm = (bloc * 32767).astype(np.int16)
        dit = None
        if detecteur:
            dit = detecteur.analyser(
                pcm, _TEXTE_PARLE, seuil=min(SEUIL_PAROLE_SUR, 0.006)
            )
        else:
            # Repli pour une installation sans Vosk : garder aussi le début
            # et la fin du mot court, puis vérifier au premier silence.
            if max(reveil.predict(pcm).values()) >= SEUIL_INTERRUPTION:
                dit = mot_activation()
            voix += int(niveau(bloc) > SEUIL_SILENCE)
            maintenant = time.monotonic()
            if (
                not dit
                and voix >= 2
                and niveau(bloc) <= SEUIL_SILENCE
                and maintenant - derniere_verif >= 0.5
            ):
                derniere_verif = maintenant
                extrait = np.pad(np.concatenate(tampon), (0, 3200))
                seg, _ = whisper.transcribe(
                    extrait,
                    language="fr",
                    beam_size=1,
                    condition_on_previous_text=False,
                )
                candidat = " ".join(x.text for x in seg).strip()
                if type_arret(candidat):
                    dit = candidat
                voix = 0
        if dit:
            couper_parole()
            interrompu = True
            from core.commandes_vocales import normaliser

            # Garder « Red… » / « arrête… » pour finir de capter une commande
            # plus longue après l'interruption, sans perdre son début.
            if normaliser(dit) not in {
                "stop",
                "red stop",
                "chut",
                "silence",
                "tais toi",
                "arrete de parler",
            }:
                _AUDIO_INTERRUPTION.extend(tampon)
            print(f"  [micro] Parole interrompue : {dit}")
            break

    thread.join(timeout=0.5 if interrompu else 10)
    reveil.reset()
    if _TOUR_ACTIF is annulation:
        _TOUR_ACTIF = None
    if interrompu:
        registre.annuler_confirme()
        return "", True, not _MICRO_MUET.is_set()
    if "erreur" in resultat:
        raise resultat["erreur"]
    historique[:] = historique_tour
    return resultat.get("texte", ""), False, False


def _confirmer(interrompu, relancer, whisper, historique, flux):
    """Capture la reponse oui/non a une demande de confirmation et agit."""
    if interrompu:
        registre.annuler_confirme()
        return "", relancer

    _INTERRUPTION.clear()
    _hud("etat", "ecoute")
    audio_conf = capturer(
        flux,
        deque(),
        duree_min=0.3,
        attente_debut=float(config.reglage("assistant.attente_confirmation", 3.0)),
    )
    reponse = ""
    if audio_conf is not None:
        seg, _ = whisper.transcribe(audio_conf, language="fr", beam_size=5)
        reponse = nettoyer(" ".join(s.text for s in seg).strip())
    print(f"  [confirmation] {reponse or '(rien)'}")

    memoriser = _est_toujours(reponse)
    from core.memoire_store import accord_explicite

    accord = (
        accord_explicite(reponse)
        if registre.nom_en_attente() in ("remember", "forget")
        else (_est_oui(reponse) or memoriser)
    )
    if accord:
        res = registre.executer_confirme(memoriser=memoriser)
        _refaire_systeme(memoire.charger())
    else:
        registre.annuler_confirme()
        res = "D'accord, j'annule."

    _hud("etat", "parole")
    if res and not _est_interrompu():
        _dire_en_vidant_micro(res, flux)
    historique.append({"role": "assistant", "content": res})
    return res, False


def _tronquer(historique):
    if len(historique) > 40:
        del historique[: len(historique) - 40]
        # Les fournisseurs cloud exigent un vrai premier tour utilisateur.
        while historique and not (
            historique[0]["role"] == "user"
            and isinstance(historique[0]["content"], str)
        ):
            historique.pop(0)


def transcrire_demande(whisper, audio):
    debut_stt = time.monotonic()
    segments, _ = whisper.transcribe(
        audio,
        language="fr",
        beam_size=3,
        condition_on_previous_text=False,
        initial_prompt=f"{mot_activation().capitalize()}, assistant vocal.",
    )
    question = nettoyer(" ".join(s.text for s in segments).strip())
    LOG.info(
        "latence STT %.3fs (audio %.2fs)",
        time.monotonic() - debut_stt,
        len(audio) / TAUX,
    )
    return question


def _arreter_assistant(flux):
    couper_parole()
    _dire_en_vidant_micro("D'accord, j'arrête Red. À bientôt.", flux)
    raise ArretAssistant()


def _lire_secret_local(whisper, flux, question):
    """Capture dédiée : aucun nettoyage conversationnel, affichage, log ou fichier audio."""
    audio_secret = None
    segments = None
    try:
        _INTERRUPTION.clear()
        _dire_en_vidant_micro(question, flux)
        bip()
        audio_secret = capturer(flux, deque(), duree_min=0.3, attente_debut=15.0)
        if audio_secret is None or _est_interrompu():
            return None
        segments, _ = whisper.transcribe(
            audio_secret, language="fr", beam_size=5, condition_on_previous_text=False
        )
        texte = " ".join(s.text for s in segments).strip()
        return None if _est_interrompu() else texte
    finally:
        if audio_secret is not None:
            audio_secret.fill(0)
        segments = None
        _AUDIO_INTERRUPTION.clear()


def _lecture_memoire_privee(store, identifiant, entrees):
    """SAPI dans un processus éphémère : pas de modèle/TTS persistant, HUD ou journal."""

    def revoquer():
        couper_parole()

    texte = ""
    courantes = []
    try:
        with _VERROU_PAROLE:
            with store.verrou:
                _INTERRUPTION.clear()
                store.observateurs.append(revoquer)
                courantes = store.consulter(identifiant)
                texte = "; ".join(e["contenu"] for e in courantes)
                _PARLE.set()
            _dire_sapi(texte, confidentiel=True)
    finally:
        texte = ""
        courantes.clear()
        entrees.clear()
        _PARLE.clear()
        if revoquer in store.observateurs:
            store.observateurs.remove(revoquer)


def _traiter_memoire_confidentielle(question, whisper, flux):
    from core import memoire_vocale
    from core.memoire_store import accord_explicite

    if memoire_vocale.reconnaitre(question) is None:
        return False
    store = memoire.magasin()

    def saisir(prompt):
        return _lire_secret_local(whisper, flux, prompt)

    def valider(prompt):
        return accord_explicite(saisir(prompt) or "")

    try:
        return memoire_vocale.traiter(
            question,
            store,
            saisir,
            valider,
            lambda texte: _dire_en_vidant_micro(texte, flux),
            lambda zone, entrees: _lecture_memoire_privee(store, zone, entrees),
        )
    finally:
        _AUDIO_INTERRUPTION.clear()


@contextual
def traiter(audio, whisper, historique, flux, reveil, question=None):
    """Transcrit, répond, parle. True permet de reformuler sans mot d'activation."""
    if question is None:
        question = transcrire_demande(whisper, audio)

    if not question or len(question) < 3:
        print("  (rien compris)\n")
        _dire_en_vidant_micro(
            "Je n’ai pas bien compris. Peux-tu répéter après le bip ?", flux
        )
        bip()
        return True

    if _traiter_memoire_confidentielle(question, whisper, flux):
        return True

    print(f"  Vous : {question}")
    _hud("dire_vous", question)
    from core.commandes_vocales import commande_assistant

    controle = commande_assistant(question)
    if controle == "quitter":
        _arreter_assistant(flux)
    if controle == "veille":
        return SENTINEL_VEILLE
    if controle == "silence":
        couper_parole()
        _hud("dire_jarvis", "Parole interrompue.")
        return True
    _hud("etat", "reflexion")
    historique.append({"role": "user", "content": question})

    texte, interrompu, relancer = repondre_en_ecoutant(
        historique, flux, reveil, whisper
    )

    if interrompu:
        _hud("dire_jarvis", "Parole interrompue.")
        return relancer
    if texte == SENTINEL_CONFIRM:
        _hud("confirmation", True)
        texte, relancer = _confirmer(interrompu, relancer, whisper, historique, flux)
        _hud("confirmation", False)
    elif not texte:
        texte = "C'est fait."
        if not interrompu:
            _hud("etat", "parole")
            _dire_en_vidant_micro(texte, flux)

    _hud("dire_jarvis", texte)
    _afficher_overlay(texte)
    _hud_status()
    print(f"  Red : {texte}\n")
    _tronquer(historique)
    return relancer


def _feedback_geste(geste):
    """Feedback discret quand un geste est reconnu : petit bip + flash HUD. Non bloquant."""
    freq = 1200 if geste == "armement" or geste.startswith("mode_") else 900
    try:
        threading.Thread(target=lambda: bip(freq, 0.05), daemon=True).start()
    except Exception:
        pass
    _hud("outil", "geste", geste)


def _installer_raccourci_gestes():
    """Raccourcis globaux des mains et du regard (optionnels, via keyboard)."""
    combo = config.reglage("gestes.raccourci", "ctrl+alt+g")
    combo_demo = config.reglage("gestes.raccourci_demo", "ctrl+alt+d")
    combo_regard = config.reglage("gestes.raccourci_regard", "ctrl+alt+r")
    if not combo and not combo_demo and not combo_regard:
        return
    try:
        import keyboard
    except Exception:
        return  # lib absente : le raccourci est optionnel, on continue sans
    from core import gestes

    def _toggle():
        print(gestes.arreter() if gestes.actif() else gestes.demarrer())

    def _demo():
        print(gestes.demarrer_demo())

    def _regard():
        print(
            gestes.arreter_regard()
            if gestes.regard_actif()
            else gestes.demarrer_regard()
        )

    try:
        if combo:
            keyboard.add_hotkey(combo, _toggle)
            print(f"Raccourci gestes : {combo}")
        if combo_demo:
            keyboard.add_hotkey(combo_demo, _demo)
            print(f"Raccourci démo gestes : {combo_demo}")
        if combo_regard:
            keyboard.add_hotkey(combo_regard, _regard)
            print(f"Raccourci regard : {combo_regard}")
    except Exception:
        LOG.exception("gestes: raccourci clavier")


def _installer_raccourci_micro():
    try:
        import keyboard
    except ImportError:
        return
    for cle, defaut, action, label in (
        ("audio.raccourci_mute", "ctrl+alt+m", basculer_micro, "mute micro"),
        ("audio.raccourci_stop", "ctrl+alt+space", couper_parole, "couper la voix"),
    ):
        combo = config.reglage(cle, defaut)
        if combo:
            try:
                keyboard.add_hotkey(combo, action)
                print(f"Raccourci {label} : {combo}")
            except Exception:
                LOG.exception("raccourci %s", cle)


def _main():
    print("Chargement des modeles...")

    registre.charger_outils()
    voix.definir_parleur(dire)
    try:
        from tools.alexa import precharger_routines

        precharger_routines()
    except Exception:
        LOG.exception("Alexa: préchargement des routines")

    whisper = charger_whisper()
    reveil = charger_reveil(whisper)
    global _DETECTEUR_INTERRUPTION
    try:
        from core.interruption_vocale import DetecteurInterruption

        modele_vosk = getattr(reveil, "_modele", None)
        if modele_vosk is not None:
            _DETECTEUR_INTERRUPTION = DetecteurInterruption(
                modele_vosk, mot_activation()
            )
            print("Interruption vocale active : dites stop pendant une réponse.")
    except Exception:
        LOG.exception("interruption Vosk indisponible, repli Whisper")

    # Les intégrations facultatives ne chargent leurs SDK que si activées.
    if config.reglage("twilio.account_sid") or config.reglage("twilio.sid"):
        try:
            from tools.appels import definir_transcripteur
            from tools.appel_direct import definir_transcripteur_direct

            definir_transcripteur(
                lambda chemin: " ".join(
                    s.text
                    for s in whisper.transcribe(chemin, language="fr", beam_size=5)[0]
                ).strip()
            )
            definir_transcripteur_direct(
                lambda audio: " ".join(
                    s.text
                    for s in whisper.transcribe(audio, language="fr", beam_size=1)[0]
                ).strip()
            )
        except ImportError:
            LOG.warning("Appels configurés mais dépendances calls absentes.")
    charger_pieces_hue()
    allumer_si_nuit()
    for key, module, function in (
        ("presence.ip", "tools.presence", "demarrer_presence"),
        ("discord.token", "tools.discord_bot", "demarrer_discord"),
        ("instagram.comptes", "tools.instagram", "demarrer_refresh_instagram"),
    ):
        if config.reglage(key, False) or (
            key == "instagram.comptes" and config.reglage("instagram.access_token")
        ):
            try:
                from importlib import import_module

                getattr(import_module(module), function)()
            except Exception:
                LOG.warning("Intégration indisponible : %s", module)

    # Serveur web unifie (pont iPhone + webhook Twilio + panneau + gestes en loopback).
    if (
        config.reglage("serveur.actif", False)
        or config.reglage("pont_iphone.actif", False)
        or config.reglage("gestes.actif", False)
        or (config.reglage("satellites", []) or [])
    ):  # satellites -> serveur requis
        from core.serveur import demarrer as demarrer_serveur_web

        demarrer_serveur_web()
    # Controle par gestes (webcam, sous-process isole 3.11) : hooks + demarrage optionnel.
    try:
        import atexit
        from core import gestes

        gestes.definir_hooks(couper_tts=couper_parole, feedback=_feedback_geste)
        atexit.register(gestes.arreter_regard)  # libère le regard à la sortie
        atexit.register(gestes.arreter)  # libère le tracker invisible
        if config.reglage("gestes.actif", False):
            print(gestes.demarrer())
        _installer_raccourci_gestes()
        _installer_raccourci_micro()
    except Exception:
        LOG.exception("gestes: initialisation")

    from core.llm import llm

    _fournisseur = llm()
    print(
        f"Mode : {config.reglage('mode', 'cloud')} — LLM {_fournisseur.nom}, "
        f"TTS {__import__('core.tts', fromlist=['tts']).tts().nom}."
    )
    if not _fournisseur.disponible():
        if config.reglage("mode", "cloud") == "local":
            print(
                "ATTENTION : Ollama injoignable. Lance 'ollama serve' et verifie le "
                "modele (config ollama.modele)."
            )
        else:
            from core import cloud

            nom_cle = (
                "openai.cle" if cloud.fournisseur() == "openai" else "anthropic.cle"
            )
            print(
                f"ATTENTION : aucune cle cloud dans config.yaml ({nom_cle}). "
                "L'assistant ne pourra pas repondre."
            )

    _hud("demarrer")
    _modele_hud = getattr(_fournisseur, "modele", "")
    _hud(
        "config",
        f"{_fournisseur.nom} · {_modele_hud}" if _modele_hud else _fournisseur.nom,
        f"whisper {MODELE_WHISPER}",
    )
    _hud_status()
    faits = memoire.charger()
    if faits:
        print(f"Memoire : {len(faits)} information(s).")
    _refaire_systeme(faits)
    historique = []

    global CAPTURE_TAUX, BLOC_CAPTURE
    CAPTURE_TAUX = _choisir_taux_capture(MICRO)
    BLOC_CAPTURE = int(round(BLOC * CAPTURE_TAUX / TAUX))  # ~80 ms au taux de capture
    if CAPTURE_TAUX != TAUX:
        print(
            f"[audio] micro en {CAPTURE_TAUX} Hz -> reechantillonnage vers {TAUX} Hz "
            f"(bloc {BLOC_CAPTURE} -> {BLOC})"
        )
    try:
        flux = sd.InputStream(
            samplerate=CAPTURE_TAUX,
            channels=1,
            dtype="float32",
            device=MICRO,
            blocksize=BLOC_CAPTURE,
        )
        flux.start()
    except (sd.PortAudioError, ValueError) as erreur:
        raise RuntimeError(
            "Impossible d'ouvrir le micro. Connecte le casque choisi dans audio.micro "
            "et vérifie les permissions Windows (Confidentialité > Microphone). "
            "Utilise lancer_red.bat pour lancer le Python standard du projet."
        ) from erreur

    # Auto-calibration des seuils de niveau selon le bruit ambiant (portabilité :
    # s'adapte au gain du micro et à la pièce). Ignorée si tu fixes toi-même
    # assistant.seuil_silence / seuil_parole, ou si assistant.auto_calibration = false.
    if (
        config.reglage("assistant.auto_calibration", True)
        and config.reglage("assistant.seuil_silence", None) is None
        and config.reglage("assistant.seuil_parole", None) is None
    ):
        global SEUIL_SILENCE, SEUIL_PAROLE_SUR
        cal = _calibrer_seuils(flux)
        if cal:
            SEUIL_SILENCE, SEUIL_PAROLE_SUR = cal
            print(
                f"[audio] seuils auto-calibrés au bruit ambiant : "
                f"silence={SEUIL_SILENCE:.4f}  parole={SEUIL_PAROLE_SUR:.4f}"
            )

    # Reconnaissance musicale : capture depuis le micro en SUSPENDANT proprement le
    # wake word (micro partage). Un bip signale l'ecoute AVANT la capture, pour ne
    # pas polluer l'empreinte envoyee a Shazam.
    try:
        from tools import musique as _musique

        def _capturer_musique(secondes):
            # Signale la capture : la boucle de surveillance (thread principal) lache
            # flux AVANT qu'on le stoppe, sinon son flux.read planterait et couperait
            # la reponse a mi-chemin.
            _CAPTURE_MUSIQUE.set()
            time.sleep(0.15)
            actif = flux.active
            try:
                flux.stop()
            except Exception:
                pass
            try:
                bip(880, 0.12)
                audio = sd.rec(
                    int(secondes * CAPTURE_TAUX),
                    samplerate=CAPTURE_TAUX,
                    channels=1,
                    dtype="float32",
                    device=MICRO,
                )
                sd.wait()
                return _vers_16k(audio.reshape(-1)), TAUX
            finally:
                try:
                    if actif:
                        flux.start()
                except Exception:
                    pass
                _CAPTURE_MUSIQUE.clear()

        _musique.definir_capture_micro(_capturer_musique)
    except Exception:
        LOG.exception("musique: hook capture micro")

    # Overlay de reponses (fenetre flottante Windows) : demarre masque, cout nul au
    # repos ; pilotable par config overlay.* et a la voix ("affiche les reponses").
    if _overlay is not None and config.reglage("overlay.actif", True):
        try:
            _overlay.demarrer(
                {
                    "actif": True,
                    "muet": config.reglage("overlay.muet_visuel", False),
                    "ecran": config.reglage("overlay.ecran", 1),
                    "coin": config.reglage("overlay.coin", "bas-droite"),
                    "opacite": config.reglage("overlay.opacite", 0.92),
                    "largeur": config.reglage("overlay.largeur", 420),
                    "duree_min": config.reglage("overlay.duree_min", 4.0),
                    "duree_max": config.reglage("overlay.duree_max", 14.0),
                    "marge": config.reglage("overlay.marge", 24),
                    "exclure_obs": config.reglage("overlay.exclure_obs", True),
                }
            )
        except Exception:
            LOG.exception("overlay: demarrage")

    print(f'\nPret. Dites "{mot_activation()}". Ctrl+C pour quitter.\n')
    print(
        f'Vous pouvez le couper en redisant "{mot_activation()}" pendant qu\'il parle.\n'
    )

    # Scene "au demarrage" : jouee UNE fois par jour, au premier lancement (musique
    # + lumieres selon l'heure + accueil vocal / brief Hermes). En tache de fond.
    try:
        from tools import scenes

        scenes.jouer_au_demarrage_async()
    except Exception:
        LOG.exception("scene au demarrage")

    # Vosk a une légère latence : conserver le début d'une commande enchaînée.
    tampon = deque(maxlen=25)
    enchainer = False
    audio_reprise = None

    try:
        while True:
            suite = enchainer
            if not enchainer:
                bloc = lire_bloc(flux)
                tampon.append(bloc)

                if _MICRO_MUET.is_set():  # wake word coupe (raccourci mute)
                    _hud("etat", "muet")
                    continue

                _hud("etat", "veille")
                _hud("niveau", _niv_hud(bloc))

                scores = reveil.predict((bloc * 32767).astype(np.int16))
                score_reveil = max(scores.values())
                if score_reveil < SEUIL_REVEIL:
                    continue
                reveil.reset()
                from core.arbitrage_micro import reserver_reveil

                priorite = float(config.reglage("assistant.priorite_micro", 1.0) or 1.0)
                if not reserver_reveil("principal", score_reveil * priorite):
                    print("  [micro] Wake ignoré : un micro plus proche a répondu.")
                    continue

            enchainer = False
            _hud("etat", "ecoute")
            if not suite:
                print("  [micro] Oui ?")
                bip()

            audio, question_reprise = (
                audio_reprise
                if audio_reprise is not None
                else (capturer(flux, tampon), None)
            )
            audio_reprise = None
            if audio is None:
                print("  (rien entendu)\n")
                audio_reprise = attendre_apres_reponse(
                    flux, tampon, whisper, reveil, delai_initial=0
                )
                enchainer = audio_reprise is not None
                if not enchainer:
                    _hud("etat", "veille")
                continue

            issue = traiter(
                audio, whisper, historique, flux, reveil, question=question_reprise
            )
            if issue == SENTINEL_VEILLE:
                audio_reprise = attendre_apres_reponse(
                    flux, tampon, whisper, reveil, forcer_confirmation=True
                )
                enchainer = audio_reprise is not None
                if not enchainer:
                    _hud("etat", "veille")
                continue
            if issue is True:
                tampon.extend(_AUDIO_INTERRUPTION)
                _AUDIO_INTERRUPTION.clear()
                enchainer = True
                continue

            print(
                "  [micro] J'écoute la suite, puis je demanderai avant de passer en veille."
            )
            audio_reprise = attendre_apres_reponse(flux, tampon, whisper, reveil)
            enchainer = audio_reprise is not None
            if not enchainer:
                _hud("etat", "veille")

    except (KeyboardInterrupt, ArretAssistant):
        print("\nAu revoir.")
    finally:
        couper_parole()
        flux.stop()
        flux.close()
