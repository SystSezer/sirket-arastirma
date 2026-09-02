"""Ulkeye gore yonlendirme: ismi nereden bulacagini bilen katman.

Her ulkede farkli bir gercek var. Bazi ulkelerde sirket yoneticileri resmi
sicilde acik ve ucretsiz; bazilarinda para istiyor; bazilarinda disaridan
erisim pratik degil.

Bu modul otomatiklestirebildigini yapar, yapamadiginda SUSMAZ: kullaniciya
o ulkede ne yapmasi gerektigini adim adim soyler.

Ayrica her ulke icin soguk e-posta hukuku notu tutar — yanlis ulkeye toplu
mail atmak para cezasi riskidir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .http import Istemci
from .isim import Kisi


@dataclass
class Ulke:
    kod: str
    ad: str
    sicil_adi: str
    sicil_url: str
    otomatik: bool
    soguk_eposta: str          # OPT_OUT | RIZA_GEREKIR | BELIRSIZ
    hukuk_notu: str
    elle_adimlar: list[str] = field(default_factory=list)
    pazar_notu: str = ""


ULKELER: dict[str, Ulke] = {
    "UK": Ulke("UK", "Birlesik Krallik", "Companies House",
               "https://find-and-update.company-information.service.gov.uk",
               True, "OPT_OUT",
               "PECR kurumsal aboneye onceden riza olmadan izin veriyor. "
               "Her mailde cikis yolu bulunmali.",
               pazar_notu="EN IYI PAZAR: isim zinciri uctan uca otomatik, Ingilizce, "
                          "saat farki 2 saat."),
    "IE": Ulke("IE", "Irlanda", "CRO", "https://core.cro.ie", False, "OPT_OUT",
               "B2B'de opt-out esasli, izin veriliyor.",
               ["core.cro.ie uzerinden sirket adiyla ara",
                "Company Details -> Directors sekmesi",
                "Bazi belgeler ucretli; temel yonetici listesi genelde gorunur"],
               "Ingilizce, AB icinde. UK'den sonraki en iyi hedef."),
    "NL": Ulke("NL", "Hollanda", "KVK Handelsregister", "https://www.kvk.nl/zoeken/",
               False, "OPT_OUT", "B2B soguk e-postaya opt-out esasli izin veriliyor.",
               ["Sitenin 'Over ons' / 'Team' sayfasi — ilk bakilacak yer",
                "LinkedIn sirket sayfasi",
                "Ilan sayfalarindaki danisman imzasi",
                "kvk.nl ucretsiz aramada yonetici genelde gorunmez (ucretli uittreksel)",
                "Kucuk ajanslarda info@ zaten kurucuya duser — ilk satirda ismi yaz"],
               "Iyi pazar ama isim isciligi var. Ekip sayfasi olan firmalari sec."),
    "BE": Ulke("BE", "Belcika", "KBO/BCE", "https://kbopub.economie.fgov.be",
               False, "OPT_OUT", "B2B'de opt-out esasli.",
               ["kbopub.economie.fgov.be uzerinden isim veya KBO numarasiyla ara",
                "Fonksiyonlar bolumunde yoneticiler listelenir"],
               "Hollandaca/Fransizca. NL ile birlikte hedeflenebilir."),
    "DE": Ulke("DE", "Almanya", "Handelsregister", "https://www.handelsregister.de",
               False, "RIZA_GEREKIR",
               "DIKKAT: UWG 7 uyarinca izinsiz ticari e-posta B2B'de bile onceden "
               "acik riza ariyor. SOGUK MAIL ATMA — LinkedIn kullan.",
               ["Impressum sayfasi: Alman sitelerinde yasal zorunluluk, "
                "yonetici adi orada yazar — en hizli yol",
                "handelsregister.de daha resmi ama belge indirmek gerekebilir",
                "ULASIM: e-posta degil, LinkedIn baglanti istegi"],
               "En buyuk pazar. Isim bulmak KOLAY (Impressum), ulasmak zor."),
    "AT": Ulke("AT", "Avusturya", "Firmenbuch", "https://www.firmenbuch.at",
               False, "RIZA_GEREKIR",
               "Almanya ile benzer. Soguk e-posta riskli, LinkedIn tercih et.",
               ["Impressum sayfasina bak — yonetici adi yasal olarak orada",
                "ULASIM: LinkedIn"],
               "Kucuk pazar, Almanya kurallariyla ayni."),
    "TR": Ulke("TR", "Turkiye", "MERSIS / Ticaret Sicil Gazetesi",
               "https://www.ticaretsicil.gov.tr", False, "BELIRSIZ",
               "Ticari elektronik ileti icin IYS kaydi ve izin kurallari var. "
               "Tacire gonderimde istisnalar mevcut — mali musavir/hukukcuya sor.",
               ["Sitenin 'Hakkimizda' / 'Ekibimiz' sayfasi",
                "LinkedIn sirket sayfasi",
                "Ticaret Sicil Gazetesi arsivi (ilan bazli, yavas)"],
               "Doviz avantaji yok, fiyat baskisi yuksek. Oncelikli pazar degil."),
    "CN": Ulke("CN", "Cin", "NECIPS", "https://www.gsxt.gov.cn", False, "BELIRSIZ",
               "PIPL kapsaminda kisisel veri kurallari kati; ticari ileti riza esasli.",
               ["gsxt.gov.cn disaridan erisimde CAPTCHA ve dil engeli cikarir",
                "Pratikte sirketin kendi sitesi ya da yerel bir araci gerekir"],
               "ONERILMEZ (su asamada): dil engeli, tahsilat zor, guven esigi yuksek. "
               "Once UK/IE/NL'de referans olustur."),
}


def rapor(kod: str) -> str:
    u = ULKELER.get(kod.upper())
    if u is None:
        return (f"{kod}: tanimli yol yok.\n"
                "  1. Sirketin kendi ekip/hakkimizda sayfasi\n"
                "  2. LinkedIn sirket sayfasi\n"
                "  3. Ulkenin ticaret sicilini arastir")
    s = [f"{u.ad} ({u.kod}) — {u.sicil_adi}",
         f"  Sicil     : {u.sicil_url}",
         f"  Otomatik  : {'EVET' if u.otomatik else 'HAYIR — elle bakilacak'}"]
    etiket = {"OPT_OUT": "opt-out esasli, izin var",
              "RIZA_GEREKIR": "ONCEDEN RIZA GEREKIR — soguk mail atma",
              "BELIRSIZ": "belirsiz, danis"}
    s.append(f"  Soguk mail: {etiket.get(u.soguk_eposta, u.soguk_eposta)}")
    s.append(f"  Hukuk     : {u.hukuk_notu}")
    if u.pazar_notu:
        s.append(f"  Pazar     : {u.pazar_notu}")
    if not u.otomatik and u.elle_adimlar:
        s.append("  YAPILACAKLAR:")
        s += [f"    {i}. {a}" for i, a in enumerate(u.elle_adimlar, 1)]
    return "\n".join(s)


# ---------- Companies House (UK) ----------

CH = "https://find-and-update.company-information.service.gov.uk"
_EK = {"ltd", "limited", "llp", "plc", "group", "uk", "the", "consulting",
       "consultancy", "international", "corporation", "co", "holdings"}


def _kelimeler(s: str) -> set[str]:
    return {k for k in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()
            if k and k not in _EK}


def _ortusme(aranan: str, bulunan: str) -> float:
    a, b = _kelimeler(aranan), _kelimeler(bulunan)
    return len(a & b) / len(a) if a else 0.0


def ch_sirket_bul(istemci: Istemci, ad: str) -> tuple[str, str, float]:
    """(numara, resmi ad, ortusme orani). Ortusme < 1.0 ise INSAN DOGRULAMALI.

    Companies House arama kutusu ticari adla sicil adi tutmadiginda alakasiz
    sirket dondurebiliyor: 'Launch Global' -> 'Hermitage Coaches Ltd',
    'Zero to One Search' -> 'Zero to One Motorsport Academy'. Bu yuzden
    eslesme orani her zaman disari veriliyor; sessizce karar verilmiyor.
    """
    y = istemci.getir(f"{CH}/search/companies?q={quote_plus(ad)}")
    if y is None or y.status_code != 200:
        return "", "", 0.0
    corba = BeautifulSoup(y.text, "html.parser")
    en_iyi = ("", "", 0.0)
    for a in corba.select("a[href^='/company/']"):
        m = re.match(r"/company/([A-Z0-9]+)$", a.get("href", ""))
        if not m:
            continue
        resmi = " ".join(a.get_text(" ").split())
        blok = a.find_parent("li")
        if blok and "dissolved" in " ".join(blok.get_text(" ").split()).lower():
            continue
        oran = _ortusme(ad, resmi)
        if oran > en_iyi[2]:
            en_iyi = (m.group(1), resmi, oran)
        if oran >= 1.0:
            break
    return en_iyi


def ch_yoneticiler(istemci: Istemci, numara: str) -> list[Kisi]:
    y = istemci.getir(f"{CH}/company/{numara}/officers")
    if y is None or y.status_code != 200:
        return []
    corba = BeautifulSoup(y.text, "html.parser")
    kisiler: list[Kisi] = []
    for b in corba.select("a[href*='/officers/'], h2"):
        ham = " ".join(b.get_text(" ").split())
        if not ham or len(ham) < 5 or "," not in ham:
            continue
        kap = b.find_parent(["div", "li", "article"]) or b.parent
        baglam = " ".join(kap.get_text(" ").split()).lower() if kap else ""
        if "resigned" in baglam:
            continue
        soyad, _, ad = ham.partition(",")
        isim = f"{ad.strip().title()} {soyad.strip().title()}".strip()
        rol = next((r for r in ("director", "secretary", "llp member")
                    if r in baglam), "director")
        if isim and isim not in [k.isim for k in kisiler]:
            kisiler.append(Kisi(isim, rol, "YUKSEK", "Companies House"))
    return kisiler[:6]


def sicilden_isim(istemci: Istemci, kod: str, sirket_adi: str) -> tuple[list[Kisi], str]:
    """Ulkenin sicili otomatiklestirilmisse oradan isim ceker."""
    u = ULKELER.get(kod.upper())
    if u is None or not u.otomatik:
        return [], ""
    numara, resmi, oran = ch_sirket_bul(istemci, sirket_adi)
    if not numara:
        return [], "sicilde eslesme bulunamadi"
    if oran < 1.0:
        return [], f"SUPHELI ESLESME: '{resmi}' ({numara}) — %{oran*100:.0f} ortusme, DOGRULA"
    kisiler = ch_yoneticiler(istemci, numara)
    if not kisiler:
        return [], f"{resmi} ({numara}) bulundu ama yonetici listesi okunamadi"
    return kisiler, f"{resmi} · {numara}"
