"""Ham domain sonuclarini ayiklar: franchise tekrarlari, yanlis firma, saglayici/ajans ayrimi."""
import csv, re
from collections import defaultdict

GENEL = {"education","healthcare","health","care","medical","medics","recruitment",
         "staffing","services","solutions","group","ltd","limited","teaching",
         "teachers","nursing","nurse","driver","driving","locums","uk","london"}

def kelimeler(ad):
    return [k.lower() for k in re.sub(r"[^A-Za-z0-9 ]"," ",ad).split()]

def skor(kanit):
    m = re.search(r"sektor skoru (\d+)", kanit or "")
    return int(m.group(1)) if m else -1

rows = [r for r in csv.DictReader(open("domainler-yeni.csv",encoding="utf-8-sig"))
        if r["guven"] == "YUKSEK"]

# 1) Franchise / sube tekrari: ayni domain birden fazla firma adi
dom = defaultdict(list)
for r in rows: dom[r["domain"]].append(r["firma"])
franchise = {d for d,v in dom.items() if len(v) > 1}

benzersiz, elenen = {}, []
for r in rows:
    d = r["domain"]
    if d in benzersiz: continue
    # 2) Baslik firmanin ayirt edici kelimesini iceriyor mu
    ayirt = [k for k in kelimeler(r["firma"]) if len(k) >= 4 and k not in GENEL]
    bas = (r["baslik"] or "").lower()
    baslik_tutuyor = (not ayirt) or any(a in bas for a in ayirt)
    r["_franchise"] = d in franchise
    r["_sube_sayisi"] = len(dom[d])
    r["_skor"] = skor(r["kanit"])
    r["_baslik_tutuyor"] = baslik_tutuyor
    if not baslik_tutuyor or not bas:
        elenen.append(r); continue
    benzersiz[d] = r

print(f"YUKSEK ham: {len(rows)}")
print(f"Benzersiz domain: {len(dom)}  (franchise/sube: {len(franchise)} domain, "
      f"{sum(len(v) for d,v in dom.items() if len(v)>1)} kayit)")
print(f"Baslik tutmayan (yanlis firma suphesi): {len(elenen)}")
print(f"KALAN: {len(benzersiz)}\n")

print("--- ELENDI: baslik firma adiyla tutmuyor ---")
for r in elenen:
    print(f"  {r['firma'][:34]:36} {r['domain']:34} -> {r['baslik'][:44]}")

kalan = sorted(benzersiz.values(), key=lambda x: -x["_skor"])
print(f"\n--- KALAN, sektor skoruna gore (yuksek = belirgin ise alim ajansi) ---")
for r in kalan:
    fr = f" [{r['_sube_sayisi']} sube]" if r["_franchise"] else ""
    print(f"  skor {r['_skor']:2}  {r['firma'][:32]:34} {r['domain']:34}{fr}")

with open("HEDEFLER-YENI.csv","w",newline="",encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["sektor_skoru","firma","domain","mx","baslik","sube_sayisi"])
    for r in kalan:
        w.writerow([r["_skor"], r["firma"], r["domain"], r["mx"], r["baslik"],
                    r["_sube_sayisi"]])
print("\ncikti: HEDEFLER-YENI.csv")
