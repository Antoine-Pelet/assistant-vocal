from services.tts.base import ProviderTTS


class WindowsProvider(ProviderTTS):
    """Demande volontairement le repli SAPI gere par audio.local.dire()."""

    nom = "Windows"
