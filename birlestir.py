"""Uc CSV'yi tek hedef listesine birlestirir: domain + adres + isim."""
import csv, sys
from collections import defaultdict

def oku(yol):
    try:
        with open(yol, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []

dom = {r["domain"]: r for r in oku("domainler-bilisim.csv") if r.get("domain")}
adr = {r["domain_site"]: r for r in oku("adresler-bilisim.csv")}
isim = defaultdict(list)
for r in oku("isimler-bilisim.csv"):
    if r.get("isim"):
        isim[r["domain"]].append((r["guven"], r["isim"], r["unvan"], r["kaynak"]))

satirlar = []
for d, r in dom.items():
    a = adr.get(d, {})
    kisiler = isim.get(d, [])
    en_iyi = ""
    for g in ("YUKSEK", "ORTA", "DUSUK"):
        v = [k for k in kisiler if k[0] == g]
        if v:
            en_iyi = f"{v[0][1]} ({v[0][2]}) [{g}]"
            break
    mail_dom = a.get("mail_domaini", "")
    uyari = a.get("uyarilar", "")
    ornek = a.get("ornekler", "")
    # Gonderilebilirlik: kisisel adres > desen + isim > info@ + isim > yok
    if "MX kaydi YOK" in uyari:
        durum = "GONDERME (MX yok)"
    elif ornek:
        durum = "HAZIR (kisisel adres var)"
    elif a.get("adres_sayisi", "0") != "0" and en_iyi:
        durum = "HAZIR (info@ + isim)"
    elif a.get("adres_sayisi", "0") != "0":
        durum = "ADRES VAR, ISIM YOK"
    elif en_iyi:
        durum = "ISIM VAR, ADRES YOK (form)"
    else:
        durum = "ELLE BAK"
    satirlar.append([durum, r["firma"], d, mail_dom or d, a.get("mx", ""),
                     en_iyi, a.get("desen", ""), ornek, r.get("baslik", ""), uyari])

oncelik = {"HAZIR (kisisel adres var)": 0, "HAZIR (info@ + isim)": 1,
           "ADRES VAR, ISIM YOK": 2, "ISIM VAR, ADRES YOK (form)": 3,
           "ELLE BAK": 4, "GONDERME (MX yok)": 5}
satirlar.sort(key=lambda x: oncelik.get(x[0], 9))

with open("HEDEFLER.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["durum", "firma", "site", "mail_domaini", "mx", "kisi", "desen",
                "ornek_adresler", "site_basligi", "uyarilar"])
    w.writerows(satirlar)

for s in satirlar:
    print(f"{s[0]:28} {s[1][:32]:34} {s[5][:38]:40} {s[7][:34]}")
print(f"\n{len(satirlar)} firma -> HEDEFLER.csv")
for k, v in sorted({s[0]: sum(1 for x in satirlar if x[0] == s[0]) for s in satirlar}.items(),
                   key=lambda x: oncelik.get(x[0], 9)):
    print(f"  {k:28} {v}")
