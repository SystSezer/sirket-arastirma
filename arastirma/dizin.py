"""Sektor birligi uye dizinleri — kesif icin dogru kapi.

Olculen gercek: Companies House isim aramasi ile "Londra'da teknoloji ise alim
ajanslari" arandiginda 208 firma cikti; sanal ofis ve alakasiz isimler
elendikten sonra 69 kaldi; sitesi dogrulanabilen yalnizca ~6 idi (%9).

Sebep yapisal: sicil TUM sirketleri icerir — ticaret yapmayan tek kisilik
kabuklari da. Sicil "bu firmanin yoneticisi kim" sorusunda %100'dur,
"hangi firmalar var" sorusunda degildir.

Sektor birligi dizininde oran tersine doner: uyelik ucretli ve denetimlidir,
yani liste zaten filtrelenmis gelir. REC'in 4.426 uyesinin hepsi gercekten
ticaret yapan ajanslardir.

Yani: **kesif icin birlik dizini, dogrulama icin resmi sicil.**
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .http import Istemci


@dataclass
class Dizin:
    kod: str
    ad: str
    ulke: str
    sitemap: str
    desen: str          # uye sayfasi URL'lerini yakalayan regex
    not_: str = ""


DIZINLER: dict[str, Dizin] = {
    "REC": Dizin("REC", "Recruitment & Employment Confederation", "UK",
                 "https://www.rec.uk.com/sitemaps/sitemap.xml",
                 r"member-directory/([^\s<\"]+)",
                 "Ucretli ve denetimli uyelik. Uye sayfasi ad + tam adres verir, "
                 "site adresi VERMEZ — domaini domain.py bulur."),
}

# Uye adresinin sonundaki sehir dilimi: ".../hoop-recruitment-ltd-cardiff"
SEHIR_DESENI = re.compile(r"-([a-z]+)$")

# Nis tahmini firma ADINDAN yapilir, beyan edilen sektorden degil.
# Bu bir YAKLASIKTIR: "care" kelimesi "Careers" icinde de gecer.
NIS_DESENLERI: dict[str, str] = {
    "saglik":      r"health|care|nurs|medic|clinic|dental|locum|nhs",
    "egitim":      r"educat|teach|school|academ|tutor|supply",
    "lojistik":    r"logistic|driv|transport|hgv|warehouse|courier",
    "insaat":      r"construct|build|civil|trades|scaffold|plant",
    "muhendislik": r"engineer|technical|manufactur|automotiv|aerospace",
    "bilisim":     r"(^|-)it(-|$)|tech|digital|software|data|cyber|cloud",
    "finans":      r"financ|account|audit|tax|banking|insur",
    "hukuk":       r"legal|law|solicit|paralegal",
    "konaklama":   r"hospitality|catering|chef|hotel|restaurant|event",
    "ofis":        r"office|admin|secretar|business-support",
}


@dataclass
class Uye:
    dilim: str
    ad: str
    sehir: str
    nisler: list[str]


def _dilimden_ad(dilim: str, sehir: str) -> str:
    govde = dilim[: -(len(sehir) + 1)] if sehir and dilim.endswith("-" + sehir) else dilim
    return govde.replace("-", " ").title()


def uyeleri_getir(istemci: Istemci, dizin_kodu: str = "REC") -> tuple[list[Uye], str]:
    """Birlik sitemap'inden uye listesini cikarir.

    Doner: (uyeler, uyari). Uyari bos degilse liste eksik ya da bostur —
    sessizce bos liste dondurmek en tehlikeli davranistir, cunku kullanici
    bunu 'burada kimse yok' diye okur.
    """
    d = DIZINLER.get(dizin_kodu.upper())
    if not d:
        return [], f"bilinmeyen dizin: {dizin_kodu}"

    y = istemci.getir(d.sitemap)
    if y is None:
        return [], f"{d.ad} sitemap'ine ulasilamadi (robots.txt ya da ag)"
    if y.status_code == 202 or not y.text.strip():
        return [], (f"{d.ad} bot korumasi dondu (HTTP {y.status_code}, bos govde). "
                    f"Zorlamiyoruz. Sayfayi tarayicida ac: {d.sitemap}")
    if y.status_code != 200:
        return [], f"{d.ad} sitemap HTTP {y.status_code}"

    dilimler = re.findall(d.desen, y.text)
    if not dilimler:
        return [], f"{d.ad} sitemap'i alindi ama uye adresi bulunamadi — desen degismis olabilir"

    uyeler = []
    for dilim in dilimler:
        m = SEHIR_DESENI.search(dilim)
        sehir = m.group(1) if m else ""
        nisler = [n for n, p in NIS_DESENLERI.items() if re.search(p, dilim)]
        uyeler.append(Uye(dilim=dilim, ad=_dilimden_ad(dilim, sehir),
                          sehir=sehir, nisler=nisler))
    return uyeler, ""


def sec(uyeler: list[Uye], sehirler: list[str] | None = None,
        nis: str | None = None, haric: list[str] | None = None) -> list[Uye]:
    """Sehir ve nise gore suzer. `haric` ile devleri elersin — zincire ya da
    kurumsal ajansa satis yapilmaz, karari merkez verir."""
    s = uyeler
    if sehirler:
        kume = {x.lower() for x in sehirler}
        s = [u for u in s if u.sehir in kume]
    if nis:
        s = [u for u in s if nis in u.nisler]
    if haric:
        dusuk = [h.lower() for h in haric]
        s = [u for u in s if not any(h in u.dilim for h in dusuk)]
    return s


def nis_dagilimi(uyeler: list[Uye]) -> list[tuple[str, int]]:
    """Hangi niste kac ajans var — yeni pazar secerken bakilacak tablo."""
    say = {n: 0 for n in NIS_DESENLERI}
    for u in uyeler:
        for n in u.nisler:
            say[n] += 1
    return sorted(say.items(), key=lambda x: -x[1])
