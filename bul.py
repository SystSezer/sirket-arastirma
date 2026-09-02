"""CLI — sirket arastirma boru hatti.

Uc mod:
    isim    domainlerden karar verici cikar (sicil once, sonra site, sonra insan)
    kesif   nis + bolge -> hedef firma listesi
    ulke    bir ulkede ismin nereden bulunacagini anlat

Ornekler:
    python bul.py isim --ulke UK --dosya sirketler.txt
    python bul.py isim --ulke NL diqq.com iqstaffing.nl --js
    python bul.py kesif --nis emlak --bbox 52.33,4.83,52.41,4.96
    python bul.py ulke DE
"""
from __future__ import annotations

import argparse
import csv

from arastirma import (NISLER, Firma, Istemci, bosluk_bul, etiket, mx_kontrol,
                       osm_ara, puanla, rapor, sicilden_isim, siteden_isim,
                       zincir_ele, ULKELER)


def komut_isim(a: argparse.Namespace) -> None:
    hedefler = list(a.hedefler)
    if a.dosya:
        with open(a.dosya, encoding="utf-8") as f:
            hedefler += [s.strip() for s in f if s.strip() and not s.startswith("#")]
    if not hedefler:
        raise SystemExit("en az bir sirket/domain ver ya da --dosya kullan")

    u = ULKELER.get(a.ulke.upper())
    print(f"Ulke: {u.ad if u else a.ulke} · "
          f"{'sicil otomatik' if u and u.otomatik else 'sicil elle — site denenecek'}"
          f"{' · JS render acik' if a.js else ''}\n")

    istemci = Istemci(js=a.js)
    satirlar, bulunan = [], 0
    try:
        for i, hedef in enumerate(hedefler, 1):
            domain = hedef.split("//")[-1].split("/")[0].removeprefix("www.")
            sirket = a.ad or domain.rsplit(".", 1)[0].replace("-", " ")
            print(f"[{i}/{len(hedefler)}] {hedef}", end="  ", flush=True)

            mx = mx_kontrol(domain)
            kisiler, not_ = [], ""

            # 1) Resmi sicil — varsa en guvenilir kaynak
            if u and u.otomatik:
                kisiler, not_ = sicilden_isim(istemci, a.ulke, sirket)

            # 2) Sicil yoksa ya da bos donduyse: ekip sayfasi (gerekirse JS ile)
            if not kisiler:
                k2, h2 = siteden_isim(istemci, domain, sirket)
                if k2:
                    kisiler, not_ = k2, "site"
                elif not not_:
                    not_ = h2

            print(f"MX:{mx[:13]:15} {'OK' if kisiler else 'isim yok'}  {not_[:44]}")
            if kisiler:
                bulunan += 1
                for k in kisiler[:4]:
                    print(f"      [{k.guven:6}] {k.isim} — {k.unvan}")
                    satirlar.append([hedef, domain, mx, k.guven, k.isim, k.unvan, k.kaynak])
            else:
                satirlar.append([hedef, domain, mx, "", "", "", not_])
                # 3) Makine yapamadi: kullaniciya ne yapacagini soyle
                if u and not u.otomatik and u.elle_adimlar:
                    print(f"      -> {u.elle_adimlar[0]}")
    finally:
        istemci.kapat()

    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["hedef", "domain", "mx", "guven", "isim", "unvan", "kaynak"])
        w.writerows(satirlar)
    print(f"\n{bulunan}/{len(hedefler)} sirkette isim bulundu · cikti: {a.cikti}")
    if u and not u.otomatik:
        print(f"\nIsim cikmayanlar icin {u.ad}:")
        print(rapor(a.ulke))


def komut_kesif(a: argparse.Namespace) -> None:
    if a.nis not in NISLER:
        raise SystemExit(f"bilinmeyen nis. secenekler: {', '.join(NISLER)}")
    nis = NISLER[a.nis]
    print(f"nis: {nis.ad} ({nis.etiket}) · bolge: {a.bbox}\nOpenStreetMap sorgulaniyor...")
    ogeler = osm_ara(nis.etiket, a.bbox, a.limit)
    if not ogeler:
        raise SystemExit("sonuc yok — Overpass mesgul olabilir, birkac dakika sonra dene")

    atilan = 0
    if not a.zincir:
        ogeler, atilan = zincir_ele(ogeler)
    print(f"{len(ogeler)} bagimsiz isletme"
          + (f" ({atilan} zincir elendi)" if atilan else "") + ", inceleniyor:\n")

    istemci, firmalar = Istemci(js=a.js), []
    try:
        for i, oge in enumerate(ogeler, 1):
            t = oge.get("tags", {})
            f = Firma(ad=t.get("name") or "(isimsiz)",
                      site=(t.get("website") or t.get("contact:website") or ""),
                      telefon=t.get("phone") or t.get("contact:phone") or "",
                      adres=" ".join(x for x in [t.get("addr:street"),
                                                 t.get("addr:housenumber"),
                                                 t.get("addr:city")] if x))
            if f.site and not f.site.startswith("http"):
                f.site = "https://" + f.site
            if f.site:
                f.mx = mx_kontrol(f.site.split("//")[-1].split("/")[0].removeprefix("www."))
            bosluk_bul(istemci, f, nis)
            puanla(f)
            firmalar.append(f)
            print(f"  [{i}/{len(ogeler)}] {f.ad[:34]:36} firsat {f.firsat:3} · "
                  f"ulasim {f.ulasim:3} · {etiket(f):11} {', '.join(f.bosluklar) or '-'}")
    finally:
        istemci.kapat()

    firmalar.sort(key=lambda x: -(x.firsat + x.ulasim))
    with open(a.cikti, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["etiket", "firsat", "ulasim", "ad", "site", "mx", "telefon",
                    "adres", "bosluklar", "teklif", "sorular"])
        for f in firmalar:
            w.writerow([etiket(f), f.firsat, f.ulasim, f.ad, f.site, f.mx, f.telefon,
                        f.adres, "; ".join(f.bosluklar), nis.teklif, "; ".join(f.sorular)])

    sicak = [f for f in firmalar if etiket(f) == "SICAK"]
    print(f"\n{len(firmalar)} firma · {len(sicak)} SICAK · "
          f"{sum(1 for f in firmalar if f.sorular)} tanesi insan gozu istiyor")
    print(f"cikti: {a.cikti}\nSatis argumani: {nis.teklif}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sirket arastirma boru hatti")
    alt = ap.add_subparsers(dest="komut", required=True)

    i = alt.add_parser("isim", help="domainlerden karar verici cikar")
    i.add_argument("hedefler", nargs="*")
    i.add_argument("--ulke", default="UK", help="UK, NL, DE, IE, BE, AT, TR, CN")
    i.add_argument("--ad", help="sicilde aranacak resmi sirket adi (tek hedefte)")
    i.add_argument("--dosya")
    i.add_argument("--js", action="store_true", help="JS ile render (playwright gerekir)")
    i.add_argument("--cikti", default="isimler.csv")
    i.set_defaults(fn=komut_isim)

    k = alt.add_parser("kesif", help="nis + bolge -> firma listesi")
    k.add_argument("--nis", required=True, help=", ".join(NISLER))
    k.add_argument("--bbox", required=True, help="guney,bati,kuzey,dogu")
    k.add_argument("--limit", type=int, default=30)
    k.add_argument("--zincir", action="store_true", help="zincirleri de dahil et")
    k.add_argument("--js", action="store_true")
    k.add_argument("--cikti", default="kesif.csv")
    k.set_defaults(fn=komut_kesif)

    u = alt.add_parser("ulke", help="bir ulkede isim nereden bulunur")
    u.add_argument("kod", nargs="?")
    u.set_defaults(fn=lambda a: print(rapor(a.kod) if a.kod else
                                      "\n\n".join(rapor(x) for x in ULKELER)))

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
