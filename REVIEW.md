# Review of tool.py

One page. Findings **ranked** — most harmful to a customer first.

For each finding: what is wrong, what it does to a customer (not to a linter),
and how you would verify it.

## 1.

Exception'lar doğru HTTP hata cevabına çevrilmiyor.

`convert` içinde bütün hatalar genel `except Exception` ile yakalanıyor ve hata
olmasına rağmen normal conversion response'una benzeyen bir body dönülüyor:

```python
except Exception as exc:
    return {
        "amount": amount,
        "from": from_,
        "to": to,
        "rate": 0.0,
        "result": 0.0,
        "rate_date": str(on or date.today()),
        "source": "ECB via frankfurter.dev",
    }
```

Bu response `error` ve `message` içermiyor, ayrıca FastAPI bunu 200 gibi başarılı
bir cevap olarak döndürebilir. Upstream timeout, 500, invalid JSON veya yanlış
currency gibi durumlarda müşteri gerçek hata yerine `rate: 0.0` ve `result: 0.0`
görebilir.

Müşteri etkisi: Bir AI agent bu cevabı gerçek dönüşüm sonucu sanıp müşteriye
"250 EUR = 0 TRY" gibi tamamen yanlış bir finansal cevap verebilir. README'deki
"wrong number is worse than no number" uyarısına en doğrudan aykırı durum bu.

Nasıl doğrulardım: Frankfurter yerine fake upstream'i 500 dönecek, timeout
atacak veya JSON olmayan body dönecek şekilde ayarlardım. Beklenen davranış
non-2xx status ile `{ "error": "...", "message": "..." }` dönmesi olmalı; mevcut
kodun başarılı görünümlü `rate: 0.0` cevabı döndürdüğünü kontrol ederdim.

## 2.

Cache istenen tarihi dikkate almıyor.

`tool.py` içinde cache anahtarı sadece para birimi çiftinden oluşuyor:

```python
key = f"{base}-{target}"
```

Bu yüzden `EUR-TRY` için bir kur cache'e girdikten sonra, farklı tarihlerdeki
`EUR-TRY` istekleri de aynı kuru kullanıyor.

Müşteri etkisi: Müşteri 2021 tarihli bir dönüşüm istediğinde servis 2026
tarihinden cache'lenmiş kuru döndürebiliyor. Daha kötüsü, response içinde bu
kurun `2021-09-01` tarihine ait olduğunu söylüyor. Bu sadece cache problemi
değil; müşteriye yanlış finansal sonuç vermek demek.

Nasıl doğruladım: `tool.py` servisini çalıştırıp aynı para birimi çifti için iki
farklı tarih sordum:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-09-01
/tools/convert?amount=250&from_=EUR&to=TRY&on=2021-09-01
```

İki cevapta da aynı kur döndü:

```json
"rate": 55.95
```

Ama ikinci cevapta servis bu kuru şu tarihe aitmiş gibi gösterdi:

```json
"rate_date": "2021-09-01"
```

Bu, README'deki "kur ait olmadığı bir tarihe aitmiş gibi gösterilmemeli"
şartını ihlal ediyor.

## 3.

Weekend/holiday tarihleri için `asked_date` ve `rate_date` ayrımı yapılmıyor.

README'de `asked_date` caller'ın istediği tarih, `rate_date` ise kullanılan
kurun gerçekten ait olduğu tarih olarak tanımlanıyor. `tool.py` response'unda
`asked_date` alanı hiç yok ve `rate_date` değeri de upstream'in döndürdüğü
gerçek `date` alanından değil, caller'ın istediği `on` parametresinden
üretiliyor.

Müşteri etkisi: Müşteri 2026-08-30 gibi ECB'nin kur yayınlamadığı bir tarih
istediğinde servis yine de başarılı cevap dönüyor ve `rate_date` alanında
`2026-08-30` yazıyor. Bu, kullanılan kurun gerçekten o güne ait olduğu
izlenimini verir. Bir AI agent bu cevabı müşteriye açıklarken yanlış tarihli
finansal bilgi verebilir.

Nasıl doğruladım: `tool.py` servisine şu isteği attım:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-08-30
```

Servis şu alanı döndürdü:

```json
"rate_date": "2026-08-30"
```

Oysa 2026-08-30 Pazar günü olduğu için ECB o gün kur yayınlamaz. Servis
upstream'in döndürdüğü gerçek `date` alanını okumalı, bunu `rate_date` olarak
göstermeli ve caller'ın istediği tarihi ayrı bir `asked_date` alanında
tutmalıydı.

## 4.

Gelecek veya olmayan tarihler `latest` kura düşüp geçerli cevap gibi görünebiliyor.

`fetch_rate` içinde hedef rate bulunamadığında kod bunu sadece weekend/holiday
durumu gibi yorumlayıp `/latest` endpoint'ine fallback ediyor:

```python
if target not in payload.get("rates", {}):
    response = await client.get(f"{UPSTREAM}/latest", params={"base": base, "symbols": target})
    payload = response.json()
```

Bu fallback çok geniş. Gelecek tarih, seri başlangıcından önceki tarih, yanlış
currency veya bozuk upstream response'u gibi durumlar da aynı yola düşebilir.

Müşteri etkisi: Müşteri `2090-01-01` gibi gelecekte ve kur yayınlanması mümkün
olmayan bir tarih istediğinde servis bugünün/latest kurunu kullanıp başarılı
cevap döndürebiliyor. Daha kötüsü, response'ta bu kurun `2090-01-01` tarihine
ait olduğunu söylüyor.

Nasıl doğruladım: `tool.py` servisine şu isteği attım:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2090-01-01
```

Servis şu cevabı döndürdü:

```json
{"amount":250.0,"from":"EUR","to":"TRY","rate":55.91,"result":13977.5,"rate_date":"2090-01-01","source":"ECB via frankfurter.dev"}
```

Ardından güncel tarih için attığım istek de aynı kuru döndürdü:

```text
/tools/convert?amount=250&from_=EUR&to=TRY&on=2026-09-02
```

```json
{"amount":250.0,"from":"EUR","to":"TRY","rate":55.91,"result":13977.5,"rate_date":"2026-09-02","source":"ECB via frankfurter.dev"}
```

Bu, olmayan bir tarih için latest kurun kullanıldığını ve rate tarihinin yanlış
sunulduğunu gösteriyor.

## 5.

`FX_UPSTREAM_BASE` kullanılmıyor.

`tool.py` içinde gerçek Frankfurter host'u hardcoded:

```python
UPSTREAM = "https://api.frankfurter.dev/v1"
```

README ise upstream URL'nin `FX_UPSTREAM_BASE` environment variable'ından
okunmasını istiyor. Reviewer fake upstream verdiğinde bu servis onu kullanamaz;
test ortamı yerine her zaman gerçek host'a gitmeye çalışır.

## 6.

Kur erken yuvarlanıyor ve sonuç yuvarlanmış kurla hesaplanıyor.

`tool.py` içinde upstream'den gelen kur önce iki haneye yuvarlanıyor:

```python
rate = round(rate, 2)
result = round(amount * rate, 2)
```

Bu, Frankfurter'ın daha hassas döndürdüğü kuru kaybettiriyor. Örneğin upstream
`47.1234` döndürürse servis bunu `47.12` yapıyor ve sonucu da bu kırpılmış
değerle hesaplıyor.

Müşteri etkisi: Küçük tutarlarda fark az görünebilir, ama yüksek tutarlı
dönüşümlerde iki ondalığa erken yuvarlama müşteriye yanlış finansal sonuç
verebilir. Kur response'ta daha az hassas gösterilse bile hesaplama mümkün
olduğunca upstream'den gelen gerçek rate ile yapılmalı.

Nasıl doğrulardım: Fake upstream ile `rate=47.1234` döndürüp `amount=250`
isteği atardım. Doğru hesap `250 * 47.1234 = 11780.85` olmalı. Kod önce
`47.12`'ye yuvarladığı için sonucu `11780.00` hesaplar.

## The one I would fix before shipping tonight

İlk bulguyu düzeltirdim: exception'lar 200 görünümlü `rate: 0.0` cevabına
çevrilmemeli, non-2xx status ile `{ "error": "...", "message": "..." }`
dönmeliydi.

## Things that look suspicious but are fine

Being right about a non-issue is worth as much as finding a real defect.
