"""Bir emlakciya gonderilecek listeyi uretir: onun bolgesinde son N gunde
SATIS icin EPC almis mulkler.

Kullanim:  py epc_liste.py Manchester M20 M21 --gun 14

API kismi posta kodu kabul etmiyor (400), o yuzden belediye cekilip burada
suzuluyor. transaction_type sadece sertifika ucunda geldigi icin adaylar
tek tek dogrulaniyor.
"""
from __future__ import annotations

import csv
import sys
import time
from datetime import date, timedelta

import httpx

ARA = "https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search"
SERT = "https://api.get-energy-performance-data.communities.gov.uk/api/certificate"


def jeton() -> str:
    return [s.strip() for s in open("epc-anahtar.txt", encoding="utf-8-sig") if s.strip()][-1]


def main() -> None:
    argv = sys.argv[1:]
    gun = 14
    if "--gun" in argv:
        i = argv.index("--gun")
        gun = int(argv[i + 1])
        del argv[i:i + 2]          # deger listede kalirsa posta kodu sanilir
    a = [x for x in argv if not x.startswith("--")]
    if len(a) < 2:
        sys.exit("kullanim: py epc_liste.py <belediye> <posta_kodu...> [--gun 14]")
    council, bolgeler = a[0], [x.upper() for x in a[1:]]

    h = {"Authorization": f"Bearer {jeton()}", "Accept": "application/json"}
    bit = date.today() - timedelta(days=2)
    bas = bit - timedelta(days=gun)
    print(f"{council} · {', '.join(bolgeler)} · {bas} → {bit}\n")

    ham, sayfa = [], 1
    while sayfa <= 6:
        y = httpx.get(ARA, params={"council[]": council, "date_start": bas.isoformat(),
                                   "date_end": bit.isoformat(), "current_page": sayfa,
                                   "page_size": 5000}, headers=h, timeout=120)
        if y.status_code != 200:
            sys.exit(f"HTTP {y.status_code}: {y.text[:200]}")
        s = y.json().get("data") or []
        ham += s
        if len(s) < 5000:
            break
        sayfa += 1

    def bolgede(pk: str) -> bool:
        d = (pk or "").split()[0].upper()
        return d in bolgeler

    aday = [r for r in ham if bolgede(r.get("postcode", ""))]
    print(f"{len(ham)} kayit → {len(bolgeler)} bolgede {len(aday)} tanesi\n")
    if not aday:
        sys.exit("bolgede kayit yok — posta kodunu kontrol et")

    satis = []
    with httpx.Client(headers=h, timeout=45) as c:
        for i, r in enumerate(aday, 1):
            try:
                y = c.get(SERT, params={"certificate_number": r["certificateNumber"]})
                d = y.json().get("data", {}) if y.status_code == 200 else {}
                if int(d.get("transaction_type") or 0) == 1:      # Marketed sale
                    satis.append({
                        "adres": " ".join(x for x in [d.get("address_line_1"),
                                                      d.get("address_line_2")] if x),
                        "posta_kodu": d.get("postcode", ""),
                        "kayit_tarihi": d.get("registration_date") or r.get("registrationDate", ""),
                        "denetim_tarihi": d.get("inspection_date", ""),
                        "tip": d.get("dwelling_type", ""),
                        "m2": d.get("total_floor_area", ""),
                        "enerji_notu": r.get("currentEnergyEfficiencyBand", ""),
                    })
            except Exception:
                pass
            if i % 20 == 0:
                print(f"  {i}/{len(aday)} kontrol edildi · {len(satis)} satis")
            time.sleep(0.3)

    # Ayni adrese birden fazla sertifika olabiliyor (yeniden kayit).
    # "Flat 43 Beech House" uc kere gelmisti — listede uc satir olarak gorunmesi
    # gonderilen maili ciddiyetsiz gosterir.
    gorulen, tekil = set(), []
    for s in satis:
        anahtar = (s["adres"].lower(), s["posta_kodu"])
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        tekil.append(s)
    yinelenen = len(satis) - len(tekil)
    satis = tekil
    satis.sort(key=lambda x: x["kayit_tarihi"], reverse=True)
    dosya = f"epc-{'-'.join(bolgeler).lower()}.csv"
    with open(dosya, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(satis[0].keys()) if satis else ["adres"])
        w.writeheader(); w.writerows(satis)

    print(f"\n=== {len(satis)} TEKIL MULK · son {gun} gunde SATIS icin EPC almis ==="
          + (f"  ({yinelenen} yinelenen elendi)" if yinelenen else "") + "\n")
    for s in satis[:25]:
        print(f"  {s['kayit_tarihi']}  {s['adres'][:38]:40} {s['posta_kodu']:9} "
              f"{s['tip'][:22]:24} {s['m2']}m2  {s['enerji_notu']}")
    print(f"\ncikti: {dosya}")


if __name__ == "__main__":
    main()
