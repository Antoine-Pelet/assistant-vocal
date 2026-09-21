# Red — assistant vocal local

Double-clique sur **lancer_red.bat**. Le moteur local démarre automatiquement.
Attends « Prêt. Dites red », dis **Red**, attends le bip, puis pose ta question
en français. Exemple : « Quelle heure est-il ? ». La détection est confirmée
localement par Whisper pour éviter les confusions avec « arrête » ou « redémarre ».

Après une réponse, tu peux enchaîner pendant 10 secondes sans répéter son nom.
**Ctrl+C** dans la console arrête l'assistant ; **Ctrl+Alt+M** coupe ou réactive
l'écoute. Le moteur Ollama peut rester en arrière-plan entre deux lancements.

La configuration est dans `config.yaml` : activation Vosk, transcription Whisper
base sur CPU, réponses Qwen 3.5 2B sur Ollama, voix française Piper. Aucun compte
ni clé API ne sont nécessaires. Les modèles se téléchargent une fois ; l'audio,
les réponses et la synthèse vocale sont traités sur ce PC. Les commandes visant
un site web utilisent naturellement Internet.

Le nom « red » est court : une conversation contenant ce mot peut déclencher
l'écoute. Prononce-le distinctement. Le modèle doit être testé avec ta voix et
ton micro ; augmente `assistant.stabilite_reveil` si nécessaire.

Pour réinstaller sur un autre PC Windows avec Python 3.13, lance
`installer_red.bat` (plusieurs Go de téléchargements). Cette installation adapte
la configuration au mode local et sauvegarde la configuration précédente dans
`.red-install/config-avant-red.yaml`. Les intégrations facultatives (Hue, mails,
Discord, etc.) nécessitent leurs propres paramètres ; les appels téléphoniques
et certaines intégrations avancées ont des dépendances supplémentaires dans
`requirements.txt`.

Le lanceur utilise un Python standard isolé dans `.venv-red`, pour éviter les
restrictions de la version Microsoft Store. Le casque OpenFit 2 doit être connecté
si son nom est sélectionné dans `audio.micro` ; change ce réglage pour un autre micro.

Diagnostic : `.venv-red\Scripts\python.exe scripts\doctor.py`.
Journal : `logs/`. L'ancien `lancer_jarvis.bat` lance aussi Red.

Modèles utilisés : [Vosk français](https://alphacephei.com/vosk/models),
[Whisper](https://huggingface.co/Systran/faster-whisper-base),
[Piper Siwis](https://huggingface.co/rhasspy/piper-voices),
[Qwen 3.5](https://ollama.com/library/qwen3.5).
