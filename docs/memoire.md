# Mémoire durable et accès confidentiels de Red

La mémoire conserve les souvenirs **sans limite de durée**. Les sept jours ne
concernent que l'historique des changements. Le délai de déverrouillage d'une zone
ne supprime jamais ses souvenirs.

## Première utilisation

1. Relancer Red, ouvrir `/panneau`, onglet **Mémoire**.
2. Cliquer **Accéder à l'historique**, choisir un mot de passe, le répéter puis
   valider la proposition. Cette configuration est requise avant tout nouveau
   changement de mémoire : aucun événement nouveau n'est conservé en clair.
3. Déverrouiller l'historique pour le consulter. Les événements suivants pourront
   être enregistrés chiffrés même lorsqu'il sera verrouillé.

Il n'existe **aucune récupération, aucun mot de passe administrateur et aucune
réinitialisation permettant de conserver les données**. Un mot de passe perdu
rend les données qu'il protège irrécupérables par Red. L'historique a son propre
mot de passe ; les zones ont chacune le leur.

## Souvenirs et validation

Chaque ajout, modification ou suppression exige un accord explicite sur le
changement présenté, à la voix ou avec **Confirmer** dans le panneau. Le silence,
un refus ou une réponse ambiguë n'autorise rien. « Toujours autoriser » ne peut
pas désactiver cette règle. Une proposition expire après cinq minutes, est à
usage unique et ne survit pas au redémarrage. Une modification concurrente impose
une nouvelle proposition.

Le champ **Supprimer ce souvenir le** est vide par défaut. Renseigner ce champ
programme sa suppression à l'instant choisi ; la proposition mentionne cette
échéance avant validation. Ce seul cas autorise ensuite une suppression automatique,
même si la zone est verrouillée. Retirer une échéance demande également validation.

La zone **Générale** sert aux souvenirs de conversation : « Retiens que je préfère
le thé », « Oublie ma préférence de boisson ». Les autres zones se consultent
explicitement dans le panneau ou avec « Red, lis la zone Personnel ». Leur contenu
ne rejoint pas les prompts du modèle, ses anciens échanges ou un index de recherche.

## Mot de passe au clavier ou à la voix

Le panneau dispose de champs de mot de passe pour créer, déverrouiller ou modifier
une protection. Le mot de passe actuel est exigé lors d'un changement de mot de
passe ou des conditions d'une zone protégée, même si une session est déjà ouverte.

Commandes vocales locales :

- « Red, ouvre l'historique » : première configuration ou déverrouillage.
- « Red, verrouille l'historique ».
- « Red, crée une zone protégée Personnel ».
- « Red, déverrouille la zone Personnel ».
- « Red, verrouille la zone Personnel ».
- « Red, change le mot de passe de la zone Personnel ».
- « Red, change le mot de passe de l'historique ».
- « Red, lis la zone Personnel » : uniquement si les conditions sont remplies.

Red demande le secret dans une capture dédiée, **séparément de la commande**.
Pour en définir un nouveau, il demande une seconde saisie puis une confirmation
de l'opération, sans prononcer le secret. La transcription utilise Whisper local
sans contexte précédent ; elle ne passe ni par le modèle de conversation, ni par
le HUD, les journaux, une file d'événements ou un fichier audio. Le tampon audio
est remis à zéro après utilisation. Une commande contenant explicitement
« mot de passe » est interceptée avant les transcriptions affichées.

Le mot de passe correspond à la transcription reçue, avec sa casse, ses accents
et sa ponctuation (seuls les blancs en début et fin sont retirés). La reconnaissance
vocale peut se tromper ; le champ de saisie permet d'entrer exactement un secret
complexe. Red ne normalise pas silencieusement un mot de passe.

Une lecture de zone à la voix utilise la voix Windows locale dans un processus
éphémère. Elle ne remplit pas le cache du moteur TTS persistant et ne s'affiche
pas dans la conversation. Un verrouillage coupe la lecture privée en cours.
Les réponses ordinaires conservent le moteur et le profil vocal configurés.

## Zones, dates et sessions

Les dates d'ouverture et de fermeture sont facultatives et limitent **l'accès**,
pas la conservation des informations. Le début est inclus et la fin exclue.
Lorsque des dates et un mot de passe sont définis, toutes les conditions doivent
être satisfaites. Pour préparer des informations à ouvrir plus tard, les ajouter
avant de fixer la date d'ouverture. Les dates utilisent le fuseau du PC à la saisie
et des instants UTC en base.

Une session de déverrouillage dure quinze minutes par défaut, réglable de une à
soixante minutes avec `memoire.session_minutes`. Elle n'est pas persistée.
Verrouillage, expiration et redémarrage retirent les clés actives et invalident
les propositions, recherches et aperçus concernés. Le panneau reçoit les
invalidations du serveur et retire ses données en mémoire ; les réponses réseau
antérieures à une invalidation ne sont pas réaffichées.

Modifier les dates d'une zone hors période reste possible en saisissant son mot
de passe actuel dans **Conditions d'accès** ; cela ne révèle pas ses souvenirs.
Le chiffrement d'une zone protégée ne peut pas être retiré. Il est possible de
changer son mot de passe ou de supprimer la zone après déverrouillage et validation.

## Couche cryptographique

`core/memoire_crypto.py` est indépendant du stockage, de l'API et du modèle.
Il délègue les primitives à **libsodium via PyNaCl** ; aucun algorithme n'est réimplémenté.

- Une DEK `zoneKey` aléatoire de 256 bits est créée pour chaque zone avec le CSPRNG
  libsodium. Deux zones utilisant le même mot de passe ont des DEK et des sels distincts.
- Une KEK `passwordKey` de 256 bits est dérivée avec **Argon2id v1.3** et un sel de
  128 bits. Aucun hash de vérification distinct n'est stocké.
- La DEK est enveloppée par **XChaCha20-Poly1305-IETF** sous la KEK. La KEK est
  effacée immédiatement après cette opération.
- Chaque souvenir a son propre ciphertext et un nonce aléatoire de 192 bits.
  L'AAD canonique JSON lie version, zone, identifiant du souvenir, type d'objet
  et éventuelle échéance de suppression. Déplacer un ciphertext ou altérer son
  contexte fait échouer son authentification.
- `cryptoVersion: 1`, algorithme, paramètres KDF, sel, nonces et ciphertexts sont
  explicitement stockés. Un identifiant de version inconnu est refusé.
- Le remplacement du mot de passe vérifie l'ancien, produit un nouveau sel et
  un nouveau nonce, puis réenveloppe **la même DEK**. Les ciphertexts des souvenirs
  restent identiques. L'écriture et son événement d'audit sont transactionnels.

Les buffers de clés sont alloués côté C, nettoyés avec `sodium_memzero` et protégés
par `sodium_mlock`/`sodium_munlock` lorsque l'OS le permet. Les composants appelants
ne reçoivent aucune KEK ou DEK en clair. Les erreurs d'authentification sont
uniformes : « Mot de passe incorrect ou données invalides. »

Après cinq échecs, une attente commence à une minute et peut augmenter jusqu'à
quinze minutes. Cette limitation est commune au panneau et à la voix, persiste
après redémarrage et s'applique aussi aux changements de mot de passe. Elle ne
remplace pas la résistance d'Argon2id face à une copie volée de la base.

## Calibration Argon2id

Le benchmark de ce PC a retenu **128 Mio, trois passes, p=1**, avec une médiane
d'environ **298 ms** pour trois mesures. Les paramètres sont enregistrés avec
chaque enveloppe ; la configuration ne change pas rétroactivement les anciennes.
Un changement de mot de passe applique les paramètres actuels.

```yaml
memoire:
  session_minutes: 15
  crypto:
    memoryCost: 131072    # Kio
    timeCost: 3
    parallelism: 1
    algorithmVersion: 19
```

Sur un autre PC : `python scripts/bench_memoire_crypto.py --appliquer`.
Le benchmark vise 250–500 ms, utilise un budget de RAM proportionné à la mémoire
disponible et ne manipule aucun secret utilisateur. Le minimum accepté est
64 Mio et deux passes. Les valeurs stockées sont bornées pour éviter une
allocation ou un calcul démesuré sur une base altérée. L'API `crypto_pwhash`
de libsodium fixe p=1 : toute autre valeur de `parallelism` est refusée.

## Historique protégé de sept jours

Seuls les changements de mémoire et de zones validés sont enregistrés : date,
action, zone, identifiants concernés et origine. Les conversations et les valeurs
des souvenirs ne sont pas recopiées dans ce journal.

L'historique emploie sa propre DEK enveloppée par son mot de passe. Cette DEK
protège une clé privée de dépôt ; seule sa clé publique reste disponible lorsque
l'historique est verrouillé. Chaque événement est chiffré avec une clé aléatoire
éphémère, elle-même scellée avec l'API **sealed boxes** de libsodium. Cela permet
d'ajouter des événements chiffrés sans garder une clé de déchiffrement en arrière-plan.
Les identifiants et échéances sont authentifiés. Le changement du mot de passe de
l'historique ne rechiffre pas les anciens événements.

Les événements restent en lecture seule : pas d'outil d'édition, de suppression
anticipée ou de récupération. Des déclencheurs SQLite imposent ces règles dans
la base active. Chaque événement expire individuellement à création + **604 800
secondes**, soit exactement 168 heures. Il est alors exclu des consultations.
La purge physique tourne pendant que Red fonctionne ; après un arrêt de Red ou
du PC, elle reprend au lancement avant consultation. Les souvenirs durables ne
sont pas supprimés avec cet historique.

## Migration, sauvegardes et limites

Les anciennes zones AES-GCM/scrypt restent lisibles : leur premier déverrouillage
correct les convertit atomiquement en DEK indépendante et souvenirs XChaCha20.
Une mauvaise authentification ne modifie pas la zone. Les anciens événements
sont chiffrés lors de la première configuration du mot de passe de l'historique,
sans renouveler leur durée de vie. Avant cette configuration ils sont inaccessibles
par l'API, et les nouveaux changements de mémoire sont suspendus.

La base `data/memoire.sqlite3` est privée et ignorée par Git. Une sauvegarde de
zone protégée ne contient que ses paramètres publics et ciphertexts : aucune
clé en clair ni export déchiffré n'est créé. Les copies externes antérieures à
la protection, notamment les anciens `memory.json`/`memoire.json`, ne sont pas
réécrites automatiquement. Le contenu de Générale est volontairement non chiffré.

Python, le navigateur, Whisper et Windows peuvent créer des copies internes
non effaçables de façon garantie. Les buffers contrôlés par Red sont nettoyés,
les références et caches retirés, mais ce mécanisme ne promet pas l'effacement
de chaque copie physique, fichier d'échange, hibernation ou sauvegarde externe.
De même, supprimer la clé active n'invalide pas une ancienne sauvegarde qui
contient encore son enveloppe et dont quelqu'un connaît le mot de passe.
Un affichage déjà vu ou une copie volontairement extraite ne peut pas être rappelé.

Ces protections ne reposent pas sur le secret du code. Une copie de la base et
du code ne fournit pas les mots de passe ou clés des zones. Elles ne protègent
pas contre un processus qui lit la mémoire du PC pendant un déverrouillage, ni
contre un administrateur qui modifie le programme ou l'horloge système.

Références : [Argon2id de libsodium](https://doc.libsodium.org/password_hashing/default_phf),
[XChaCha20-Poly1305](https://doc.libsodium.org/secret-key_cryptography/aead/chacha20-poly1305/xchacha20-poly1305_construction),
[mémoire sécurisée](https://doc.libsodium.org/memory_management),
[sealed boxes](https://doc.libsodium.org/public-key_cryptography/sealed_boxes),
[recommandations OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
