# Red — local French voice assistant

The current installation and architecture are documented in [README.md](README.md).
Run `python -m assistant_vocal` from the configured project environment.
`--check` validates configuration and module discovery without opening the microphone.
`--admin-only` starts the optional local administration server without opening a browser.

The local path uses Vosk, faster-whisper, Ollama and Chatterbox Multilingual, with
Piper Tom and Windows speech as fallbacks. Optional integrations have separate
dependency extras. Chatterbox runs in its own Python 3.11 environment.

See [the extension API](docs/modules.md), [voice setup](docs/chatterbox.md) and
[the migration report](docs/refonte-rapport.md). No multi-user system is included
in this refactoring phase. Legacy names survive only for temporary compatibility.

## Executable capabilities and modules

Hermes, screen analysis and PC control now use automatically discovered modules.
The existing admin panel includes a **Modules** tab. Voice commands and tool calls
share the existing N1/N2/N3 policy. See the
[completion report](docs/refonte-capabilities-rapport.md) and
[module guide](docs/modules.md). Restart Red to load the updated code.
