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


Dis **« Red fonction »** pour entendre les fonctions actuellement disponibles.
Le catalogue tient compte des outils chargés, du mode et de la configuration.
Les intégrations externes doivent aussi être connectées.

Dis **« Red panneau »**, saisis **`/panneau`** dans une entrée texte de Red,
ou ouvre [le panneau local](http://127.0.0.1:8790/panneau) pendant que Red tourne.
Il permet de régler le micro, la sortie audio, la voix, la personnalité, le délai
de conversation, la détection et les modèles. L'onglet **Fonctionnalités** donne
des exemples et les intégrations à configurer.

Dans **Réglages → Voix française hors ligne**, choisis **Red — style français**
puis **Écouter** pour une préécoute. Cette voix masculine grave, légèrement
synthétique, correspond au style de Red.
Les voix Siwis et Tom restent disponibles. Le choix vocal s'applique à la
prochaine réponse ; les réglages du micro et de détection demandent un redémarrage.
Tout est enregistré dans `config.yaml`.

La voix Piper de Red utilise [Piper Tom français](https://huggingface.co/rhasspy/piper-voices/tree/main/fr/fr_FR/tom/medium)
avec un léger traitement audio local ; la fiche du modèle et sa licence sont
conservées dans `voix/fr_FR-tom-medium.MODEL_CARD`.


Red accuse maintenant réception dès qu'une demande est transcrite, pendant
que le modèle prépare la réponse. Une seule voix parle à la fois.

Après le délai d'écoute enchaînée, il demande la permission de passer en veille.
Réponds **oui** pour confirmer, **non** pour rester en conversation, ou dis ta
nouvelle demande. Le silence ne vaut pas confirmation : Red continue d'écouter
sans répéter la question. Le raccourci **Ctrl+Alt+M** coupe toujours le micro.

Les réglages **Voix & écoute** du panneau permettent de modifier immédiatement
l'accusé de réception, la confirmation de veille et les délais : 4 secondes
pour commencer, 1,6 seconde de pause pour terminer une phrase, 6 secondes pour
commencer une réponse de confirmation. Une hésitation trop longue coupe toujours
la phrase : augmente le réglage « Pause avant la fin de phrase » si nécessaire.

Un verrou empêche désormais deux instances de Red d'écouter simultanément.
Les journaux indiquent séparément la durée audio transcrite, le temps de
transcription, celui du modèle et celui de la voix, pour diagnostiquer les délais.

Commandes de conversation :

- **« Stop »**, **« Red stop »**, **« arrête de parler »** : coupe la voix pendant
  une réponse, puis permet une nouvelle demande. **Ctrl+Alt+Espace** fait la même
  chose immédiatement au clavier. Ctrl+Alt+M coupe aussi la voix en désactivant
  le micro.
- **« Quelles sont les fonctionnalités actuelles ? »**, **« donne-moi tes
  capacités »** ou **« Red fonction »** : même liste des possibilités réellement
  disponibles, sans génération par le modèle.
- **« Mets-toi en veille »** (aussi reconnu sous « mes toi en veille ») : Red
  demande confirmation. **Oui** termine l'écoute de conversation ; **non** ou
  une nouvelle demande la prolonge. La veille conserve l'activation par « Red ».
- **« Arrête Red »**, **« arrête l'assistant »** ou **« quitte Red »** : ferme
  Red et libère le micro. Pour le relancer, double-clique sur `lancer_red.bat`.
  Cette commande ne met pas Windows hors tension.

En veille, commence par « Red ». Pendant une réponse, « stop » suffit. Le casque
facilite la séparation entre ta voix et celle de l'assistant. La détection des
interruptions utilise Vosk localement ; une ancienne réponse annulée ne peut
plus reprendre la parole ni lancer de nouveaux outils après le début d'un autre tour.


Pour une voix personnalisée à partir d’un WAV, consulte le [guide Chatterbox](docs/chatterbox.md).
Le moteur Chatterbox Multilingual fonctionne localement, avec profils `jarvis` et
`reddington`, et conserve Piper/Windows en secours. Le WAV Reddington est installé ; le profil Chatterbox correspondant est actif.


Red demande maintenant simplement « Est-ce que je peux me mettre en veille ? ».
Les confirmations d'actions gardent la question « Tu confirmes ? » et attendent
ta réponse, sans réciter les choix possibles. Le silence ne confirme toujours
pas la veille. La mémorisation d'une autorisation reste utilisable si tu la demandes.

Le fichier fourni est copié sans transformation dans `voices/reddington_reference.wav`.
`tts.moteur: chatterbox` et `tts.profil: reddington` activent cette référence
au prochain lancement. Piper reste disponible dans le panneau et sert de secours.
Un échantillon de synthèse est disponible dans `logs/red-reddington-sobre-confirmation.wav`.
Les messages et l'interface utilisent le nom Red ; les identifiants techniques
historiques restent compatibles avec les configurations existantes.

Les paramètres Reddington ont été ajustés à cette référence : xaggeration: 0.25,
cfg_weight: 0.5, 	emperature: 0.65. Les deux phrases de validation ont été
correctement retranscrites par Whisper local, avec génération Chatterbox sur CUDA.
