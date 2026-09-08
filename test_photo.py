"""Test de la logique structurée avec la transcription de référence du devis Feu Vert."""
from app import analyze_text

SAMPLE = """
FEU VERT veille au recyclage de tous les déchets
Client
JENOIS SYLVAIN
Véhicule Dacia Duster 1.5 dCi 110
Immatriculation : DJ639PF
Cylindrée : 461 cm3
Mise en circulation : 25/08/2014
Puissance : 109 ch
"""

result = analyze_text(SAMPLE)["fields"]
assert result["client"]["value"] == "JENOIS SYLVAIN"
assert result["immatriculation"]["value"] == "DJ639PF"
assert result["cylindree"]["value"] == "1461 cm³"
assert result["annee"]["value"] == "2014"
print("Référence Feu Vert V31 : OK")
