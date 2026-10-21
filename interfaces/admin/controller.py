"""Adaptateur HTTP de l’administration ; métier et catalogues séparés."""

import json
import time
import logging
import threading

LOG = logging.getLogger("assistant.admin")
from core.config import reglage
from interfaces.admin import service
from interfaces.admin.security import local_request


def monter_routes(app):
    """Monte les routes du panneau sur l'app FastAPI unifiee (appelee par core.serveur)."""
    from interfaces.admin.security import AdminBoundary

    app.add_middleware(AdminBoundary)
    from fastapi import Request
    from fastapi.responses import HTMLResponse, JSONResponse

    def garde(request: Request):
        if not local_request(request):
            return JSONResponse(
                {"ok": False, "message": "Panneau accessible en local uniquement."},
                status_code=403,
            )
        # Anti-CSRF : sur les écritures (POST), exiger application/json. Une page
        # web malveillante ne peut pas envoyer ce Content-Type en « requête simple »
        # (il déclenche un préflight CORS qu'on ne satisfait pas) -> pas de CSRF.
        if request.method not in ("GET", "HEAD"):
            ct = (request.headers.get("content-type", "") or "").lower()
            if "application/json" not in ct:
                return JSONResponse(
                    {"ok": False, "message": "Content-Type invalide."}, status_code=415
                )
        return None

    from interfaces.admin.memory_api import monter_routes as monter_memoire

    monter_memoire(app, garde)

    @app.get("/panneau")
    def panneau(request: Request):
        refus = garde(request)
        if refus:
            return refus
        if not service._HTML.exists():
            return HTMLResponse(
                "<h1>Panneau</h1><p>web/panneau.html manquant.</p>", 500
            )
        return HTMLResponse(service._HTML.read_text(encoding="utf-8"))

    # -- lecture --
    @app.get("/api/panneau/modeles")
    def api_modeles(request: Request):
        return garde(request) or service._modeles()

    @app.get("/api/panneau/etat")
    def api_etat(request: Request):
        return garde(request) or service._etat()

    @app.get("/api/panneau/budget")
    def api_budget(request: Request):
        return garde(request) or service._budget()

    @app.get("/api/panneau/hermes-activite")
    def api_hermes_activite(request: Request):
        return garde(request) or service._hermes_activite()

    @app.get("/api/panneau/taches")
    def api_taches(request: Request):
        return garde(request) or service._taches()

    @app.get("/api/panneau/permissions")
    def api_permissions(request: Request):
        return garde(request) or service._permissions()

    @app.get("/api/panneau/pull-status")
    def api_pull_status(request: Request, nom: str = ""):
        return garde(request) or service._PULLS.get(
            nom, {"statut": "inconnu", "pct": 0, "message": ""}
        )

    @app.get("/api/panneau/reglages")
    def api_reglages(request: Request):
        return garde(request) or service._reglages()

    @app.get("/api/panneau/fonctionnalites")
    def api_fonctions(request: Request):
        refus = garde(request)
        if refus:
            return refus
        from core.fonctionnalites import catalogue

        return catalogue()

    @app.post("/api/panneau/voix/apercu")
    async def api_apercu(request: Request):
        refus = garde(request)
        if refus:
            return refus
        from core.voix_locales import PROFILS, installee

        try:
            donnees = await request.json()
            identifiant = donnees.get("id", "") if isinstance(donnees, dict) else ""
            if (
                not isinstance(identifiant, str)
                or identifiant not in PROFILS
                or not installee(identifiant)
            ):
                return JSONResponse(
                    {"ok": False, "message": "Voix locale indisponible."},
                    status_code=400,
                )
            # La préécoute ne modifie ni la voix active ni le microphone de Red.
            from core.tts import PiperProvider
            from starlette.concurrency import run_in_threadpool

            resultat = await run_in_threadpool(
                PiperProvider(profil=identifiant).synthetiser,
                "Bonjour. Je suis votre assistant Red. Je suis à votre écoute.",
            )
            if resultat is None:
                return JSONResponse(
                    {"ok": False, "message": "La synthèse a échoué."}, status_code=503
                )
            import io
            import wave
            from fastapi.responses import Response

            audio, taux = resultat
            tampon = io.BytesIO()
            with wave.open(tampon, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(taux)
                wav.writeframes(audio.astype("<i2").tobytes())
            return Response(tampon.getvalue(), media_type="audio/wav")
        except (ValueError, TypeError):
            return JSONResponse(
                {"ok": False, "message": "Demande invalide."}, status_code=400
            )

    # -- ecriture (sans danger : modeles + reconnexion) --
    async def _corps(request):
        try:
            donnees = await request.json()
            return donnees if isinstance(donnees, dict) else {}
        except Exception:
            return {}

    @app.post("/api/panneau/ollama/pull")
    async def api_pull(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return (
            service._ollama_pull(str(d.get("nom", "")).strip())
            if d.get("nom")
            else JSONResponse({"ok": False, "message": "nom manquant."}, 400)
        )

    @app.post("/api/panneau/ollama/supprimer")
    async def api_suppr(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._ollama_supprimer(str(d.get("nom", "")).strip())

    @app.post("/api/panneau/ollama/tester")
    async def api_test(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._ollama_tester(str(d.get("nom", "")).strip())

    @app.post("/api/panneau/whisper/pull")
    async def api_wpull(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._whisper_installer(str(d.get("nom", "")).strip())

    @app.post("/api/panneau/whisper/supprimer")
    async def api_wsuppr(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._whisper_supprimer(str(d.get("nom", "")).strip())

    @app.post("/api/panneau/modele-actif")
    async def api_actif(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._definir_actif(
            d.get("backend"),
            str(d.get("modele", "")).strip(),
            profil=str(d.get("profil", "hybride")).strip().lower(),
            fournisseur=str(d.get("fournisseur", "")).strip().lower(),
        )

    @app.post("/api/panneau/reglage")
    async def api_reglage(request: Request):
        if r := garde(request):
            return r
        d = await _corps(request)
        return service._definir_reglage(str(d.get("cle", "")).strip(), d.get("valeur"))

    @app.post("/api/panneau/tester-voix")
    def api_tester_voix(request: Request):
        if r := garde(request):
            return r
        try:
            from core import voix

            threading.Thread(
                target=voix.parler,
                args=("Test de la voix Red. La voix selectionnee est active.",),
                daemon=True,
                name="test-voix",
            ).start()
            return {"ok": True, "message": "Test vocal lance."}
        except Exception as e:
            LOG.exception("test voix panneau")
            return {"ok": False, "message": str(e)[:120]}

    @app.post("/api/panneau/reconnecter-mcp")
    def api_reco(request: Request):
        return garde(request) or service._reconnecter_mcp()

    @app.post("/api/panneau/permissions/revoquer")
    async def api_revoquer(request: Request):
        if r := garde(request):
            return r
        from core import registre

        nom = str((await _corps(request)).get("nom", "")).strip()
        ok = registre.revoquer(nom)
        return {
            "ok": ok,
            "message": (
                f"« {nom} » repasse en confirmation a chaque fois."
                if ok
                else "Rien a revoquer pour cet outil."
            ),
        }

    LOG.info("panneau monte : /panneau (local uniquement)")

    from assistant_vocal.runtime import runtime

    if runtime.modules:
        for record in runtime.modules.records.values():
            if record.state == "STARTED":
                for path, endpoint, methods in record.api.admin_routes:
                    app.add_api_route(path, endpoint, methods=list(methods))
