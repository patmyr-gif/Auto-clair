from PIL import Image, ImageOps, ImageEnhance
import pytesseract, re, json

PHOTO="/mnt/data/86867.jpg"
im=Image.open(PHOTO).convert("L")
im=ImageOps.autocontrast(im)
im=im.resize((int(im.width*2),int(im.height*2)))
im=ImageEnhance.Contrast(im).enhance(1.8)
text=pytesseract.image_to_string(im,lang="fra+eng",config="--oem 3 --psm 6")

expected = {
 "quote_number":"145303",
 "client":"JENOIS SYLVAIN",
 "registration":"DJ639PF",
 "vehicle":"DUSTER",
 "mileage":"154939",
 "total_ht":"67.03",
 "total_ttc":"80.43"
}
print("OCR produit", len(text), "caractères")
for k,v in expected.items():
    print(k, "OK" if v.lower() in text.lower().replace(" ","") or v.lower() in text.lower() else "A VERIFIER", "=>", v)
print("\nExtrait OCR:\n", text[:5000])
