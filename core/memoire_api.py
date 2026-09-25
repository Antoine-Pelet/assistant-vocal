"""Routes locales de mémoire, distinctes des outils accessibles au modèle."""
import json
import asyncio
from urllib.parse import urlsplit
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from nacl._sodium import ffi, lib
from pathlib import Path
from core import memoire
from core.memoire_store import ErreurMemoire


def monter_routes(app, garde):
    def refuser(request):
        refus = garde(request)
        if refus:
            return refus
        hote = urlsplit("http://" + request.headers.get("host", "")).hostname
        if hote not in ("127.0.0.1", "localhost", "::1"):
            return JSONResponse({"ok": False, "message": "Adresse locale requise."}, status_code=403)
        origine = request.headers.get("origin")
        if (origine and origine != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"ok": False, "message": "Origine refusée."}, status_code=403)

    def resultat(fn):
        try:
            return JSONResponse({"ok": True, **fn()}, headers={"Cache-Control": "no-store"})
        except ErreurMemoire as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=400,
                                headers={"Cache-Control": "no-store"})

    @app.get("/panneau/memoire.js")
    def javascript(request: Request):
        return refuser(request) or Response(
            (Path(__file__).resolve().parent.parent / "web/memoire.js").read_text(encoding="utf-8"),
            media_type="application/javascript", headers={"Cache-Control": "no-store"})

    @app.get("/api/panneau/memoire")
    def etat(request: Request):
        return refuser(request) or resultat(lambda: memoire.magasin().etat())

    @app.get("/api/panneau/memoire/historique")
    def historique(request: Request):
        return refuser(request) or resultat(lambda: {"historique": memoire.magasin().historique()})

    @app.get("/api/panneau/memoire/evenements")
    async def evenements(request: Request):
        refus=refuser(request)
        if refus:return refus
        async def flux():
            precedent=None
            while not await request.is_disconnected():
                courant=memoire.magasin().generation
                if courant!=precedent:
                    yield "data: " + str(courant) + "\n\n"
                    precedent=courant
                await asyncio.sleep(.25)
        return StreamingResponse(flux(),media_type='text/event-stream',headers={'Cache-Control':'no-store'})

    @app.post("/api/panneau/memoire/{action}")
    async def agir(action: str, request: Request):
        refus = refuser(request)
        if refus:
            return refus
        brut = bytearray()
        async for chunk in request.stream():
            brut.extend(chunk)
            if len(brut) > 32768:
                return JSONResponse({"ok": False, "message": "Demande trop volumineuse."}, status_code=413)
        try:
            data = json.loads(brut)
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            return JSONResponse({"ok": False, "message": "Demande JSON invalide."}, status_code=400)

        def executer():
            store = memoire.magasin()
            if action == "proposer":
                return store.preparer(data.get("action"), data.get("valeurs", {}))
            if action == "confirmer":
                return {"message": store.confirmer(data.get("jeton", ""))}
            if action == "annuler":
                store.annuler(data.get("jeton", ""))
                return {"message": "Changement annulé."}
            if action == "deverrouiller":
                return {"message": store.debloquer(data.get("zone"), data.get("mot_de_passe", ""))}
            if action == "verrouiller":
                store.bloquer(data.get("zone"))
                return {"message": "Zone verrouillée."}
            raise ErreurMemoire("Action inconnue. L'historique est en lecture seule.")
        try:
            return resultat(executer)
        finally:
            data.clear()
            if brut:
                lib.sodium_memzero(ffi.from_buffer(brut),len(brut))
