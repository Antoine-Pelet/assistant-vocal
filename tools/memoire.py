"""Mémoire de Red : lecture, propositions et validation obligatoire de chaque écriture."""
from core import memoire
from core.registre import outil
from core.memoire_store import normaliser, ErreurMemoire

MUTATIONS = frozenset(("remember", "forget"))
_CATEGORIES = {"preference": "preferences", "preferences": "preferences",
               "personne": "people", "people": "people", "projet": "projects",
               "projects": "projects", "fait": "facts", "facts": "facts"}


def preparer(nom, args):
    """Seul le contrôleur vocal appelle ceci. Aucun jeton ne vient du modèle."""
    if nom == "remember":
        cat = _CATEGORIES.get(normaliser(args.get("categorie", "fait")))
        if not cat:
            raise ErreurMemoire("Catégorie inconnue.")
        return memoire.magasin().preparer("ajouter", dict(zone="generale", categorie=cat,
            contenu=args.get("contenu"), cle=args.get("cle", "")), origine="voix")
    if nom == "forget":
        return memoire.magasin().preparer("oublier", dict(zone="generale", sujet=args.get("sujet")),
                                          origine="voix")
    raise ErreurMemoire("Action inconnue.")


@outil(nom="remember", confirmation=True,
       description="Propose d'ajouter un souvenir durable, ou de modifier celui qui porte la même clé. "
                   "Chaque changement exige une confirmation de l'utilisateur. "
                   "Les zones protégées se gèrent dans le panneau.",
       parametres={"type": "object", "properties": {
           "categorie": {"type": "string", "enum": ["preference", "personne", "projet", "fait"]},
           "contenu": {"type": "string", "description": "Information exacte à retenir."},
           "cle": {"type": "string", "description": "Même étiquette pour modifier une préférence, une personne ou un projet."}},
           "required": ["categorie", "contenu"]})
def remember(categorie: str, contenu: str, cle: str = "") -> str:
    return "Cette modification nécessite une validation sur le PC de Red, à la voix ou dans le panneau."


@outil(nom="forget", confirmation=True,
       description="Propose d'oublier les souvenirs contenant ce sujet dans la zone générale. "
                   "Red présente exactement les éléments concernés puis demande confirmation.",
       parametres={"type": "object", "properties": {"sujet": {"type": "string"}}, "required": ["sujet"]})
def forget(sujet: str) -> str:
    return "Cette suppression nécessite une validation sur le PC de Red, à la voix ou dans le panneau."


@outil(nom="recall", description="Recherche dans les souvenirs sans condition d'accès. "
       "Les zones protégées sont accessibles uniquement sur le PC, après déverrouillage dans le panneau.",
       parametres={"type": "object", "properties": {"requete": {"type": "string"}}})
def recall(requete: str = "") -> str:
    m = memoire.charger()
    besoin = normaliser(requete).strip()
    trouves = []
    for cat in ("preferences", "people", "projects"):
        for cle, val in m[cat].items():
            if not besoin or besoin in normaliser(f"{cle} {val}"):
                trouves.append(f"{cle} : {val}")
    trouves.extend(f for f in m["facts"] if not besoin or besoin in normaliser(f))
    return "Je retiens : " + " ; ".join(trouves) if trouves else "Je n'ai aucun souvenir accessible à ce sujet."
