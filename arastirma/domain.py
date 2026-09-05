"""Firma adindan domain bulma — tahmin et, sonra GERCEKTEN o firma mi diye dogrula.

Neden gerekli: sicil (Companies House, REC uye dizini) firma adini ve adresini
verir, site adresini vermez. Signify'da bunu elle yaptik; 69 firmalik bir kosuda
elle yapmak mumkun degil.

Neden sadece DNS yetmez: `everycloud.com` DNS'te cozuluyor ama sahibi Hornetsecurity
adli bir Alman guvenlik sirketi. `database.com` cozuluyor, sahibi Salesforce.
Bir domainin var olmasi o firmaya ait oldugunu GOSTERMEZ. Ilk surumde bu kontrol
zayifti ve 11 "bulundu" sonucunun 3'u yanlis firmaydi.

Bu yuzden ikili "bulundu/bulunamadi" yerine guven seviyesi doner ve sayfa basligi
her zaman disari verilir — karari insan verir.
"""
from __future__ import annotations

import re
import socket
from dataclasses import dataclass

from .http import Istemci, mx_kontrol

# Ayirt edici olmayan kelimeler: bunlarin sayfada gecmesi hicbir sey kanitlamaz.
# Her ise alim sitesinde "technology", "talent", "recruitment" zaten gecer.
GENEL = {
    "tech", "technology", "digital", "data", "cloud", "cyber", "software",
    "recruitment", "recruiting", "recruiters", "search", "talent", "staffing",
    "resourcing", "consulting", "consultancy", "solutions", "services",
    "partners", "people", "group", "global", "international", "uk", "london",
    "manchester", "contract", "technical", "engineering", "systems",
}
SON_EKLER = {"limited", "ltd", "llp", "plc", "inc", "corp", "company", "the", "and"}

ISE_ALIM_IZI = ("recruit", "talent", "candidat", "vacanc", "hiring", "staffing",
                "headhunt", "placement", "consultan", "job", "career")

# Satilik / park edilmis / bos domainler.
# DIKKAT: cıplak "for sale" KULLANILAMAZ — emlakci sitesinin basliginda zaten
# "Properties for sale in ..." yazar. Bu desen once oyleydi ve butun emlakcilari
# "satilik domain" sanip elerdi. Satilik olan DOMAIN'dir, mulk degil.
PARK_DESENI = re.compile(
    r"(domain|website|site)\s+(name\s+)?(is\s+)?for sale|"
    r"hugedomains|under\s?construction|parked|godaddy|sedo|"
    r"domain (is )?available|buy this domain|coming soon", re.I)

TLD_VARSAYILAN = (".co.uk", ".com", ".io")



# Ulke sinyali: ayni isimde baska ulkede baska sirket olabilir.
# Olculen hata: "Network IT Recruitment" (REC uyesi, Ingiltere) arandi,
# networkit.com dondu — Los Angeles'ta bir IT servis sirketi. Sayfada
# "network it" bitisik gectigi icin YUKSEK guven aldi.
# "Connected IT Recruitment" (Manchester) -> connected-it.co.uk, Bradford'da
# 10 kisilik donanim bayii. Isim ayni, sirket baska.
UK_IZI = re.compile(
    r"\+44|\(0\)\s?1|\b0[12]\d{2,3}[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b|"
    r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}\b|"          # posta kodu: BR1 1DE
    r"companies house|registered in england|vat\s*(no|number)?\s*:?\s*gb", re.I)
ABD_IZI = re.compile(r"\+1[\s\-]?8|1-8\d\d-|\b[A-Z]{2}\s\d{5}(-\d{4})?\b|"
                     r"\b(california|texas|florida|new york|illinois)\b", re.I)


def ulke_izi(metin_ham: str) -> str:
    """Sayfanin hangi ulkeye ait oldugunu kabaca soyler: UK | ABD | ? """
    uk, us = len(UK_IZI.findall(metin_ham)), len(ABD_IZI.findall(metin_ham))
    if uk and uk > us:
        return "UK"
    if us and us > uk:
        return "ABD"
    return "?"


# Sektore OZGU kelimeler. Jenerik olanlar bilerek disarida: her sirketin
# altbilgisinde "careers" ya da "contact" yazar, ayirt etmez. Buradakiler
# yalnizca o isi gercekten yapan sirkette bir arada bulunur.
SEKTORLER: dict[str, tuple[str, ...]] = {
    "isealim": (
        "candidate", "vacanc", "job seeker", "jobseeker", "permanent", "temporary",
        "placement", " cv ", "shortlist", "recruiter", "recruitment agency",
        "apply now", "submit your cv", "register your cv", "browse jobs",
        "search jobs", "hiring manager", "contract role", "day rate",
    ),
    "emlak": (
        "for sale", "to let", "property for sale", "properties for sale",
        "valuation", "market appraisal", "vendor", "asking price", "guide price",
        "offers over", "viewing", "bedroom", "freehold", "leasehold",
        "stamp duty", "conveyanc", "instruction", "landlord", "tenant",
        "lettings", "sold stc", "under offer", "rightmove", "zoopla",
    ),
}
SEKTOR_TERIMLERI = SEKTORLER["isealim"]     # geriye uyumluluk


def sektor_skoru(metin_duz: str, sektor: str | tuple[str, ...] = "isealim") -> int:
    """Sayfada kac farkli sektor terimi geciyor.

    Olculdu (8 site, isealim): ise alim ajansi OLMAYAN uc firma da 0 aldi —
    connected-it.co.uk (donanim bayii), bureautechnicalservices.co.uk (denetim),
    digitalskills.com (danismanlik). Gercek ajanslar 5, 7 ve 11 aldi.
    Apps IT ve Stealth IT 1 aldi: gercek ajanslar ama ana sayfalari cok sade.
    Bu yuzden esik konmaz — yalnizca SIFIR ceza sayilir, gerisi disari verilir.
    """
    terimler = SEKTORLER.get(sektor, ()) if isinstance(sektor, str) else sektor
    return sum(1 for t in terimler if t in metin_duz)

@dataclass
class DomainSonuc:
    firma: str
    domain: str = ""
    mx: str = ""
    guven: str = ""        # YUKSEK | ORTA | (bos)
    baslik: str = ""
    kanit: str = ""
    ulke: str = ""
    denenen: int = 0


def _kelimeler(ad: str) -> list[str]:
    """Firma adini kelimelere ayirir.

    DIKKAT — buyuk/kucuk harf duyarli calisilir. Ayni islemi PowerShell'de
    duyarsiz `-replace` ile yazmistik ve tr-TR makinesinde her buyuk 'I'
    silindi ('INTRINSIC' -> 'ntrns'), cunku Turkce'de 'I'nin kucugu 'i' degil
    'i' noktasizdir ve a-z araliginda degildir. Python'un re modulu kulture
    bagli degildir, yani burada ayni tuzak yok — ama es deger kodu baska bir
    dilde yazarken hatirla.
    """
    temiz = re.sub(r"[^A-Za-z0-9 ]", " ", ad)
    return [k for k in temiz.split() if k and k.lower() not in SON_EKLER]


def adaylar(ad: str, tldler: tuple[str, ...] = TLD_VARSAYILAN) -> list[str]:
    """Firma adindan olasi domainleri, en olasidan en zayifa siralar."""
    kel = _kelimeler(ad)
    if not kel:
        return []
    govdeler: list[str] = []
    govdeler.append("".join(kel).lower())
    if len(kel) >= 2:
        govdeler.append("".join(kel[:2]).lower())
        govdeler.append("-".join(kel[:2]).lower())
    if len(kel) >= 3:
        govdeler.append("".join(kel[:3]).lower())
    govdeler.append("-".join(kel).lower())

    gorulen, cikti = set(), []
    for g in govdeler:
        if not (5 <= len(g) <= 40) or g in gorulen:
            continue
        gorulen.add(g)
        cikti += [f"{g}{t}" for t in tldler]
    return cikti


def _cozuluyor_mu(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, None)
        return True
    except OSError:
        return False


def dogrula(istemci: Istemci, domain: str, firma: str,
            beklenen_ulke: str = "UK",
            sektor: str = "isealim") -> tuple[str, str, str, str]:
    """Sayfayi acar ve bu domainin GERCEKTEN o firmaya ait oldugunu sinar.

    YUKSEK  firmanin ayirt edici iki kelimesi sayfada bitisik gecer
            ("cloud employee", "tech change") — baska firmada rastlanmaz
    ORTA    ayirt edici tek kelime + ise alim izi var; muhtemelen dogru,
            gozle bak
    (bos)   kanit yok, sonuc verilmez

    Doner: (guven, baslik, kanit, ulke)
    """
    y = istemci.getir(f"https://{domain}")
    if y is None or y.status_code != 200:
        return "", "", "", ""

    ham = y.text
    baslik_e = re.search(r"<title[^>]*>(.*?)</title>", ham, re.I | re.S)
    baslik = re.sub(r"\s+", " ", baslik_e.group(1)).strip() if baslik_e else ""
    if PARK_DESENI.search(baslik):
        return "", baslik, "park edilmis / satilik", ""

    duz = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>", " ", ham))
    metin = re.sub(r"[^a-z0-9]+", " ", duz.lower())

    # Isim tutmasi yetmez. Ayni isimde sirket baska ULKEDE ya da baska
    # SEKTORDE olabilir; ikisi de olculdu ve ikisi de gerceklesti.
    ulke = ulke_izi(duz)
    yanlis_ulke = beklenen_ulke and ulke != "?" and ulke != beklenen_ulke
    skor = sektor_skoru(metin, sektor)

    notlar = ""
    if yanlis_ulke:
        notlar += f" — DIKKAT: sayfa {ulke} gorunuyor, {beklenen_ulke} bekleniyordu"
    if skor == 0:
        notlar += f" — DIKKAT: sayfada hic {sektor} dili yok, bu firma o isi yapmiyor olabilir"
    supheli = yanlis_ulke or skor == 0

    kel = [k.lower() for k in _kelimeler(firma)]
    ayirt = [k for k in kel if len(k) >= 3 and k not in GENEL]

    if len(kel) >= 2:
        ifade = " ".join(kel[:2])
        if ifade in metin or ifade in baslik.lower():
            # Isim tutuyor ama supheliyse YUKSEK verilmez: "Network IT"
            # hem Ingiltere'de hem Los Angeles'ta, "Connected IT" hem
            # Manchester'da ajans hem Bradford'da donanim bayii olarak var.
            return ("ORTA" if supheli else "YUKSEK", baslik,
                    f"'{ifade}' sayfada bitisik geciyor · sektor skoru {skor}" + notlar,
                    ulke)

    isim_var = [k for k in ayirt if k in metin]
    is_var = any(i in metin for i in ISE_ALIM_IZI)
    if isim_var and is_var:
        return ("" if supheli else "ORTA", baslik,
                f"ayirt edici '{isim_var[0]}' · sektor skoru {skor}" + notlar, ulke)
    return "", baslik, f"kanit yok · sektor skoru {skor}", ulke


def domain_bul(istemci: Istemci, firma: str,
               tldler: tuple[str, ...] = TLD_VARSAYILAN,
               beklenen_ulke: str = "UK",
               sektor: str = "isealim") -> DomainSonuc:
    """Adaylari sirayla dener, ilk YUKSEK'i alir; yoksa en iyi ORTA'yi doner."""
    s = DomainSonuc(firma=firma)
    en_iyi: DomainSonuc | None = None
    for aday in adaylar(firma, tldler):
        if not _cozuluyor_mu(aday):
            continue
        s.denenen += 1
        guven, baslik, kanit, ulke = dogrula(istemci, aday, firma, beklenen_ulke, sektor)
        if guven == "YUKSEK":
            s.domain, s.guven, s.baslik, s.kanit, s.ulke = \
                aday, guven, baslik, kanit, ulke
            s.mx = mx_kontrol(aday)
            return s
        if guven == "ORTA" and en_iyi is None:
            en_iyi = DomainSonuc(firma=firma, domain=aday, guven=guven,
                                 baslik=baslik, kanit=kanit, ulke=ulke,
                                 denenen=s.denenen)
    if en_iyi:
        en_iyi.denenen = s.denenen
        en_iyi.mx = mx_kontrol(en_iyi.domain)
        return en_iyi
    return s
