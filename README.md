# Auto Clair V30 — OCR documentaire optimisé

V30 conserve le parcours document-first : photo/scan/PDF → OCR serveur HTTPS → extraction structurée → vérification humaine → analyse.

## Correction principale de V30
- OCR ramené à une seule passe Tesseract par image (au lieu de deux).
- Taille des images limitée avant OCR pour réduire la mémoire.
- PDF rendu à une résolution plus légère.
- Gunicorn limité à 1 worker pour éviter deux OCR simultanés sur une petite instance.
- Erreurs serveur renvoyées en JSON et erreurs réseau mieux signalées par l’interface.
- Limite d’upload abaissée à 12 Mo.

## Déploiement Render
Le service écoute la variable `PORT` fournie par l’hébergeur et peut être déployé avec le Dockerfile.

## Test de référence
Le document de référence est décrit dans `REFERENCE_TEST.md`.
Avant une mise en production commerciale, prévoir authentification, suppression contrôlée des documents, limitation de fréquence, politique RGPD et extraction documentaire plus robuste.
