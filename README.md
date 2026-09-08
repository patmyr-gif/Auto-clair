# Auto Clair V31

V31 conserve l'interface Auto Clair V30 et les points d'entrée `POST /api/ocr` et `POST /api/analyze`.

La lecture est conçue pour les devis Feu Vert : elle privilégie les valeurs situées près de leurs libellés, ne remplit pas les informations absentes et marque `uncertain: true` les interprétations qui demandent vérification.

## Déploiement Render

Envoyer le contenu de ce dossier à la racine du dépôt GitHub. Render utilise le `Dockerfile` automatiquement.

## Test rapide

```powershell
python -m py_compile app.py
python test_photo.py
```
