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

# Satilik / park edilmis / bos domainler
PARK_DESENI = re.compile(
    r"for sale|hugedomains|under\s?construction|parked|godaddy|sedo|"
    r"domain (is )?available|buy this domain|coming soon", re.I)

TLD_VARSAYILAN = (".co.uk", ".com", ".io")


@dataclass
class DomainSonuc:
    firma: str
    domain: str = ""
    mx: str = ""
    guven: str = ""        # YUKSEK | ORTA | (bos)
    baslik: str = ""
    kanit: str = ""
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


def dogrula(istemci: Istemci, domain: str, firma: str) -> tuple[str, str, str]:
    """Sayfayi acar ve bu domainin GERCEKTEN o firmaya ait oldugunu sinar.

    YUKSEK  firmanin ayirt edici iki kelimesi sayfada bitisik gecer
            ("cloud employee", "tech change") — baska firmada rastlanmaz
    ORTA    ayirt edici tek kelime + ise alim izi var; muhtemelen dogru,
            gozle bak
    (bos)   kanit yok, sonuc verilmez

    Doner: (guven, baslik, kanit)
    """
    y = istemci.getir(f"https://{domain}")
    if y is None or y.status_code != 200:
        return "", "", ""

    ham = y.text
    baslik_e = re.search(r"<title[^>]*>(.*?)</title>", ham, re.I | re.S)
    baslik = re.sub(r"\s+", " ", baslik_e.group(1)).strip() if baslik_e else ""
    if PARK_DESENI.search(baslik):
        return "", baslik, "park edilmis / satilik"

    metin = re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<script.*?</script>", " ", ham))
    metin = re.sub(r"[^a-z0-9]+", " ", metin.lower())

    kel = [k.lower() for k in _kelimeler(firma)]
    ayirt = [k for k in kel if len(k) >= 3 and k not in GENEL]

    if len(kel) >= 2:
        ifade = " ".join(kel[:2])
        if ifade in metin or ifade in baslik.lower():
            return "YUKSEK", baslik, f"'{ifade}' sayfada bitisik geciyor"

    isim_var = [k for k in ayirt if k in metin]
    is_var = any(i in metin for i in ISE_ALIM_IZI)
    if isim_var and is_var:
        return "ORTA", baslik, f"ayirt edici '{isim_var[0]}' + ise alim izi"
    return "", baslik, "kanit yok"


def domain_bul(istemci: Istemci, firma: str,
               tldler: tuple[str, ...] = TLD_VARSAYILAN) -> DomainSonuc:
    """Adaylari sirayla dener, ilk YUKSEK'i alir; yoksa en iyi ORTA'yi doner."""
    s = DomainSonuc(firma=firma)
    en_iyi: DomainSonuc | None = None
    for aday in adaylar(firma, tldler):
        if not _cozuluyor_mu(aday):
            continue
        s.denenen += 1
        guven, baslik, kanit = dogrula(istemci, aday, firma)
        if guven == "YUKSEK":
            s.domain, s.guven, s.baslik, s.kanit = aday, guven, baslik, kanit
            s.mx = mx_kontrol(aday)
            return s
        if guven == "ORTA" and en_iyi is None:
            en_iyi = DomainSonuc(firma=firma, domain=aday, guven=guven,
                                 baslik=baslik, kanit=kanit, denenen=s.denenen)
    if en_iyi:
        en_iyi.denenen = s.denenen
        en_iyi.mx = mx_kontrol(en_iyi.domain)
        return en_iyi
    return s
