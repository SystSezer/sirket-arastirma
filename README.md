# Şirket Araştırma

Soğuk erişim öncesi hedef listesi hazırlayan boru hattı. Bir bölge ve niş verirsin,
firmaları bulur; bir domain verirsin, karar vericiyi çıkarır; yapamadığı yerde
susmaz — o ülkede ne yapman gerektiğini söyler.

```bash
python bul.py isim  --ulke UK --dosya sirketler.txt
python bul.py kesif --nis emlak --bbox 52.33,4.83,52.41,4.96
python bul.py ulke  DE
```

---

## Neden böyle kurulu

İlk sürüm şirket sitelerindeki ekip sayfalarını okuyup isim çıkarıyordu. Rastgele
seçilmiş **21 şirkette 2 isim** buldu — %10. Kod temizdi, sonuç kullanılamazdı.

Sorun kodda değildi: çoğu şirket ekibini sitesinde yayınlamıyor, yayınlayanların bir
kısmı JavaScript ile kuruyor, kalanı da anlamsız işaretleme kullanıyor.

Çözüm daha akıllı bir kazıyıcı yazmak değil, **daha iyi bir kaynağa gitmekti.**
Birleşik Krallık'ta her limited şirketin yöneticileri Companies House'ta açık ve
ücretsiz. Aynı 21 şirketin İngiltere'dekilerinde isabet **%10'dan %100'e** çıktı —
tek satır kazıma yapmadan.

Araç bunun üzerine kurulu: **önce resmî sicil, sonra site, sonra insan.**

```
1. Ülkenin sicili otomatikleştirilebiliyor mu?   → Companies House  (%100)
2. Hayır → ekip sayfası, statik HTML              (~%10-30)
3. Boş  → aynı sayfayı JS ile render edip tekrar dene
4. Hâlâ boş → o ülkede ne yapılacağını yaz, insana devret
```

Dördüncü adım özellikle önemli. Bir araştırma aracının en tehlikeli davranışı,
bulamadığında sessiz kalmaktır — kullanıcı boş satırı "burada kimse yok" diye okur.

---

## Ölçülen isabet

| Yol | Örneklem | İsabet |
|---|---|---|
| Companies House (UK) | İsmi birebir eşleşen şirketler | **%100** |
| Ekip sayfası, statik | 21 rastgele şirket | **~%10** |
| Ekip sayfası + JS | JS ile kurulan siteler | İçeriği açar, ama site ismi yayınlamıyorsa yine boş |

Son satır gerçek bir örnekten: Londra'daki bir ajansın sitesi JavaScript ile
kuruluyordu ve statik istek boş dönüyordu. Render edince 62 KB içerik geldi —
ama sitede zaten hiç isim yoktu. Yöneticiyi yalnızca sicil verdi.

---

## Sicil eşleşmesi: sessizce karar vermez

Companies House arama kutusu, ticari ad ile sicil adı tutmadığında alakasız şirket
döndürebiliyor. Gerçek örnekler:

| Aranan | Dönen | |
|---|---|---|
| Launch Global | Hermitage Coaches Ltd | otobüs firması |
| Zero to One Search | Zero to One Motorsport Academy | motor sporları |
| King's Choice | A&A Choice Ltd | alakasız |

Araç bu yüzden **örtüşme oranını her zaman dışarı verir.** Tam eşleşme yoksa isim
döndürmez, `ŞÜPHELİ EŞLEŞME` yazıp doğrulamanı ister. Yanlış kişiye "sen işe alım
ajansı sahibisin" diye yazmaktansa boş dönmek iyidir.

---

## Keşif: iki ayrı skor

Niş ve bölge verince OpenStreetMap üzerinden bağımsız işletmeleri bulur. Zincirleri
`brand` etiketiyle eler — zincire satış yapılamaz, kararı merkez verir.

Skorlama **fırsat** ve **ulaşım** olarak ayrı tutulur. İlk sürümde tek skor vardı ve
yapısal olarak bozuktu: sitesi olmayan işletme en büyük fırsattır ama tam da bu
yüzden MX'i, ekip sayfası ve ismi yoktur — yani ulaşılabilirlik puanı toplayamaz ve
tavana çarpar. Hiçbir koşuda "sıcak" firma çıkmamasının sebebi buydu.

| Etiket | Anlamı |
|---|---|
| `SICAK` | İhtiyacı var **ve** ulaşabiliyoruz |
| `IHTIYAC VAR` | Eksiği çok ama e-postası yok — telefon veya kapı gerekir |
| `ULASILIR` | Ulaşılır ama belirgin eksiği yok — başka açıyla gidilir |

**Bilinen sınır:** OSM'de `website` etiketi olmaması "sitesi yok" demek değil,
"OSM kaydetmemiş" demektir. Ölçülen bir örnekte 13 ajansın 8'inin sitesi vardı ama
OSM 5'ini boş gösteriyordu. Bu yüzden boşluklar **sinyal** olarak işaretlenir,
gerçek olarak değil, ve şüpheliler `sorular` sütununa yazılır.

---

## Ülke katmanı

Her ülke için üç şey tutulur: ismin nereden bulunacağı, otomatikleştirilebilir mi,
ve **soğuk e-posta hukuku.** Sonuncusu araştırma aracının işi gibi görünmeyebilir
ama yanlış ülkeye toplu mail atmak para cezası riskidir.

| Ülke | Sicil | Otomatik | Soğuk e-posta |
|---|---|---|---|
| Birleşik Krallık | Companies House | ✅ | Opt-out esaslı, izinli |
| İrlanda | CRO | ✖ | Opt-out esaslı |
| Hollanda | KVK | ✖ | Opt-out esaslı |
| Belçika | KBO/BCE | ✖ | Opt-out esaslı |
| **Almanya** | Handelsregister | ✖ | **Önceden rıza gerekir — mail atma** |
| Avusturya | Firmenbuch | ✖ | Önceden rıza gerekir |
| Türkiye | MERSIS | ✖ | İYS kuralları, danış |
| Çin | NECIPS | ✖ | Belirsiz |

Almanya ilginç bir durum: isim bulmak **en kolay** ülke, çünkü Impressum sayfası
yasal zorunluluk ve yönetici adı orada yazmak zorunda. Ama e-posta kanalı kapalı.
Araç bunu bilir ve LinkedIn'e yönlendirir.

*Hukuk notları bilgi amaçlıdır, hukuki tavsiye değildir.*

---

## Ne yapmaz — bilerek

- **Giriş gerektiren hiçbir siteye dokunmaz.** LinkedIn dahil.
- **robots.txt'i okur ve uyar.** Yasaklı adresi çekmez.
- **403 dönen siteyi zorlamaz.** Engelleyen site engellemiştir.
- CAPTCHA çözmez, kimlik gizlemez, otomatik form göndermez.
- İstekler arasında 1,5 saniye bekler; User-Agent'ta iletişim adresi vardır.

**JS render hakkında:** herkese açık bir sayfayı tarayıcıyla açmak ile giriş yapıp
kimlik gizlemek aynı şey değil. Burada yalnızca birincisi yapılır ve robots.txt
render yolunda da geçerlidir.

Bunlar eksik özellik değil, tasarım kararı. Kaçınmaya ihtiyaç duymayan bir hat,
üçüncü ayda hâlâ çalışan hattır.

---

## Kurulum

```bash
pip install -r requirements.txt

# JS render istersen (isteğe bağlı, ~150 MB):
playwright install chromium
```

Playwright kurulu değilse araç çalışmaya devam eder, yalnızca `--js` yedeği devre
dışı kalır. MX doğrulaması için sistemde `nslookup` bulunmalıdır.

## Çıktı

`isim` → `hedef, domain, mx, guven, isim, unvan, kaynak`
`kesif` → `etiket, firsat, ulasim, ad, site, mx, telefon, adres, bosluklar, teklif, sorular`

Güven seviyeleri: `YUKSEK` (resmî sicil ya da anlamsal işaretleme) ·
`ORTA` (başlık deseni) · `DUSUK` (sezgisel — gözle doğrula).
