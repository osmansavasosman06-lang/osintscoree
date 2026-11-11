# OSINTCORE v2.4 - Çoklu Platform Açık Kaynak İstihbarat Platformu

Discord, Instagram, YouTube ve TikTok üzerindeki herkese açık (public) verileri analiz eden, **Free / Pro** abonelik & kredi sistemine ve **hCaptcha** bot korumasına sahip tam yığın (Full-Stack) web uygulaması.

## Özellikler
- **Sıfır Sahte / Demo Veri:** Tüm modüller gerçek HTTP uç noktaları, Discord API v9 public invite endpoint'i, YouTube oEmbed/RSS akışları ve Snowflake bit-shift algoritmaları ile canlı çalışır.
- **Kayıt Ol & Giriş Yap + hCaptcha:** Hem `/register` hem `/login` uç noktalarında sunucu taraflı (`https://api.hcaptcha.com/siteverify`) doğrulama aktif olarak çalışır.
- **Ücretsiz (Beleş) Modüller:**
  1. Discord Snowflake & ID Çözücü
  2. Discord Davet Kodu (Invite) İstihbaratı
  3. YouTube Video & Kanal Metadata Çıkarıcı
  4. Hızlı Kullanıcı Adı Ayak İzi Taraması
- **Ücretli (PRO) Modüller:**
  5. Instagram Derin Profil & Biyografi Analizi
  6. TikTok Profil & Video Sinyal İstihbaratı
  7. YouTube Kanal Kaynak Kod & RSS İstihbaratı
  8. Çapraz Platform Kimlik Korelasyon Motoru

## Kurulum ve Çalıştırma

1. Klasöre girin ve sanal ortam oluşturun:
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. `.env.example` dosyasının adını `.env` olarak değiştirin ve hCaptcha **Secret Key** değerinizi yazın:
```env
SECRET_KEY=guclu-bir-gizli-anahtar-yaz
HCAPTCHA_SITEKEY=f7f82598-e7dc-49a2-8fda-6c084054b8ee
HCAPTCHA_SECRET=BURAYA_HCAPTCHA_SECRET_KEY_YAZ
```
*(Not: hCaptcha panelinden aldığınız iki anahtardan biri `sitekey` (HTML tarafında görünür), diğeri `secret` (sadece sunucuda `.env` içinde saklanan gizli anahtar) değeridir.)*

3. Uygulamayı başlatın:
```bash
python app.py
```
Tarayıcıdan `http://127.0.0.1:5000` adresine gidin.
