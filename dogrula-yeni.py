"""97 adayi YENI kodla (ulke + sektor sinavi) yeniden dogrular."""
import csv
from arastirma import Istemci
from arastirma.domain import dogrula
from arastirma.http import mx_kontrol

rows = list(csv.DictReader(open("HEDEFLER-YENI.csv", encoding="utf-8-sig")))
i, out = Istemci(), []
try:
    for n, r in enumerate(rows, 1):
        g, b, k, u = dogrula(i, r["domain"], r["firma"])
        skor = 0
        if "sektor skoru" in k:
            skor = int(k.split("sektor skoru ")[1].split()[0].rstrip("—").strip() or 0)
        mx = mx_kontrol(r["domain"]) if g else ""
        out.append({"guven": g or "RED", "skor": skor, "firma": r["firma"],
                    "domain": r["domain"], "mx": mx, "baslik": b,
                    "sube": r["sube_sayisi"], "kanit": k})
        print(f"[{n}/{len(rows)}] {r['domain'][:34]:36} {g or 'RED':7} skor {skor:2}  {b[:40]}")
finally:
    i.kapat()

out.sort(key=lambda x: (x["guven"] != "YUKSEK", -x["skor"]))
with open("HEDEFLER-TEMIZ.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["guven","skor","firma","domain","mx","baslik","sube","kanit"])
    w.writeheader(); w.writerows(out)

y = [x for x in out if x["guven"] == "YUKSEK"]
print(f"\nYUKSEK: {len(y)}/{len(out)}")
print(f"  skor 5+: {sum(1 for x in y if x['skor']>=5)}  (belirgin ise alim ajansi)")
print(f"  skor 1-4: {sum(1 for x in y if 1<=x['skor']<5)}")
print(f"  skor 0:  {sum(1 for x in y if x['skor']==0)}")
print("cikti: HEDEFLER-TEMIZ.csv")
