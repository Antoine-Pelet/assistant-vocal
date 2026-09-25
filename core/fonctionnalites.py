"""Fonctions annoncées d'après les outils chargés et la configuration actuelle."""
from pathlib import Path

from core import config, registre

RACINE = Path(__file__).resolve().parent.parent


def demande_fonctions(phrase):
    from core.commandes_vocales import demande_fonctionnalites
    return demande_fonctionnalites(phrase)


def catalogue():
    noms = {o.nom for o in registre.tous()}
    mode = config.reglage("mode", "local")
    try:
        from core.llm import llm
        dialogue = llm().disponible()
    except Exception:
        dialogue = False
    entries = []

    def ajouter(identifiant, nom, description, exemples, outils=(), configure=True,
                raison="Intégration à configurer.", besoin_dialogue=False):
        charge = all(n in noms for n in outils)
        if not charge:
            statut, detail = "indisponible", "Les outils nécessaires ne sont pas chargés."
        elif not configure:
            statut, detail = "a_configurer", raison
        elif besoin_dialogue and not dialogue:
            statut, detail = "indisponible", "Le moteur de réponses doit être disponible pour interpréter la demande."
        else:
            statut, detail = "disponible", description
        entries.append({"id": identifiant, "nom": nom, "description": description,
                        "statut": statut, "detail": detail, "exemples": exemples})

    ajouter("aide", "Mes fonctions et mes réglages", "Liste actuelle des fonctions et accès au panneau.",
            ["Quelles sont les fonctionnalités actuelles ?", "Red panneau"])
    ajouter("conversation", "Contrôle de la conversation", "Interrompre la voix, confirmer la veille ou fermer Red.",
            ["Stop", "Mets-toi en veille", "Arrête Red"])
    ajouter("dialogue", "Questions et réponses", "Répondre en français et poursuivre la conversation.",
            ["Explique-moi ce qu'est une API"], configure=dialogue,
            raison="Modèle local indisponible ou clé du fournisseur cloud absente.")
    ajouter("applications", "Applications et sites", "Ouvrir une application configurée ou un site web.",
            ["Ouvre YouTube", "Ouvre le bloc-notes"], ["ouvrir_application", "browser_open"])
    ajouter("audio", "Volume et lecture multimédia", "Régler le volume, mettre en pause ou reprendre la lecture.",
            ["Baisse le volume", "Mets en pause"], ["regler_volume", "controler_media"], besoin_dialogue=True)
    ajouter("notes", "Notes et idées", "Enregistrer des notes et retrouver celles du jour.",
            ["Note que je dois préparer ma présentation", "Lis mes notes du jour"],
            ["noter", "notes_du_jour"], besoin_dialogue=True)
    ajouter("temps", "Heure, date et minuteurs", "Donner l'heure ou démarrer un minuteur avec un rappel vocal.",
            ["Quelle heure est-il ?", "Lance un minuteur de cinq minutes"],
            ["heure_et_date", "lancer_minuteur"], besoin_dialogue=True)
    ajouter("memoire", "Mémoire personnelle", "Souvenirs persistants, validation de chaque changement, zones protégées et historique de sept jours dans le panneau.",
            ["Souviens-toi que je préfère les réponses courtes"], ["remember", "recall", "forget"], besoin_dialogue=True)
    ajouter("stats", "État du PC", "Consulter l'utilisation du processeur, de la mémoire et du disque.",
            ["Quel est l'état du PC ?"], ["get_system_stats"], besoin_dialogue=True)

    hue = str(config.reglage("hue.pont", "") or "")
    ajouter("hue", "Lumières Philips Hue", "Piloter les lumières d'un pont Hue configuré.",
            ["Allume la lumière du salon"], ["allumer_lumiere"],
            configure=bool(hue and "xxx" not in hue.lower() and config.reglage("hue.cle", "")),
            raison="Adresse et clé du pont Hue à renseigner.", besoin_dialogue=True)
    ajouter("gestes", "Commandes par gestes", "Contrôler les actions configurées à l'aide de la webcam.",
            ["Active les gestes"], ["controler_gestes"],
            configure=(RACINE / "gestes/.venv-tracker").is_dir(),
            raison="Le module de gestes et sa calibration doivent être installés.")
    ajouter("agenda", "Agenda Google", "Consulter ou créer des événements dans l'agenda connecté.",
            ["Quels sont mes rendez-vous ?"], ["get_events"],
            configure=mode != "local" and (RACINE / config.reglage("agenda.token", "google_token.json")).is_file(),
            raison="Compte Google connecté et mode cloud nécessaires.", besoin_dialogue=True)
    ajouter("mail", "Courrier électronique", "Lire des messages et préparer des mails ; l'envoi demande confirmation.",
            ["Lis mes derniers mails"], ["lire_mails"],
            configure=mode != "local" and bool(config.reglage("mail.mot_de_passe_app", "")),
            raison="Messagerie et mode cloud à configurer.", besoin_dialogue=True)
    ajouter("web", "Recherche sur le Web", "Chercher des informations récentes sur Internet.",
            ["Cherche les actualités du jour"], ["chercher_web"], configure=mode != "local",
            raison="Le routage de ce projet réserve la recherche Web au mode cloud.", besoin_dialogue=True)
    ajouter("vision", "Lecture de l'écran", "Décrire une capture de l'écran avec un modèle compatible vision.",
            ["Explique cette erreur à l'écran"], ["capture_screen"], configure=mode != "local" and dialogue,
            raison="Fournisseur cloud avec vision à configurer.")
    ajouter("obs", "Streaming et enregistrement OBS", "Contrôler OBS quand son serveur WebSocket est connecté.",
            ["Lance un enregistrement"], ["start_record"], configure=bool(config.reglage("obs.mot_de_passe", "")),
            raison="OBS et ses identifiants WebSocket à configurer.", besoin_dialogue=True)
    ajouter("discord", "Résumés Discord", "Consulter les mentions avec un bot connecté.",
            ["Résume mes mentions Discord"], ["get_mentions_summary"],
            configure=mode != "local" and bool(config.reglage("discord.token", "") and config.reglage("discord.user_id", "")),
            raison="Bot Discord et mode cloud à configurer.", besoin_dialogue=True)
    return {"mode": mode, "fonctions": entries,
            "disponibles": sum(e["statut"] == "disponible" for e in entries)}


def resume_vocal():
    etat = catalogue()
    disponibles = [e["nom"].lower() for e in etat["fonctions"] if e["statut"] == "disponible"]
    texte = "Mes fonctions actuellement disponibles sont : " + ", ".join(disponibles) + ". "
    texte += "Dis Red panneau pour voir les détails, les exemples et les fonctions à configurer."
    return texte
