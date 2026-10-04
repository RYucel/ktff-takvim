# KKTC Futbol Takvimi

KTFF fikstürlerini (AKSA Süper Lig, AKSA 1. Lig; A2 ligleri isteğe bağlı) takvim aboneliğine çevirir.
fixtur.es'in KKTC için olmayan karşılığı.

- **Google Takvim:** Her lig ve takım için public bir Google takvimi. Etkinlikler Calendar API ile
  doğrudan yazılır; saat değişikliği abonelere dakikalar içinde yansır.
- **Apple / Outlook / diğerleri:** Her lig ve takım için `.ics` dosyası (GitHub Pages).
- **Abone sayfası:** `docs/index.html`; takım ara, tek tıkla ekle.

```
cron-job.org ──(her 15 dk, POST /dispatches)──▶ GitHub Actions
                                                  ├─ ktff.org fikstür sayfalarını tara
                                                  ├─ data/matches.json güncelle (Maç No = sabit kimlik)
                                                  ├─ Google Calendar API: sadece değişen etkinlikler
                                                  └─ docs/*.ics + index.html → commit → GitHub Pages
```

## Kurulum (yaklaşık 20 dk)

### 1. Repo ve Pages
1. Bu klasörü **public** bir GitHub reposu olarak push et. Public repolarda Actions dakikaları sınırsız.
2. **Settings → Pages →** Source: *Deploy from a branch*, Branch: `main`, klasör: `/docs`.
3. Özel alan adı kullanacaksan: **Settings → Secrets and variables → Actions → Variables** altında
   `SITE_URL` = `https://takvim.ornek.com`. Kullanmayacaksan bir şey yapma; adres otomatik
   `https://<kullanici>.github.io/<repo>` olur.

### 2. Google Calendar katmanı
1. [Google Cloud Console](https://console.cloud.google.com/)'da bir proje aç, **Google Calendar API**'yi etkinleştir.
2. **IAM & Admin → Service Accounts →** yeni service account oluştur (rol gerekmez).
   **Keys → Add key → JSON** ile anahtarı indir.
3. Repo **Settings → Secrets and variables → Actions → Secrets:**
   - `GCP_SA_KEY` → JSON dosyasının tüm içeriği
   - `CAL_OWNER_EMAIL` → (opsiyonel) kendi Gmail adresin. Takvimlere sahip yetkisi verilir;
     Google Takvim'de görür, gerekirse elle düzeltirsin.
4. Takvimler service account'a aittir ve herkese açık okunur. `data/gcal_state.json` takvim
   kimliklerini tutar. **Bu dosyayı silme**, silersen yeni takvimler oluşur ve mevcut aboneler kopar.

> Google kısa sürede çok sayıda takvim oluşturmayı sınırlayabilir (2 lig ≈ 30 takvim).
> İlk çalıştırmada bir kısmı hata verirse sorun değil; kalanlar sonraki çalıştırmalarda oluşur.

### 3. İlk çalıştırma
**Actions → Takvimleri güncelle → Run workflow → mode: full.** Logda her lig için maç sayısını
gör (`super-lig: 240 maç...`). Bittiğinde `docs/` dolar ve Pages birkaç dakikada yayına girer.

### 4. Hızlı tetikleyici: cron-job.org
GitHub'ın kendi `schedule:` tetikleyicisi yoğun saatlerde 10-60 dk gecikebiliyor, hatta bazen atlıyor.
`workflow_dispatch` ise API çağrısıyla anında kuyruğa girer. Zamanlamayı ücretsiz **cron-job.org** yapar:

1. GitHub → **Settings → Developer settings → Fine-grained tokens → Generate:**
   sadece bu repo, izin: **Actions: Read and write**. Süresi dolunca yenilemeyi unutma
   (takvimine hatırlatma koy).
2. [cron-job.org](https://cron-job.org)'da hesap aç, saat dilimini **Europe/Nicosia** yap, yeni cronjob oluştur:
   - **URL:** `https://api.github.com/repos/<KULLANICI>/<REPO>/actions/workflows/update.yml/dispatches`
   - **Advanced → Request method:** `POST`
   - **Headers:**
     ```
     Accept: application/vnd.github+json
     Authorization: Bearer <TOKEN>
     X-GitHub-Api-Version: 2022-11-28
     Content-Type: application/json
     ```
   - **Body:** `{"ref":"main","inputs":{"mode":"quick"}}`
   - Başarılı yanıt **HTTP 204**'tür (gövde boş).
3. Önerilen zamanlama (iki ayrı cronjob):
   - **Maç günleri (Cuma–Pazartesi), 10:00–23:45, her 15 dk:** `mode: quick`
   - **Hafta içi (Salı–Perşembe), her 3 saatte:** `mode: quick`
   - Tam tarama zaten workflow'daki gece `schedule:` ile yapılıyor (gecikmesi önemsiz).
     İstersen cron-job.org'a 05:00'te bir `{"ref":"main","inputs":{"mode":"full"}}` işi de ekle.

`quick` modu sitenin gösterdiği güncel haftayı ve çevresini tarar (~5 sayfa/lig).
`full` tüm sezonu tarar (~35 sayfa/lig) ve bilinmeyen saha bilgilerini doldurur.
İstekler arasında 0,6 sn bekleme var, KTFF sunucusunu yormaz.

## Yerel çalıştırma
```bash
pip install -r requirements.txt
python -m ktff_cal --mode full -v          # GCP_SA_KEY yoksa Google katmanı atlanır
python -m ktff_cal --offline --no-gcal     # sadece kayıtlı veriden ICS/sayfa üret
pip install pytest icalendar && pytest -q  # testler (ağ gerektirmez)
```

## Yeni sezon
KTFF her sezon lig adresindeki sayıyı değiştiriyor (`aksa-super-lig-163` gibi). Yeni sezonda
`ktff_cal/config.py` içindeki `LEAGUES[].path` değerlerini güncelle ve `full` çalıştır.
Takım takvimleri kalıcıdır: küme düşen takımın takvimi yeni liginin maçlarıyla devam eder.

## Bilinen sınırlar
- **Parser canlı sayfaya karşı test edilmedi.** Geliştirme ortamı ktff.org'a erişemediği için
  sayfanın metin yapısından (tarih başlıkları + `/maclar/<No>` linkleri + "Maç No: …") yola çıkılarak
  yazıldı ve fixture'larla test edildi. HTML sınıflarına değil metne dayandığı için dayanıklı,
  ama ilk `full` çalıştırmada maç sayılarını kontrol et. 0 maç gelirse `-v` ile çalıştırıp çıktıya bak.
- Saat açıklanmamış maçlar tüm gün etkinliği olarak görünür, saat gelince otomatik saatli olur.
- Apple/Outlook ICS'yi kendi aralığında yeniler (Apple'da abonelik ayarından 15 dk–1 saat seçilebilir).
- Veri KTFF'nin sitesinden alınır. Bu proje KTFF ile bağlantılı değildir.

## Dosyalar
| Yol | Ne |
|---|---|
| `ktff_cal/scrape.py` | Fikstür ve maç sayfası parser'ı |
| `ktff_cal/store.py` | `data/matches.json`, değişiklik takibi (rev/SEQUENCE) |
| `ktff_cal/events.py` | Maç → etkinlik metni, lig/takım takvim listesi |
| `ktff_cal/ics.py` | RFC 5545 ICS üretimi |
| `ktff_cal/gcal.py` | Google Calendar senkronu (sadece değişenler, silinenleri temizler) |
| `ktff_cal/site.py` | `docs/` altına ICS'ler ve abone sayfası |
| `.github/workflows/update.yml` | Dispatch + gece yedek tarama + commit |
