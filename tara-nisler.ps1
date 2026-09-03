$sehirler = 'london','manchester','birmingham','bristol','leeds','glasgow','nottingham','sheffield'
foreach($n in 'saglik','egitim','lojistik'){
  & py bul.py dizin --nis $n --sehir $sehirler --limit 200 --cikti "dizin-$n.csv" 2>&1 | Select-Object -Last 2
}
& py -c @"
import csv, glob
devler={'hays','reed','adecco','randstad','manpower','pertemps','brook-street','blue-arrow',
        'nhs','gi-group','impellam','sthree','robert-walters','michael-page','page-group',
        'search-consultancy','service-care','maxim','acacium','id-medical','pulse','teaching-personnel',
        'protocol','prospero','academics','supply-desk','tradewind','engage-education'}
gorulen, adlar = set(), []
for y in glob.glob('dizin-*.csv'):
    if 'bilisim' in y: continue
    for r in csv.DictReader(open(y, encoding='utf-8-sig')):
        if any(d in r['dilim'] for d in devler): continue
        a = r['ad'].strip()
        if a.lower() in gorulen: continue
        gorulen.add(a.lower()); adlar.append(a)
open('yeni-adlar.txt','w',encoding='utf-8').write('\n'.join(adlar))
print(len(adlar), 'yeni firma')
"@
& py bul.py domain --dosya yeni-adlar.txt --cikti domainler-yeni.csv 2>&1 | Select-Object -Last 2
