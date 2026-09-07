# Auto Clair V27 — architecture B (serveur HTTPS)

Cette version corrige le problème vu sur le téléphone : le navigateur n'essaie plus de contacter `localhost`.
Le HTML et l'API sont servis par le même serveur. Une fois déployé en HTTPS, le téléphone utilise directement l'URL du serveur.

## Chaîne

PHOTO/PDF → serveur HTTPS → Tesseract OCR → extraction structurée → écran de vérification → analyse Auto Clair.

## Déploiement

Le dossier est prêt pour un hébergeur qui accepte un Dockerfile (par exemple Render, Railway ou un serveur Docker).

1. Mettre ces fichiers dans un dépôt Git.
2. Créer un service Web depuis ce dépôt.
3. Laisser le Dockerfile construire l'application.
4. Le serveur doit écouter le port fourni par la variable `PORT`.
5. Ouvrir l'URL HTTPS depuis le téléphone.

Aucun changement d'URL n'est nécessaire dans le HTML.

## Sécurité / production

Avant mise en production commerciale :
- authentification et comptes utilisateurs ;
- chiffrement HTTPS (fourni par l'hébergeur) ;
- suppression des documents après traitement si aucune conservation n'est demandée ;
- journalisation minimale ;
- limitation de taille et de fréquence ;
- politique RGPD et information sur le traitement des devis ;
- remplacement progressif des heuristiques OCR par une extraction documentaire plus robuste.

## Ce que V27 garantit

Le programme peut lire une photo ou un PDF via Tesseract et remplir les champs lorsqu'ils sont réellement détectés.
Il ne doit pas inventer un kilométrage, VIN, symptôme, prix ou caractéristique absente.
La validation humaine reste obligatoire avant l'analyse.


## V28 — test sur un vrai devis

La photo fournie dans la conversation a été utilisée comme cas de test OCR.
Le moteur OCR installé dans l'environnement de développement lit effectivement le document ; le point à améliorer est désormais l'extraction structurée et la correction des erreurs OCR sur les champs sensibles (VIN, immatriculation, dates et montants).

Le fichier `test_photo.py` permet de reproduire le test sur la photo de référence.
