# Xphere Community Bot — Daily Check-in

Bot check-in harian otomatis untuk **Xphere Community Bot** ([t.me/Xphere_CommunityBot](https://t.me/Xphere_CommunityBot)) menggunakan session Telegram yang sudah ada — **tanpa login ulang, tanpa browser, tanpa emulator**.

> ⚠️ Panduan ini untuk edukasi & manajemen akun milik sendiri. Gunakan secara bertanggung jawab.

---

## Apa yang dikerjakan bot ini

| Aksi | Frekuensi | Poin |
|---|---|---|
| Daily check-in | 1×/hari | +2 |
| Misi: Join Telegram | sekali | +5 |
| Misi: Follow X | sekali | +5 |
| Misi: Visit website | sekali | +3 |
| Misi: Comment / Like / Retweet | sekali | +3 × 3 |
| Referral | sekali | +5 ke referrer |

Setup awal (onboarding + misi + hubungkan X) **tidak** diotomasi oleh repo ini — lihat bagian [Setup Awal Akun](#setup-awal-akun) di bawah. Bot ini fokus ke **daily check-in** yang berulang tiap hari.

---

## Cara kerja

```
┌──────────────┐    1. RequestWebView     ┌─────────────────┐
│ Session      │ ────────────────────────▶│  @Xphere_Comm…  │
│ Telethon     │                          │  (bot Telegram) │
│ (accNN.sess) │ ◀────────────────────────└─────────────────┘
└──────────────┘      initData (tgWebAppData)
        │
        │ 2. POST {action:"checkin", initData}
        ▼
┌─────────────────────────────────────┐
│  Supabase Edge Function             │
│  (dynamic-handler)                  │
│  → verifikasi signature initData    │
│  → beri +2 poin, catat streak       │
└─────────────────────────────────────┘
```

Kunci autentikasi ke backend adalah **`initData`** yang ditandatangani Telegram. Bot ini memintanya langsung ke Telegram via MTProto (Telethon) — tidak perlu membuka mini app di browser.

---

## Persyaratan

- **Python 3.10+**
- `pip install telethon`
- **File session Telethon** per akun (`acc01.session`, `acc02.session`, …) yang **sudah login** (authorized). Session ini biasanya dihasilkan sekali dengan login nomor telepon + kode OTP.
- `api_id` & `api_hash` Telegram (gratis dari [my.telegram.org](https://my.telegram.org)) — untuk membuka session, **tidak** digunakan untuk login ulang.
- Koneksi internet biasa — **tidak butuh proxy** khusus untuk check-in (aktifitas read-only, sekali sehari).

---

## Instalasi

```bash
git clone https://github.com/asbryx/xphere-daily.git
cd xphere-daily
pip install telethon
cp .env.example .env
# edit .env — isi SESSION_DIR, TG_API_ID, TG_API_HASH
```

### Struktur folder yang diharapkan

```
xphere-daily/
├── xphere_daily.py       # script utama
├── .env                  # konfigurasi lokal (JANGAN di-commit)
├── sessions/             # folder file .session (JANGAN di-commit)
│   ├── acc01.session
│   ├── acc02.session
│   └── …
└── xphere_state.json     # (opsional) mapping/status akun
```

### Format `.env`

```ini
SESSION_DIR=./sessions
TG_API_ID=12345678
TG_API_HASH=0123456789abcdef0123456789abcdef
STATE_FILE=./xphere_state.json
LOG_FILE=./xphere_checkin_log.jsonl
DELAY_BETWEEN=3
```

### Format `xphere_state.json` (opsional)

Kalau ada, bot hanya memproses akun yang terdaftar di sini. Formatnya:

```json
{
  "accounts": {
    "acc01": {"onboarded": true, "x_connected": true},
    "acc02": {"onboarded": true, "x_connected": true}
  }
}
```

Kalau file tidak ada, bot otomatis memproses semua `acc*.session` di folder `sessions/`.

---

## Menjalankan

```bash
python xphere_daily.py
```

Output:

```
=== XPHERE DAILY CHECK-IN: 26 akun ===
acc01    ✓ +24 pts total (streak 2)
acc02    ~ sudah checkin hari ini
acc03    ✗ session unauthorized
…
=== SELESAI: 25 checkin baru | 1 sudah | 0 gagal ===
```

Log lengkap tersimpan di `xphere_checkin_log.jsonl`.

### Jadwal otomatis (opsional)

**Windows Task Scheduler:**
```
Program : python.exe
Argument: C:\path\to\xphere_daily.py
Trigger : Daily 09:00
```

**Linux cron:**
```cron
0 9 * * * cd /path/to/xphere-daily && /usr/bin/python3 xphere_daily.py >> cron.log 2>&1
```

---

## Setup Awal Akun (di luar bot ini)

Sebelum akun bisa check-in, tiap akun harus **onboarded** dulu lewat mini app Xphere:

1. Buka [t.me/Xphere_CommunityBot](https://t.me/Xphere_CommunityBot) → `/start`
2. Tekan **Play** → ikuti onboarding (setuju, hubungkan X, isi wallet EVM)
3. Selesaikan misi sekali-klaim (Join TG, Follow X, dll)

Otomasi onboarding + hubungkan X **ada di repo lain** (private) karena melibatkan kredensial akun X. Repo ini hanya untuk **daily check-in** yang repeatable & aman dibagikan.

---

## Troubleshooting

| Masalah | Penyebab | Solusi |
|---|---|---|
| `session unauthorized` | Session file rusak/expired | Login ulang session tersebut |
| `HTTP 401` di backend | Anon key Supabase berubah | Update `SUPABASE_ANON_KEY` di `.env` |
| `initData kosong` | Bot menolak RequestWebView | Coba ulang, atau session di-ban bot |
| `WinError 10061/1231` | Network flap / DNS ISP | Retry beberapa menit lagi |
| Check-in `already` terus | Jam UTC belum ganti | Check-in reset jam **00:00 UTC** (07:00 WIB) |

---

## Keamanan

- **File `.session` = kredensial penuh akun Telegram.** Jangan pernah di-commit atau dibagikan.
- `api_id`/`api_hash` boleh di-share ke tim, tapi idealnya tetap di `.env`.
- Script ini **tidak** menyimpan password / token apapun — semuanya di file session Telethon yang di-encrypt oleh library.
- Supabase anon key yang dipakai adalah **public anon key** milik mini app Xphere (ter ekspos di client manapun) — bukan secret.

---

## Lisensi

MIT — gunakan secara bijak, tanggung jawab masing-masing.
