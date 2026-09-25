"""Worker Chatterbox isolé, protocole JSON sur stdin/stdout, diagnostics stderr."""
import base64
from contextlib import redirect_stdout
import gc
import json
import os
from pathlib import Path
import re
import sys
import traceback

# Fixés avant les imports tiers : seul l'installateur a le droit de télécharger.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["DO_NOT_TRACK"] = "1"


def interdire_reseau(event, args):
    """Filet de sécurité : aucune bibliothèque du worker ne doit se connecter."""
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise RuntimeError("Chatterbox est hors ligne : connexion réseau interdite.")


def charger_modele_local(dossier, device):
    from chatterbox import mtl_tts
    from chatterbox.models.tokenizers import MTLTokenizer
    from tokenizers import Tokenizer

    class TokenizerFrancais(MTLTokenizer):
        def __init__(self, vocab_file_path):
            # Compatibilité ciblée 0.1.7 : l'initialisation originale télécharge
            # pkuseg pour le chinois, même pour fr. Garder EXACTEMENT le tokenizer
            # multilingue, sans le convertisseur chinois jamais utilisé ici.
            self.tokenizer = Tokenizer.from_file(str(vocab_file_path))
            self.cangjie_converter = None
            self.check_vocabset_sot_eot()

    original = mtl_tts.MTLTokenizer
    mtl_tts.MTLTokenizer = TokenizerFrancais
    try:
        return mtl_tts.ChatterboxMultilingualTTS.from_local(dossier, device=device)
    finally:
        mtl_tts.MTLTokenizer = original


def morceaux(texte, limite=240):
    """Borne la mémoire nécessaire sans couper une réponse ni perdre de mots."""
    resultat = []
    for phrase in re.split(r"(?<=[.!?])\s+", texte.strip()):
        courant = ""
        for mot in phrase.split():
            if courant and len(courant) + len(mot) + 1 > limite:
                resultat.append(courant)
                courant = ""
            courant = (courant + " " + mot).strip()
        if courant:
            resultat.append(courant)
    return resultat


class Moteur:
    def __init__(self):
        self.modele = None
        self.cle = None
        self.reference = None
        self.device = None
        self.cuda_echec = False

    def charger(self, conf, force_cpu=False):
        import torch
        torch.set_num_threads(conf["threads"])
        device = "cpu"
        if not force_cpu and not self.cuda_echec and conf["device"] != "cpu" and torch.cuda.is_available():
            try:
                # Test réel du pilote, pas seulement de la présence d'une carte.
                torch.zeros(1, device="cuda").add_(1)
                torch.cuda.synchronize()
                device = "cuda"
            except Exception as exc:
                print(f"CUDA inutilisable, utilisation CPU : {exc}", file=sys.stderr)
                self.cuda_echec = True
        cle = (conf["modele"], device)
        if cle != self.cle:
            self.modele = None
            self.reference = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            print(f"Chargement Chatterbox Multilingual sur {device}...", file=sys.stderr, flush=True)
            self.modele = charger_modele_local(conf["modele"], device=device)
            self.cle = cle
        self.device = device

    def _generer(self, conf):
        import numpy as np
        import torch
        reference = Path(conf["reference"])
        cle = (str(reference), reference.stat().st_mtime_ns, reference.stat().st_size, conf["exaggeration"])
        with torch.inference_mode():
            if cle != self.reference:
                self.modele.prepare_conditionals(str(reference), exaggeration=conf["exaggeration"])
                self.reference = cle
            audios = []
            for phrase in morceaux(conf["texte"]):
                wav = self.modele.generate(
                    phrase, language_id="fr", exaggeration=conf["exaggeration"],
                    cfg_weight=conf["cfg_weight"], temperature=conf["temperature"],
                )
                audio = wav.detach().cpu().numpy().reshape(-1)
                if not audio.size or not np.isfinite(audio).all():
                    raise ValueError("Le modèle a renvoyé un audio vide ou invalide.")
                audios.append(audio)
            if not audios:
                raise ValueError("Texte vide.")
            audio = np.concatenate(audios)
            pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        return {"ok": True, "pcm": base64.b64encode(pcm.tobytes()).decode("ascii"),
                "frequence": self.modele.sr, "device": self.device}

    def generer(self, conf):
        try:
            self.charger(conf)
            return self._generer(conf)
        except Exception as exc:
            # Une carte reconnue peut manquer de VRAM ou avoir un pilote trop
            # ancien. Une seule nouvelle tentative, sur CPU, dans ce cas.
            if conf["device"] != "cpu" and (self.device == "cuda" or "cuda" in str(exc).lower()):
                print(f"Échec CUDA, nouvelle tentative CPU : {exc}", file=sys.stderr)
                self.cuda_echec = True
                self.charger(conf, force_cpu=True)
                return self._generer(conf)
            raise


def main():
    sys.addaudithook(interdire_reseau)
    moteur = Moteur()
    sortie = sys.stdout
    for ligne in sys.stdin:
        try:
            # Les bibliothèques affichent parfois leur progression sur stdout.
            with redirect_stdout(sys.stderr):
                resultat = moteur.generer(json.loads(ligne))
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            resultat = {"ok": False, "erreur": str(exc)}
        sortie.write(json.dumps(resultat, ensure_ascii=False) + "\n")
        sortie.flush()


if __name__ == "__main__":
    main()
