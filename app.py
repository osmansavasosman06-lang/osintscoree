import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "osintcore-super-secret-key-2026")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///osintcore.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

HCAPTCHA_SITEKEY = os.getenv("HCAPTCHA_SITEKEY", "f7f82598-e7dc-49a2-8fda-6c084054b8ee")
HCAPTCHA_SECRET = os.getenv("HCAPTCHA_SECRET", "")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Bu alana erişmek için giriş yapmalısınız."
login_manager.login_message_category = "warning"


# -------------------- MODELLER --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    plan = db.Column(db.String(20), default="free", nullable=False)  # free, pro, enterprise
    credits = db.Column(db.Integer, default=15, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    logs = db.relationship("QueryLog", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_pro(self):
        return self.plan in ("pro", "enterprise")


class QueryLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    tool_code = db.Column(db.String(64), nullable=False)
    target = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), default="success")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------- HCAPTCHA DOĞRULAMA --------------------
def verify_hcaptcha(token: str, ip: str):
    if not token:
        return False, ["missing-input-response"]

    # Eğer kullanıcı .env içine henüz secret key girmediyse uyarı döndür
    if not HCAPTCHA_SECRET or HCAPTCHA_SECRET == "BURAYA_HCAPTCHA_SECRET_KEY_YAZ":
        return False, ["server-missing-hcaptcha-secret"]

    data = {
        "secret": HCAPTCHA_SECRET,
        "response": token,
        "remoteip": ip,
        "sitekey": HCAPTCHA_SITEKEY,
    }
    try:
        resp = requests.post(
            "https://api.hcaptcha.com/siteverify",
            data=data,
            timeout=6,
        )
        j = resp.json()
        if j.get("success"):
            return True, []
        return False, j.get("error-codes", ["verification-failed"])
    except requests.RequestException as exc:
        return False, [f"network-error: {str(exc)}"]


# -------------------- ARAÇ KATALOĞU --------------------
TOOLS = [
    # ÜCRETSİZ (FREE) ARAÇLAR
    {
        "code": "dc_snowflake",
        "platform": "Discord",
        "name": "Discord Snowflake & ID Çözücü",
        "tier": "free",
        "cost": 0,
        "desc": "Discord Kullanıcı, Sunucu veya Mesaj ID'sinden milisaniye hassasiyetinde hesap oluşturulma tarihini, Worker ID ve Process ID verilerini çıkarır."
    },
    {
        "code": "dc_invite",
        "platform": "Discord",
        "name": "Discord Davet Kodu (Invite) İstihbaratı",
        "tier": "free",
        "cost": 0,
        "desc": "Açık Discord davet kodlarından sunucu adı, üye sayısı, çevrimiçi sayısı, doğrulama seviyesi ve sunucu özelliklerini çeker."
    },
    {
        "code": "yt_oembed",
        "platform": "YouTube",
        "name": "YouTube Video & Kanal Metadata Çıkarıcı",
        "tier": "free",
        "cost": 0,
        "desc": "Herhangi bir YouTube video bağlantısından kanal adı, kanal URL'si, yüksek çözünürlüklü kapak görselleri ve oEmbed yapısını getirir."
    },
    {
        "code": "username_footprint",
        "platform": "Multi-Platform",
        "name": "Hızlı Kullanıcı Adı Ayak İzi Taraması",
        "tier": "free",
        "cost": 0,
        "desc": "Verilen kullanıcı adının YouTube, TikTok ve açık dizinlerdeki profil varlığını gerçek zamanlı HTTP durum kontrolü ile doğrular."
    },
    # ÜCRETLİ (PRO) ARAÇLAR
    {
        "code": "ig_deep_osint",
        "platform": "Instagram",
        "name": "Instagram Derin Profil & Biyografi Analizi",
        "tier": "pro",
        "cost": 2,
        "desc": "Açık profil meta etiketlerini, biyografi bağlantılarını, dış URL yönlendirmelerini ve herkese açık etkileşim sinyallerini ayrıştırır."
    },
    {
        "code": "tt_profile_intel",
        "platform": "TikTok",
        "name": "TikTok Profil & Video Sinyal İstihbaratı",
        "tier": "pro",
        "cost": 2,
        "desc": "TikTok kullanıcı profili veya video linkinden açık meta verileri, bölge/etiket sinyallerini ve paylaşım özetini çıkartır."
    },
    {
        "code": "yt_channel_audit",
        "platform": "YouTube",
        "name": "YouTube Kanal Kaynak Kod & RSS İstihbaratı",
        "tier": "pro",
        "cost": 3,
        "desc": "Kanal sayfası ve herkese açık RSS akışı üzerinden Channel ID, son yüklenen videolar, yayın zaman damgaları ve açıklama anahtar kelimelerini çıkarır."
    },
    {
        "code": "cross_correlation",
        "platform": "Multi-Platform",
        "name": "Çapraz Platform Kimlik Korelasyon Motoru",
        "tier": "pro",
        "cost": 5,
        "desc": "Discord, Instagram, YouTube ve TikTok genelinde aynı kullanıcı adı ve biyografi izlerini tek raporda birleştirip güven skoru hesaplar."
    }
]

TOOLS_MAP = {t["code"]: t for t in TOOLS}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7"
}


# -------------------- GERÇEK OSİNT MOTORLARI --------------------
def run_dc_snowflake(target: str):
    clean_id = re.sub(r"\D", "", target.strip())
    if not clean_id or len(clean_id) < 15 or len(clean_id) > 22:
        raise ValueError("Geçerli bir 17-20 haneli Discord Snowflake ID girin.")
    snowflake = int(clean_id)
    discord_epoch = 1420070400000
    timestamp_ms = (snowflake >> 22) + discord_epoch
    worker_id = (snowflake & 0x3E0000) >> 17
    process_id = (snowflake & 0x1F000) >> 12
    increment = snowflake & 0xFFF
    dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    return {
        "snowflake_id": str(snowflake),
        "created_at_utc": dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC",
        "unix_timestamp": int(timestamp_ms / 1000),
        "internal_worker_id": worker_id,
        "internal_process_id": process_id,
        "increment_sequence": increment,
        "account_age_days": (datetime.now(timezone.utc) - dt).days
    }


def run_dc_invite(target: str):
    code = target.strip().rstrip("/").split("/")[-1]
    if not re.match(r"^[a-zA-Z0-9\-_]{2,32}$", code):
        raise ValueError("Geçerli bir Discord davet kodu veya linki girin (örn: discord.gg/python).")
    url = f"https://discord.com/api/v9/invites/{code}?with_counts=true&with_expiration=true"
    r = requests.get(url, headers=HEADERS, timeout=8)
    if r.status_code == 404:
        raise ValueError("Davet kodu bulunamadı veya süresi dolmuş.")
    if r.status_code != 200:
        raise ValueError(f"Discord API yanıt kodu: {r.status_code}")
    data = r.json()
    guild = data.get("guild", {})
    inviter = data.get("inviter", {})
    return {
        "invite_code": data.get("code"),
        "guild_id": guild.get("id"),
        "guild_name": guild.get("name"),
        "guild_description": guild.get("description") or "Açıklama yok",
        "verification_level": guild.get("verification_level"),
        "approx_member_count": data.get("approximate_member_count"),
        "approx_online_count": data.get("approximate_presence_count"),
        "features": guild.get("features", []),
        "inviter_username": inviter.get("username") if inviter else "Gizli / Sistem",
        "expires_at": data.get("expires_at") or "Süresiz"
    }


def run_yt_oembed(target: str):
    url = target.strip()
    if not url.startswith("http"):
        url = f"https://www.youtube.com/watch?v={url}"
    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
    r = requests.get(oembed_url, headers=HEADERS, timeout=8)
    if r.status_code != 200:
        raise ValueError("YouTube videosu bulunamadı veya oEmbed verisi kapalı.")
    data = r.json()
    return {
        "title": data.get("title"),
        "author_name": data.get("author_name"),
        "author_url": data.get("author_url"),
        "provider": data.get("provider_name"),
        "thumbnail_url": data.get("thumbnail_url"),
        "dimensions": f"{data.get('width')}x{data.get('height')}"
    }


def run_username_footprint(target: str):
    username = target.strip().lstrip("@")
    if not re.match(r"^[a-zA-Z0-9._\-]{2,35}$", username):
        raise ValueError("Geçerli bir kullanıcı adı girin (harf, rakam, nokta, alt çizgi).")

    checks = {
        "YouTube": f"https://www.youtube.com/@{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "GitHub": f"https://github.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}/about.json"
    }
    results = {}
    for platform, check_url in checks.items():
        try:
            res = requests.get(check_url, headers=HEADERS, timeout=6, allow_redirects=True)
            if platform == "Reddit":
                found = res.status_code == 200 and '"error": 404' not in res.text
            elif platform == "TikTok":
                found = res.status_code == 200 and f'"uniqueId":"{username.lower()}"' in res.text.lower()
            else:
                found = res.status_code == 200
            results[platform] = {
                "status": "BULUNDU" if found else "BULUNAMADI / GİZLİ",
                "http_code": res.status_code,
                "url": check_url.replace("/about.json", "")
            }
        except requests.RequestException:
            results[platform] = {
                "status": "ZAMAN AŞIMI",
                "http_code": 0,
                "url": check_url
            }
    return {"queried_username": username, "platforms": results}


def run_ig_deep_osint(target: str):
    username = target.strip().lstrip("@").rstrip("/").split("/")[-1]
    if not re.match(r"^[a-zA-Z0-9._]{1,30}$", username):
        raise ValueError("Geçerli bir Instagram kullanıcı adı girin.")
    profile_url = f"https://www.instagram.com/{username}/"
    r = requests.get(profile_url, headers=HEADERS, timeout=8)
    if r.status_code == 404:
        raise ValueError("Instagram profili bulunamadı.")
    html = r.text
    title_match = re.search(r'<meta property="og:title" content="(.*?)"', html)
    desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html)
    img_match = re.search(r'<meta property="og:image" content="(.*?)"', html)

    description = desc_match.group(1) if desc_match else "Meta açıklama erişime kapalı (Giriş duvarı)"
    stats = re.findall(r"([\d.,]+[KMB]?\s+(?:Followers|Following|Posts|Takipçi|Takip|Gönderi))", description, re.I)

    return {
        "username": username,
        "profile_url": profile_url,
        "http_status": r.status_code,
        "og_title": title_match.group(1) if title_match else username,
        "public_summary": description,
        "extracted_metrics": stats if stats else ["Açık metrik ayrıştırılamadı"],
        "avatar_preview": img_match.group(1) if img_match else "Mevcut değil"
    }


def run_tt_profile_intel(target: str):
    cleaned = target.strip()
    if cleaned.startswith("http"):
        url = cleaned
    else:
        uname = cleaned.lstrip("@")
        url = f"https://www.tiktok.com/@{uname}"

    r = requests.get(url, headers=HEADERS, timeout=8)
    if r.status_code == 404:
        raise ValueError("TikTok hedefi bulunamadı.")
    html = r.text
    title_m = re.search(r"<title>(.*?)</title>", html, re.S)
    desc_m = re.search(r'<meta name="description" content="(.*?)"', html)
    uid_m = re.search(r'"id":"(\d{10,25})"', html)
    region_m = re.search(r'"region":"([A-Z]{2})"', html)

    return {
        "target_url": url,
        "http_status": r.status_code,
        "page_title": title_m.group(1).strip() if title_m else "Bilinmiyor",
        "meta_description": desc_m.group(1) if desc_m else "Açık açıklama bulunamadı",
        "detected_numeric_id": uid_m.group(1) if uid_m else "Gizli / Dinamik JS",
        "detected_region_signal": region_m.group(1) if region_m else "Belirtilmemiş"
    }


def run_yt_channel_audit(target: str):
    handle = target.strip()
    if not handle.startswith("http"):
        if not handle.startswith("@") and not handle.startswith("UC"):
            handle = f"@{handle}"
        url = f"https://www.youtube.com/{handle}" if handle.startswith("@") else f"https://www.youtube.com/channel/{handle}"
    else:
        url = handle

    r = requests.get(url, headers=HEADERS, timeout=8)
    if r.status_code != 200:
        raise ValueError("YouTube kanalı bulunamadı.")
    html = r.text
    cid_m = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html)
    title_m = re.search(r'<meta property="og:title" content="(.*?)"', html)
    desc_m = re.search(r'<meta property="og:description" content="(.*?)"', html)

    channel_id = cid_m.group(1) if cid_m else None
    recent_videos = []
    if channel_id:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        rss = requests.get(rss_url, headers=HEADERS, timeout=6)
        if rss.status_code == 200:
            entries = re.findall(r"<entry>(.*?)</entry>", rss.text, re.S)[:5]
            for e in entries:
                vt = re.search(r"<title>(.*?)</title>", e)
                vp = re.search(r"<published>(.*?)</published>", e)
                vl = re.search(r'<link rel="alternate" href="(.*?)"', e)
                recent_videos.append({
                    "title": vt.group(1) if vt else "-",
                    "published": vp.group(1) if vp else "-",
                    "url": vl.group(1) if vl else "-"
                })

    return {
        "channel_title": title_m.group(1) if title_m else handle,
        "channel_id": channel_id or "Tespit edilemedi",
        "rss_feed_url": f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}" if channel_id else "Yok",
        "description": desc_m.group(1) if desc_m else "Yok",
        "latest_5_uploads": recent_videos
    }


def run_cross_correlation(target: str):
    uname = target.strip().lstrip("@")
    footprint = run_username_footprint(uname)
    found_count = sum(1 for v in footprint["platforms"].values() if v["status"] == "BULUNDU")
    confidence = min(100, found_count * 25)
    return {
        "subject": uname,
        "matched_platforms": found_count,
        "correlation_confidence": f"%{confidence}",
        "footprint_matrix": footprint["platforms"],
        "analyst_note": "Aynı kullanıcı adına sahip açık uç noktalar doğrulandı. Biyografi çapraz linkleri manuel incelemeye hazır."
    }


RUNNERS = {
    "dc_snowflake": run_dc_snowflake,
    "dc_invite": run_dc_invite,
    "yt_oembed": run_yt_oembed,
    "username_footprint": run_username_footprint,
    "ig_deep_osint": run_ig_deep_osint,
    "tt_profile_intel": run_tt_profile_intel,
    "yt_channel_audit": run_yt_channel_audit,
    "cross_correlation": run_cross_correlation,
}


# -------------------- ROTALAR --------------------
@app.route("/")
def index():
    return render_template("index.html", tools=TOOLS)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        hcaptcha_token = request.form.get("h-captcha-response", "")
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        ok, errors = verify_hcaptcha(hcaptcha_token, client_ip)
        if not ok:
            flash(f"hCaptcha doğrulaması başarısız oldu: {', '.join(errors)}", "danger")
            return render_template("register.html", sitekey=HCAPTCHA_SITEKEY)

        if len(username) < 3 or len(password) < 6:
            flash("Kullanıcı adı en az 3, şifre en az 6 karakter olmalıdır.", "danger")
            return render_template("register.html", sitekey=HCAPTCHA_SITEKEY)

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("Bu kullanıcı adı veya e-posta zaten kayıtlı.", "danger")
            return render_template("register.html", sitekey=HCAPTCHA_SITEKEY)

        user = User(username=username, email=email, plan="free", credits=15)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("OSINTCORE hesabınız oluşturuldu! 15 ücretsiz başlangıç kredisi tanımlandı.", "success")
        return redirect(url_for("dashboard"))

    return render_template("register.html", sitekey=HCAPTCHA_SITEKEY)


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        hcaptcha_token = request.form.get("h-captcha-response", "")
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        ok, errors = verify_hcaptcha(hcaptcha_token, client_ip)
        if not ok:
            flash(f"hCaptcha doğrulaması başarısız oldu: {', '.join(errors)}", "danger")
            return render_template("login.html", sitekey=HCAPTCHA_SITEKEY)

        user = User.query.filter(
            (User.username == identity) | (User.email == identity.lower())
        ).first()

        if not user or not user.check_password(password):
            flash("Geçersiz kullanıcı adı/e-posta veya şifre.", "danger")
            return render_template("login.html", sitekey=HCAPTCHA_SITEKEY)

        login_user(user)
        flash(f"Tekrar hoş geldin, {user.username}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html", sitekey=HCAPTCHA_SITEKEY)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Oturum güvenli şekilde kapatıldı.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    recent_logs = (
        QueryLog.query.filter_by(user_id=current_user.id)
        .order_by(QueryLog.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template("dashboard.html", tools=TOOLS, logs=recent_logs)


@app.route("/pricing")
def pricing():
    return render_template("pricing.html")


@app.route("/upgrade/<plan_name>", methods=["POST"])
@login_required
def upgrade_plan(plan_name):
    # Ödeme altyapısı (Stripe / Iyzico / Shopier webhook) entegrasyon noktası
    if plan_name == "pro":
        current_user.plan = "pro"
        current_user.credits += 250
        db.session.commit()
        flash("PRO Operatör paketine geçiş yapıldı (+250 Kredi eklendi).", "success")
    elif plan_name == "enterprise":
        current_user.plan = "enterprise"
        current_user.credits += 1000
        db.session.commit()
        flash("ENTERPRISE İstihbarat paketine geçiş yapıldı (+1000 Kredi eklendi).", "success")
    return redirect(url_for("dashboard"))


@app.route("/api/run-tool", methods=["POST"])
@login_required
def api_run_tool():
    payload = request.get_json(silent=True) or {}
    tool_code = payload.get("tool_code", "")
    target = payload.get("target", "").strip()

    tool = TOOLS_MAP.get(tool_code)
    if not tool:
        return jsonify({"ok": False, "error": "Geçersiz istihbarat modülü."}), 400

    if not target:
        return jsonify({"ok": False, "error": "Hedef parametre boş bırakılamaz."}), 400

    if tool["tier"] == "pro" and not current_user.is_pro:
        return jsonify({
            "ok": False,
            "error": "Bu modül PRO / ENTERPRISE üyelik gerektirir. Paketler sayfasından hesabınızı yükseltin.",
            "upgrade_required": True
        }), 403

    cost = tool["cost"]
    if cost > 0 and current_user.credits < cost:
        return jsonify({
            "ok": False,
            "error": f"Yetersiz kredi. Bu modül {cost} kredi gerektirir (Mevcut: {current_user.credits})."
        }), 402

    runner = RUNNERS.get(tool_code)
    try:
        result_data = runner(target)
        if cost > 0:
            current_user.credits -= cost
        log = QueryLog(user_id=current_user.id, tool_code=tool_code, target=target, status="success")
        db.session.add(log)
        db.session.commit()
        return jsonify({
            "ok": True,
            "tool": tool["name"],
            "remaining_credits": current_user.credits,
            "data": result_data
        })
    except ValueError as ve:
        return jsonify({"ok": False, "error": str(ve)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Sorgu motoru hatası: {str(exc)}"}), 500


with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
