"""Point d'entrée stable : python -m assistant_vocal."""


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Red — assistant vocal local, sans interface graphique."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifier configuration, imports et extensions sans ouvrir le micro.",
    )
    parser.add_argument(
        "--admin-only",
        action="store_true",
        help="Démarrer uniquement le panneau local, sans ouvrir de navigateur.",
    )
    parser.add_argument(
        "--admin-password",
        action="store_true",
        help="Définir le mot de passe unique du panneau sur ce PC.",
    )
    args = parser.parse_args(argv)
    if args.admin_password:
        from getpass import getpass
        from interfaces.admin.security import set_password

        password = getpass("Nouveau mot de passe administrateur : ")
        if password != getpass("Confirmer : "):
            raise SystemExit("Les mots de passe ne correspondent pas.")
        set_password(password)
        print("Protection du panneau activée.")
        return
    if args.check:
        import json
        from assistant_vocal.runtime import Runtime

        runtime = Runtime()
        try:
            runtime.start()
            health = runtime.health()
            print(json.dumps(health, ensure_ascii=False))
            if not health["ok"]:
                raise SystemExit(1)
        finally:
            runtime.stop()
        return
    if args.admin_only:
        import time
        from core import serveur
        from assistant_vocal.runtime import runtime

        runtime.start()
        serveur.demarrer()
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            runtime.stop()
        return
    from assistant_vocal.app import main as run

    return run()


if __name__ == "__main__":
    main()
