"""DEPRECATED : compatibilité des anciens imports et scripts, sans runtime propre."""
if __name__ == '__main__':
    from assistant_vocal.__main__ import main
    main()
else:
    import sys
    from audio import local as app
    sys.modules[__name__] = app
