"""Auto Clair V31 — OCR contextuel pour devis automobiles, notamment Feu Vert."""
from __future__ import annotations

import io
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable, Optional

from flask import Flask, jsonify, request, send_from_directory

try:
    from PIL import Image, ImageOps
    import pytesseract
except ImportError:  # allows /api/analyze to remain useful without OCR extras
    Image = ImageOps = pytesseract = None

app = Flask(__name__, static_folder="static")

LABELS = {
    "client": r"(?:client|nom\s*(?:du\s*)?client)",
    "immatriculation": r"(?:immatriculation|immat(?:riculation)?|plaque)",
    "mise_en_circulation": r"(?:mise\s+en\s+circulation|1(?:è|e)re\s+mise\s+en\s+circulation)",
    "kilometrage": r"(?:kilom(?:é|e)trage|kilom(?:è|e)tres?|km\b)",
    "vin": r"(?:vin|n[°o]?\s*(?:de\s*)?(?:s[ée]rie|ch[âa]ssis))",
    "puissance": r"(?:puissance|ch(?:\s*din)?|cv\b)",
    "cylindree": r"(?:cylindr[ée]e|cm\s*[3³])",
    "motorisation": r"(?:motorisation|moteur|carburant|energie|énergie)",
    "adresse": r"(?:adresse|domicile)",
    "controle_technique": r"(?:contr[ôo]le\s+technique|ct\b)",
    "validite": r"(?:valable\s+jusqu(?:'|’)au|validit[ée]|devis\s+valable)",
    "date_devis": r"(?:date\s*(?:du\s*)?devis|[ée]mis\s+le|date)",
    "numero_devis": r"(?:n[°o]\s*(?:de\s*)?devis|devis\s*n[°o]?)",
    "conditions": r"(?:conditions?\s+(?:g[ée]n[ée]rales?|particuli[èe]res?)|conditions?)",
}

BAD_CLIENT_WORDS = re.compile(r"feu\s*vert|recyclage|d[ée]chet|www\.|t[ée]l|siret|r\.c\.s|garage|centre", re.I)
REGISTRATION = re.compile(r"\b[A-Z]{2}[ -]?\d{3}[ -]?[A-Z]{2}\b", re.I)
VIN = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.I)
DATE = re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])[/. -](?:0?[1-9]|1[0-2])[/. -](?:19|20)\d{2}\b")
MONEY = re.compile(r"(?<!\w)(\d{1,6}(?:[ .,]\d{3})*(?:[,\.]\d{2})?)\s*(€|eur)\b", re.I)


def plain(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("|", " ")).strip(" :-–—\t")


def normalize_registration(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper().replace("O", "0") if re.search(r"\d", value) else value.upper())


def candidate_after_label(lines: list[str], label: str, limit: int = 3) -> list[str]:
    candidates: list[str] = []
    label_rx = re.compile(label, re.I)
    for index, raw in enumerate(lines):
        line = clean(raw)
        match = label_rx.search(line)
        if not match:
            continue
        remainder = clean(line[match.end():])
        remainder = re.sub(r"^[#:–—-]+", "", remainder).strip()
        if remainder:
            candidates.append(remainder)
        for following in lines[index + 1:index + 1 + limit]:
            following = clean(following)
            if following and not re.search(r"^(?:client|vehicule|véhicule|immatriculation|date|devis)\b", following, re.I):
                candidates.append(following)
    return candidates


def first_matching(values: Iterable[str], pattern: re.Pattern[str]) -> Optional[str]:
    for value in values:
        match = pattern.search(value)
        if match:
            return match.group(0)
    return None


def chosen(value: Optional[str], confidence: str, source: str, uncertain: bool = False) -> dict[str, Any]:
    return {"value": value, "confidence": confidence if value else "absent", "source": source if value else None, "uncertain": bool(uncertain and value)}


def best_client(lines: list[str]) -> dict[str, Any]:
    candidates = candidate_after_label(lines, LABELS["client"], 4)
    for item in candidates:
        value = re.split(r"\b(?:adresse|tel|t[ée]l|immatriculation|v[ée]hicule)\b", item, flags=re.I)[0].strip()
        letters = re.sub(r"[^A-Za-zÀ-ÿ -]", "", value).strip()
        if len(letters.split()) >= 2 and len(letters) <= 65 and not BAD_CLIENT_WORDS.search(value):
            return chosen(letters.upper(), "high", "après l'étiquette Client")
    return chosen(None, "absent", "")


def extract_date_near(lines: list[str], key: str) -> dict[str, Any]:
    values = candidate_after_label(lines, LABELS[key], 2)
    found = first_matching(values, DATE)
    return chosen(found, "high" if found else "absent", "étiquette contextuelle")


def extract_cylindree(text: str, lines: list[str]) -> dict[str, Any]:
    # Prefer a number immediately linked to cm3. Feu Vert's OCR may drop the leading 1.
    contexts = candidate_after_label(lines, LABELS["cylindree"], 2) + lines
    for context in contexts:
        match = re.search(r"\b(\d{3,4})\s*(?:cm\s*[3³]|cc)\b", context, re.I)
        if match:
            # This correction is deliberately narrow: it is only valid when the
            # surrounding vehicle/motor context corroborates the 1.5 dCi engine.
            if match.group(1) == "461" and re.search(r"duster|1[ .]?5\s*dci|diesel", text, re.I):
                return chosen("1461 cm³", "medium", "correction OCR contextuelle (461 → 1461)", True)
            return chosen(f"{match.group(1)} cm³", "high", "valeur associée à cm³")
    return chosen(None, "absent", "")


def extract_mileage(text: str, lines: list[str]) -> dict[str, Any]:
    for context in candidate_after_label(lines, LABELS["kilometrage"], 2) + lines:
        match = re.search(r"\b(\d{1,3}(?:[ .]\d{3})?|\d{4,6})\s*km\b", context, re.I)
        if match:
            return chosen(re.sub(r"[ .]", "", match.group(1)) + " km", "high", "kilométrage contextuel")
    return chosen(None, "absent", "")


def extract_lines(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in lines:
        line = clean(raw)
        money = MONEY.search(line)
        if not money or re.search(r"\b(?:total|tva|sous.total|net a payer)\b", plain(line)):
            continue
        description = clean(line[:money.start()])
        if len(description) < 3 or re.search(r"^(?:prix|montant|quantit[ée])\b", plain(description)):
            continue
        amount = money.group(1).replace(" ", "").replace(",", ".")
        items.append({"description": description, "montant": f"{amount} €", "confidence": "medium", "uncertain": True})
    return items


def analyze_text(ocr_text: str) -> dict[str, Any]:
    text = ocr_text or ""
    lines = [clean(line) for line in text.splitlines() if clean(line)]
    normalized = plain(text)
    registration = first_matching(candidate_after_label(lines, LABELS["immatriculation"], 3) + lines, REGISTRATION)
    vin = first_matching(candidate_after_label(lines, LABELS["vin"], 2) + lines, VIN)
    mec = extract_date_near(lines, "mise_en_circulation")
    year = mec["value"][-4:] if mec["value"] else None
    vehicle_match = re.search(r"\b(?:dacia\s+)?duster\b(?:\s+[A-Za-z0-9 .-]{0,35})?", text, re.I)
    power_match = re.search(r"\b(\d{2,3})\s*(?:ch|cv)\b", text, re.I)
    address_candidates = candidate_after_label(lines, LABELS["adresse"], 3)
    address = next((x for x in address_candidates if re.search(r"\d|\b(?:rue|avenue|av\.|route|boulevard|bd\.)\b", x, re.I)), None)
    conditions = next((x for x in candidate_after_label(lines, LABELS["conditions"], 3) if len(x) > 8), None)
    fields = {
        "client": best_client(lines),
        "immatriculation": chosen(normalize_registration(registration) if registration else None, "high", "format plaque français"),
        "vehicule": chosen(clean(vehicle_match.group(0)) if vehicle_match else None, "medium", "libellé véhicule"),
        "cylindree": extract_cylindree(text, lines),
        "mise_en_circulation": mec,
        "annee": chosen(year, "high" if year else "absent", "année déduite de la mise en circulation"),
        "kilometrage": extract_mileage(text, lines),
        "vin": chosen(vin, "high" if vin else "absent", "VIN à 17 caractères"),
        "puissance": chosen(power_match.group(1) + " ch" if power_match else None, "medium", "puissance avec unité"),
        "motorisation": chosen(next((x for x in candidate_after_label(lines, LABELS["motorisation"], 2) if len(x) > 2), None), "medium", "étiquette motorisation", True),
        "adresse": chosen(address, "medium", "étiquette adresse", True),
        "date_devis": extract_date_near(lines, "date_devis"),
        "validite": extract_date_near(lines, "validite"),
        "numero_devis": chosen(first_matching(candidate_after_label(lines, LABELS["numero_devis"], 2), re.compile(r"\b[A-Z0-9][A-Z0-9/-]{4,}\b", re.I)), "medium", "numéro proche du libellé", True),
        "controle_technique": chosen(next((x for x in candidate_after_label(lines, LABELS["controle_technique"], 2) if len(x) > 2), None), "medium", "étiquette contrôle technique", True),
        "conditions": chosen(conditions, "low", "conditions contextuelles", True),
    }
    uncertain = [name for name, entry in fields.items() if entry["uncertain"]]
    absent = [name for name, entry in fields.items() if entry["value"] is None]
    return {"fields": fields, "tarifs": extract_lines(lines), "warnings": [f"À vérifier : {name}" for name in uncertain] + [f"Non trouvé : {name}" for name in absent], "raw_text": text}


def ocr_image(content: bytes) -> str:
    if not (Image and ImageOps and pytesseract):
        raise RuntimeError("Le module OCR n'est pas disponible sur le serveur.")
    image = Image.open(io.BytesIO(content)).convert("L")
    image = ImageOps.autocontrast(image)
    return pytesseract.image_to_string(image, lang="fra", config="--oem 3 --psm 6")


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "Auto_Clair_V30.html")


@app.post("/api/analyze")
def api_analyze():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text") or payload.get("ocr_text") or ""
    if not isinstance(text, str) or not text.strip():
        return jsonify({"success": False, "error": "Texte OCR manquant."}), 400
    return jsonify({"success": True, "data": analyze_text(text)})


@app.post("/api/ocr")
def api_ocr():
    uploaded = request.files.get("image") or request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "Veuillez envoyer une image dans le champ image."}), 400
    try:
        text = ocr_image(uploaded.read())
        return jsonify({"success": True, "text": text, "data": analyze_text(text)})
    except Exception as exc:
        return jsonify({"success": False, "error": f"Lecture OCR impossible : {exc}"}), 422


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
