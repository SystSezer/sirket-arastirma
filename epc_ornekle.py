"""Rastgele orneklem: kayitlarin kaci SATIS amacli EPC?

Arama ucu transaction_type vermiyor, sertifika ucu veriyor. 5000 sertifikayi
tek tek cekmek gereksiz — rastgele 250 orneklem %95 guvenle +-6 puan verir.
Karar icin fazlasiyla yeterli.
"""
from __future__ import annotations

import csv
import random
import sys
import time
from collections import Counter

import httpx

K = "https://api.get-energy-performance-data.communities.gov.uk/api/certificate"
KOD = {1: "Marketed sale", 2: "Non-marketed sale", 3: "Mandatory (construction)",
       4: "Mandatory (to let)", 5: "None of the above", 6: "New dwelling",
       7: "Not recorded", 8: "Rental", 9: "Green Deal assessment",
       10: "Following Green Deal", 11: "FiT", 12: "RHI", 13: "ECO",
       14: "Stock condition", 15: "Re-mortgaging", 16: "Grant", 17: "Non-grant"}


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    tok = [s.strip() for s in open("epc-anahtar.txt", encoding="utf-8-sig") if s.strip()][-1]
    h = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    hepsi = list(csv.DictReader(open("epc-ornek.csv", encoding="utf-8-sig")))
    random.seed(42)                       # tekrar edilebilir olsun
    ornek = random.sample(hepsi, min(n, len(hepsi)))
    print(f"{len(hepsi)} kayittan {len(ornek)} rastgele orneklem\n")

    sayac, tenure, hata = Counter(), Counter(), 0
    with httpx.Client(headers=h, timeout=45) as c:
        for i, r in enumerate(ornek, 1):
            try:
                y = c.get(K, params={"certificate_number": r["certificateNumber"]})
                if y.status_code != 200:
                    hata += 1
                else:
                    d = y.json().get("data", {})
                    sayac[int(d.get("transaction_type") or 0)] += 1
                    tenure[str(d.get("tenure") or "?")] += 1
            except Exception:
                hata += 1
            if i % 25 == 0:
                print(f"  {i}/{len(ornek)}...")
            time.sleep(0.35)

    gecerli = sum(sayac.values())
    print(f"\n=== {gecerli} sertifika okundu ({hata} hata) ===\n")
    for kod, adet in sayac.most_common():
        print(f"  {KOD.get(kod, kod):28} {adet:4}  %{100*adet/gecerli:5.1f}")

    satis = sayac[1] + sayac[2]
    kira = sayac[4] + sayac[8]
    print(f"\nSATIS  (1+2): {satis:4}  %{100*satis/gecerli:.1f}")
    print(f"KIRA   (4+8): {kira:4}  %{100*kira/gecerli:.1f}")
    print(f"YENI INSAAT (6): {sayac[6]:3}  %{100*sayac[6]/gecerli:.1f}")

    haftalik = len(hepsi) / (90 / 7)
    print(f"\nManchester haftalik toplam EPC: ~{haftalik:.0f}")
    print(f"Bunun SATIS amacli olani:       ~{haftalik*satis/gecerli:.0f} / hafta")
    print(f"Sadece 'Marketed sale' (1):     ~{haftalik*sayac[1]/gecerli:.0f} / hafta")


if __name__ == "__main__":
    main()
