import sys, os, io, pymupdf, pytesseract
from PIL import Image
folder, cache = sys.argv[1], sys.argv[2]
cap = int(sys.argv[3]) if len(sys.argv)>3 else 0   # 0 = all pages
os.makedirs(cache, exist_ok=True)
for f in sorted(os.listdir(folder)):
    if not f.lower().endswith('.pdf'): continue
    out = os.path.join(cache, f+'.txt')
    if os.path.exists(out): continue
    doc = pymupdf.open(os.path.join(folder,f)); parts=[]
    n = len(doc) if not cap else min(cap, len(doc))
    for i in range(n):
        page=doc[i]
        t = page.get_text()
        if not t.strip():
            pix = page.get_pixmap(dpi=140)
            t = pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))))
        parts.append(t)
    open(out,'w').write("\n".join(parts))
    print("cached", f, "(", n, "pages )", flush=True)
print("DONE", flush=True)
