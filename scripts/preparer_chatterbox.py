"""Téléchargement explicite, une fois, des poids officiels Multilingual 0.1.7."""
import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
REVISION = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
FICHIERS = ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt",
            "grapheme_mtl_merged_expanded_v1.json", "Cangjie5_TC.json"]


def main():
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HOME"] = str(RACINE / "models/chatterbox-cache")
    # Ce script est la seule étape en ligne ; le worker utilise from_local.
    os.environ.pop("HF_HUB_OFFLINE", None)
    import truststore
    truststore.inject_into_ssl()
    from huggingface_hub import snapshot_download
    dossier = RACINE / "models/chatterbox"
    snapshot_download("ResembleAI/chatterbox", revision=REVISION,
                      allow_patterns=FICHIERS, local_dir=str(dossier), max_workers=2)
    absents = [f for f in FICHIERS if not (dossier / f).is_file()]
    if absents:
        raise RuntimeError(f"Téléchargement incomplet : {absents}")
    (dossier / "revision.txt").write_text(REVISION + "\n", encoding="utf-8")
    print(f"Modèle Multilingual prêt : {dossier}")


if __name__ == "__main__":
    main()
