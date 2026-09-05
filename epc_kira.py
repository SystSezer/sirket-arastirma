"""Kiralama tarafi: sormaya gerek olmayan iki sinyal.

1) MEES — F ve G notlu bir mulk YASAL OLARAK kiraya verilemez. Notu F/G olan
   kiralik mulk sahibi ya iyilestirme yapacak ya muafiyet alacak ya bos
   tutacak. Bu bir tahmin degil, mevzuat.

2) SURE — EPC 10 yil gecerli. 10 yil once kaydedilmis mulkun belgesi bu yil
   doluyor; yeniden kiralamak icin yenisi gerekiyor.

Ikisi de "kim satmak istiyor" tahmini degil, "kimin yasal sorunu var" olgusu.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import httpx

ADRES = "https://api.get-energy-performance-data.communities.gov.uk/api/domestic/search"


def jeton() -> str:
    return [s.strip() for s in open("epc-anahtar.txt", encoding="utf-8-sig") if s.strip()][-1]


def say(council: str, bas: date, bit: date, notlar: list[str] | None = None) -> int:
    """Sayfalayarak toplam kayit sayisini bulur."""
    h = {"Authorization": f"Bearer {jeton()}", "Accept": "application/json"}
    toplam, sayfa = 0, 1
    while sayfa <= 12:
        p = {"council[]": council, "date_start": bas.isoformat(),
             "date_end": bit.isoformat(), "current_page": sayfa, "page_size": 5000}
        if notlar:
            p["efficiency_rating[]"] = notlar
        y = httpx.get(ADRES, params=p, headers=h, timeout=120)
        if y.status_code != 200:
            print(f"   HTTP {y.status_code}: {y.text[:150]}")
            break
        satirlar = y.json().get("data") or []
        toplam += len(satirlar)
        if len(satirlar) < 5000:
            break
        sayfa += 1
    return toplam


def main() -> None:
    councils = sys.argv[1:] or ["Manchester"]
    bugun = date.today() - timedelta(days=2)

    for c in councils:
        print(f"\n===== {c} =====")

        # 1) MEES: F ve G notlu mulkler (son 12 ay icinde belgelenmis)
        y1 = bugun - timedelta(days=365)
        fg = say(c, y1, bugun, ["F", "G"])
        tum = say(c, y1, bugun)
        print(f"Son 12 ay toplam EPC        : {tum:6}")
        print(f"  bunun F/G notlu olani     : {fg:6}  "
              f"(%{100*fg/max(tum,1):.1f}) — kiraya verilmesi YASAK")

        # 2) SURE: 10 yil once kaydedilenler, bu yil doluyor
        eski_bas = date(bugun.year - 10, 1, 1)
        eski_bit = date(bugun.year - 10, 12, 31)
        eski = say(c, eski_bas, eski_bit)
        print(f"{eski_bas.year} kayitlari (bu yil doluyor): {eski:6}  "
              f"→ haftada ~{eski/52:.0f} belge suresi doluyor")


if __name__ == "__main__":
    main()
