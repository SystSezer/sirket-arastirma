"""Saglik ajanslarinda UYUM dili gercekten satis argumani mi — olcum.

Varsayim: 'belge suresi takibi' saglik personeli ajanslarinin gercek acisi.
Eger oyleyse sitelerinde bunu REKLAM ediyor olmalilar. Etmiyorlarsa varsayim
yanlis ve o mail yazilmamali.
"""
import csv, re
from arastirma import Istemci

TERIMLER = {
    "NMC kaydi":        r"\bnmc\b|nursing and midwifery council",
    "DBS":              r"\bdbs\b|disclosure and barring",
    "CQC":              r"\bcqc\b|care quality commission",
    "cerceve/framework": r"\bframework\b|crown commercial|nhs workforce|\bhte\b",
    "uyum (compliance)": r"complian",
    "zorunlu egitim":   r"mandatory training|statutory and mandatory|\bstat[/ ]?mand\b",
    "revalidation":     r"revalidat",
    "calisma izni":     r"right to work|\brtw\b",
    "denetim (audit)":  r"\baudit",
    "yerlestirme oncesi": r"pre[- ]employment|onboarding check",
}

doms = []
for r in csv.DictReader(open("HEDEFLER-TEMIZ.csv", encoding="utf-8-sig")):
    if r["guven"] != "YUKSEK":
        continue
    t = (r["firma"] + " " + r["domain"]).lower()
    if re.search(r"health|care|nurs|medic|locum", t):
        doms.append((r["firma"], r["domain"], int(r["skor"])))

print(f"{len(doms)} saglik ajansi taranacak\n")
i, sonuc = Istemci(), []
YOLLAR = ["", "/compliance", "/about", "/about-us", "/clients", "/employers", "/candidates"]
try:
    for n, (firma, dom, skor) in enumerate(doms, 1):
        metin, sayfa = "", 0
        for y in YOLLAR:
            if sayfa >= 4:
                break
            r = i.getir(f"https://{dom}{y}")
            if r is None or r.status_code != 200:
                continue
            sayfa += 1
            metin += " " + re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>", " ", r.text)).lower()
        bulunan = [k for k, p in TERIMLER.items() if re.search(p, metin)]
        sonuc.append({"firma": firma, "domain": dom, "sayfa": sayfa,
                      "uyum_sayisi": len(bulunan), "terimler": "; ".join(bulunan)})
        print(f"[{n}/{len(doms)}] {dom[:32]:34} {sayfa} sayfa · {len(bulunan):2} terim · {', '.join(bulunan[:5])}")
finally:
    i.kapat()

with open("olcum-saglik.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["firma","domain","sayfa","uyum_sayisi","terimler"])
    w.writeheader(); w.writerows(sonuc)

okunan = [s for s in sonuc if s["sayfa"] > 0]
print(f"\n=== OLCUM ===")
print(f"Sitesi okunabilen: {len(okunan)}/{len(sonuc)}")
if okunan:
    for esik in (1, 3, 5):
        k = sum(1 for s in okunan if s["uyum_sayisi"] >= esik)
        print(f"  {esik}+ uyum terimi: {k}/{len(okunan)}  (%{100*k//len(okunan)})")
    from collections import Counter
    c = Counter(t for s in okunan for t in s["terimler"].split("; ") if t)
    print("\nEn cok gecen terimler:")
    for t, k in c.most_common(10):
        print(f"  {t:22} {k}/{len(okunan)}")
