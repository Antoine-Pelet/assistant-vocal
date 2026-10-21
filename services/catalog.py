"""Catalogue backend commun à l’administration et au diagnostic."""

CATALOGUE_LLM = [
    {
        "nom": "llama3.2:3b",
        "params": "3B",
        "vram": 3.5,
        "taille_go": 2.0,
        "tool_calling": True,
        "francais": True,
        "licence": "Llama 3.2",
    },
    {
        "nom": "qwen2.5:3b",
        "params": "3B",
        "vram": 3.5,
        "taille_go": 1.9,
        "tool_calling": True,
        "francais": True,
        "licence": "Qwen (Apache-2.0)",
    },
    {
        "nom": "qwen2.5:7b",
        "params": "7B",
        "vram": 6.0,
        "taille_go": 4.7,
        "tool_calling": True,
        "francais": True,
        "licence": "Qwen (Apache-2.0)",
    },
    {
        "nom": "mistral:7b",
        "params": "7B",
        "vram": 6.0,
        "taille_go": 4.1,
        "tool_calling": True,
        "francais": True,
        "licence": "Apache-2.0",
    },
    {
        "nom": "llama3.1:8b",
        "params": "8B",
        "vram": 6.5,
        "taille_go": 4.9,
        "tool_calling": True,
        "francais": True,
        "licence": "Llama 3.1",
    },
    {
        "nom": "qwen2.5:14b",
        "params": "14B",
        "vram": 10.0,
        "taille_go": 9.0,
        "tool_calling": True,
        "francais": True,
        "licence": "Qwen (Apache-2.0)",
    },
]

CATALOGUE_OPENAI = [
    {
        "nom": "gpt-5.6-luna",
        "role": "Rapide / economique",
        "prix_entree": 0.20,
        "prix_sortie": 1.20,
        "tool_calling": True,
        "vision": True,
        "francais": True,
    },
    {
        "nom": "gpt-5.6-terra",
        "role": "Equilibre (hybride conseille)",
        "prix_entree": 2.00,
        "prix_sortie": 12.00,
        "tool_calling": True,
        "vision": True,
        "francais": True,
    },
    {
        "nom": "gpt-5.6-sol",
        "role": "Qualite professionnelle",
        "prix_entree": 4.00,
        "prix_sortie": 20.00,
        "tool_calling": True,
        "vision": True,
        "francais": True,
    },
    {
        "nom": "gpt-6-astra",
        "role": "Flagship (qualite maximale)",
        "prix_entree": 10.00,
        "prix_sortie": 50.00,
        "tool_calling": True,
        "vision": True,
        "francais": True,
    },
]

CATALOGUE_WHISPER = [
    {
        "nom": "tiny",
        "vram": 1.0,
        "francais_fiable": False,
        "note": "tres rapide, peu precis",
    },
    {"nom": "base", "vram": 1.0, "francais_fiable": False, "note": "rapide, moyen"},
    {"nom": "small", "vram": 2.0, "francais_fiable": True, "note": "bon compromis"},
    {
        "nom": "medium",
        "vram": 5.0,
        "francais_fiable": True,
        "note": "precis (defaut conseille)",
    },
    {
        "nom": "large-v3",
        "vram": 10.0,
        "francais_fiable": True,
        "note": "le plus precis, lent en CPU",
    },
    {
        "nom": "large-v3-turbo",
        "vram": 6.0,
        "francais_fiable": True,
        "note": "precis et plus rapide que large",
    },
]


def voice_profiles():
    from core.config import reglage
    from services.tts.chatterbox import ChatterboxProvider

    active = reglage("tts.profile", "red")
    return [
        {
            "id": ident,
            "name": str(value.get("name", ident)),
            "installed": ChatterboxProvider(ident).disponible(),
            "active": ident == active,
        }
        for ident, value in (reglage("voices", {}) or {}).items()
        if isinstance(value, dict)
    ]


def tts_engines():
    from core.config import reglage
    from services.tts.chatterbox import ChatterboxProvider
    from services.tts.piper import PiperProvider
    import os

    active = reglage("tts.engine", "chatterbox")
    states = [
        ("chatterbox", "Chatterbox", ChatterboxProvider().disponible()),
        ("piper", "Piper", PiperProvider().disponible()),
        ("windows", "Windows", os.name == "nt"),
    ]
    return [
        {
            "id": key,
            "name": label,
            "available": True,
            "installed": installed,
            "active": key == active,
            "compatible": key != "windows" or os.name == "nt",
        }
        for key, label, installed in states
    ]
