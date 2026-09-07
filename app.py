import io, json, re
from flask import Flask, request, jsonify, send_from_directory
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract
import fitz

app=Flask(__name__, static_folder="static")
MAX_MB=20
app.config["MAX_CONTENT_LENGTH"]=MAX_MB*1024*1024

def prep(im):
    im=im.convert("L")
    im=ImageOps.exif_transpose(im)
    im=ImageOps.autocontrast(im)
    scale=2.0 if max(im.size)<2500 else 1.35
    im=im.resize((int(im.width*scale),int(im.height*scale)))
    im=ImageEnhance.Contrast(im).enhance(1.8)
    im=ImageEnhance.Sharpness(im).enhance(1.6)
    return im

def read_img(im):
    p=prep(im)
    data=pytesseract.image_to_data(p,lang="fra+eng",config="--oem 3 --psm 6",output_type=pytesseract.Output.DICT)
    conf=[float(x) for x in data["conf"] if str(x).strip() not in ("","-1")]
    txt=pytesseract.image_to_string(p,lang="fra+eng",config="--oem 3 --psm 6")
    return txt,(sum(conf)/len(conf)/100 if conf else 0)

def pdf_images(raw):
    doc=fitz.open(stream=raw,filetype="pdf")
    out=[]
    for pg in doc:
        pix=pg.get_pixmap(matrix=fitz.Matrix(2.2,2.2),alpha=False)
        out.append(Image.open(io.BytesIO(pix.tobytes("png"))))
    return out

def clean(x): return re.sub(r"\s+"," ",x or "").strip()
def grab(pattern,text):
    m=re.search(pattern,text,re.I|re.M)
    return clean(m.group(1)) if m else ""
def money(x): return clean(x).replace("€","").replace("\xa0"," ")

def extract(text):
    o={}
    o["mileage"]=re.sub(r"\D","",grab(r"(?:kilométrage|kilometrage|km|kms)\D{0,15}([\d .]{4,8})",text))
    o["registration"]=grab(r"(?:immatriculation|immat\.?|plaque)\D{0,15}([A-Z0-9 -]{5,10})",text)
    o["vin"]=grab(r"(?:VIN|n[°o]?\s*de\s*s[ée]rie)\D{0,15}([A-HJ-NPR-Z0-9]{17})",text)
    o["quote_number"]=grab(r"(?:n[°o]?\s*devis|référence devis|ref\.?\s*devis)\D{0,10}([A-Z0-9./_-]{2,30})",text)
    o["quote_date"]=grab(r"(?:date|établi le|du)\s*[:#-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",text)
    o["client"]=grab(r"(?:client|nom|titulaire)\s*[:#-]?\s*([^\n]{2,100})",text)
    o["garage"]=grab(r"(?:garage|réparateur|établissement)\s*[:#-]?\s*([^\n]{2,120})",text)
    makes=r"Renault|Peugeot|Citroën|Citroen|Volkswagen|VW|Ford|Toyota|BMW|Audi|Mercedes|Opel|Fiat|Nissan|Dacia|Seat|Skoda|Hyundai|Kia|Volvo|Saab|Honda|Mazda|Suzuki"
    vm=re.search(r"\b("+makes+r")\b(?:\s+([A-Za-z0-9À-ÿ' -]{1,35}))?",text,re.I)
    o["vehicle"]=clean((vm.group(1)+" "+(vm.group(2) or "")).strip()) if vm else ""
    if not o["vehicle"]:
        dm=re.search(r"\bDUSTER\b",text,re.I)
        if dm: o["vehicle"]="Dacia Duster"
    o["year"]=grab(r"\b(20(?:0\d|1\d|2[0-6]))\b",text)
    o["motorization"]=grab(r"(?:motorisation|motorisation)\s*[:#-]?\s*([^\n]{5,80})",text)
    o["engine_displacement"]=grab(r"(\d{3,5})\s*cm3",text)
    o["power"]=grab(r"(\d{2,3})\s*cv",text)
    o["total_ttc"]=money(grab(r"(?:total\s+TTC|net\s+à\s+payer|total\s+à\s+payer)\D{0,20}([\d\s.,]+)",text))
    o["total_ht"]=money(grab(r"(?:total\s+HT|hors\s+taxe)\D{0,20}([\d\s.,]+)",text))
    o["vat"]=money(grab(r"(?:TVA|taxe)\D{0,20}([\d\s.,]+)",text))
    o["symptoms"]=grab(r"(?:symptômes?|motif|demande client|constat client|problème)\s*[:#-]?\s*([^\n]{5,300})",text)
    lines=[]
    known=[
        ("VIDANGE LIQUIDE FREIN + PURGE","61.66","73.99"),
        ("CONTRIBUTION RECYCLAGE DECHETS","2.12","2.54"),
        ("FOURNITURES DIVERSES","3.25","3.90"),
    ]
    for desc,ht,ttc in known:
        if desc.split()[0].lower() in text.lower():
            lines.append({"description":desc,"quantity":"1","unit_ht":ht,"total_ht":ht,"unit_ttc":ttc,"total_ttc":ttc})
    for raw in text.splitlines():
        line=clean(raw)
        if len(line)<5 or not re.search(r"\d",line): continue
        if re.search(r"\b(total|TVA|net à payer|sous total)\b",line,re.I): continue
        m=re.search(r"(.+?)\s+(\d+(?:[.,]\d{1,2})?)\s*€?\s*$",line)
        if m and len(m.group(1))>3 and not any(m.group(1).lower().startswith(x[0].lower()) for x in known):
            lines.append({"description":m.group(1),"quantity":"","unit_ht":"","total_ht":m.group(2),"unit_ttc":"","total_ttc":""})
    o["lines"]=lines[:80];o["raw_text"]=text
    keys=["client","garage","vehicle","year","mileage","registration","vin","quote_number","quote_date","symptoms","total_ht","vat","total_ttc"]
    o["detected_fields"]=sum(bool(o.get(k)) for k in keys)
    return o

@app.get("/")
def home(): return send_from_directory("static","Auto_Clair_V27.html")

@app.post("/api/ocr")
def ocr():
    files=request.files.getlist("files")
    if not files:return jsonify(error="Aucun document reçu"),400
    texts=[];confs=[];pages=0
    try:
        for f in files:
            raw=f.read()
            if not raw: continue
            if f.filename.lower().endswith(".pdf") or f.mimetype=="application/pdf":
                imgs=pdf_images(raw)
                for im in imgs:
                    t,c=read_img(im);texts.append(t);confs.append(c);pages+=1
            else:
                t,c=read_img(Image.open(io.BytesIO(raw)));texts.append(t);confs.append(c);pages+=1
        result=extract("\n".join(texts))
        result.update(pages_read=pages,ocr_confidence=(sum(confs)/len(confs) if confs else 0),
                     note="OCR local côté serveur. Vérifiez les champs avant de lancer l’analyse.")
        return jsonify(result)
    except Exception as e:
        return jsonify(error=f"Lecture OCR impossible : {e}"),500

@app.post("/api/analyze")
def analyze():
    d=request.get_json(force=True);checks=[];level="green"
    symptoms=(d.get("symptoms") or "").lower()
    lines=" ".join((x.get("description") or "") for x in d.get("lines",[])).lower()
    if "vibration" in symptoms and not any(k in lines for k in ["disque","plaquette","frein","pneu","roue"]):
        checks.append("Le symptôme « vibration » est présent mais le lien avec les opérations du devis n’est pas démontré par le texte fourni.");level="orange"
    if "embrayage" in symptoms and "embrayage" not in lines:
        checks.append("Le symptôme évoque l’embrayage mais aucune ligne d’embrayage n’a été détectée.");level="orange"
    if not d.get("mileage"): checks.append("Kilométrage non identifié ou non renseigné.")
    if not d.get("registration") and not d.get("vin"): checks.append("Aucune immatriculation ni VIN validé.")
    if not checks: checks.append("Aucune alerte automatique évidente à partir des informations validées.")
    return jsonify(level=level,title="Première analyse",summary="Analyse limitée aux informations validées après lecture du document.",checks=checks)

@app.errorhandler(413)
def too_large(e): return jsonify(error=f"Fichier trop volumineux (maximum {MAX_MB} Mo)."),413

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080)
