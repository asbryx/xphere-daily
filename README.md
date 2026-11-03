# Xphere Community Bot — Daily Check-in

Automated daily check-in for the **Xphere Community Bot** ([t.me/Xphere_CommunityBot](https://t.me/Xphere_CommunityBot)) using existing Telegram sessions — **no re-login, no browser, no emulator**.

> ⚠️ Intended for education & managing accounts you own. Use responsibly.

---

## What this bot does

| Action | Frequency | Points |
|---|---|---|
| Daily check-in | 1×/day | +2 |
| Daily: Comment on X (m1) | 1×/day | +3 |
| Daily: Like on X (m2) | 1×/day | +3 |
| Daily: Retweet on X (m3) | 1×/day | +3 |
| Missions: Join TG / Follow X / Visit web | once | +13 total |
| Referral | once | +5 to referrer |

**Daily total: +11 points per account per day** (check-in + 3 Twitter missions).
The 3 Twitter missions are click-only: the server never verifies the actual X activity —
claims succeed without touching your X accounts.

Initial account setup (onboarding, missions, X connection) is **not** automated by this repo — see [Initial Account Setup](#initial-account-setup) below. This repo focuses on the **daily check-in**, which repeats every day.

## Two scripts, pick one

| Script | Behavior | Best for |
|---|---|---|
| `xphere_daily.py` | Run once → check-in all accounts → exit | Cron / Task Scheduler |
| `xphere_daily_loop.py` | Run once → check-in → **loop forever** (auto-retry failures + sleep until next UTC day) | VPS / dedicated box |

Both do the same check-in. The loop version is a daemon — start it once and forget it:

```bash
python xphere_daily_loop.py
```

- Failed accounts (network/session errors) are **auto-retried every 30 minutes** (max 6 retries/day)
- Once all accounts succeed or are `already`, it sleeps until **00:05 UTC** (the daily reset) and starts over
- Restart-safe: accounts that already checked in are skipped automatically
- Logs: `xphere_daily_loop.log` + `xphere_daily_loop.jsonl`

---

## How it works

```
┌──────────────┐    1. RequestWebView     ┌─────────────────┐
│ Telethon     │ ────────────────────────▶│  @Xphere_Comm…  │
│ session      │                          │  (Telegram bot) │
│ (accNN.sess) │ ◀────────────────────────└─────────────────┘
└──────────────┘      initData (tgWebAppData)
        │
        │ 2. POST {action:"checkin", initData}
        ▼
┌─────────────────────────────────────┐
│  Supabase Edge Function             │
│  (dynamic-handler)                  │
│  → verifies initData signature      │
│  → grants +2 points, updates streak │
└─────────────────────────────────────┘
```

The backend authenticates via **`initData`** signed by Telegram. This bot requests it directly from Telegram over MTProto (Telethon) — no need to open the mini app in a browser.

---

## Requirements

- **Python 3.10+**
- `pip install telethon`
- **Telethon session files** per account (`acc01.session`, `acc02.session`, …) that are **already logged in** (authorized). Sessions are created once with a phone number + OTP login.
- Telegram `api_id` & `api_hash` (free from [my.telegram.org](https://my.telegram.org)) — used to open existing sessions, **not** to log in again.
- A normal internet connection — **no proxies needed** for check-in (read-only activity, once per day).

---

## Installation

```bash
git clone https://github.com/asbryx/xphere-daily.git
cd xphere-daily
pip install telethon
cp .env.example .env
# edit .env — set SESSION_DIR, TG_API_ID, TG_API_HASH
```

### Expected folder layout

```
xphere-daily/
├── xphere_daily.py       # main script
├── .env                  # local config (DO NOT commit)
├── sessions/             # folder with .session files (DO NOT commit)
│   ├── acc01.session
│   ├── acc02.session
│   └── …
└── xphere_state.json     # (optional) account mapping/status
```

### `.env` format

```ini
SESSION_DIR=./sessions
TG_API_ID=12345678
TG_API_HASH=0123456789abcdef0123456789abcdef
STATE_FILE=./xphere_state.json
LOG_FILE=./xphere_checkin_log.jsonl
DELAY_BETWEEN=4

# loop-only (xphere_daily_loop.py)
RETRY_INTERVAL=1800    # seconds between failed-account retries (default 30m)
MAX_RETRIES=6          # max retries per UTC day
```

### `xphere_state.json` format (optional)

If present, the bot only processes accounts listed here:

```json
{
  "accounts": {
    "acc01": {"onboarded": true, "x_connected": true},
    "acc02": {"onboarded": true, "x_connected": true}
  }
}
```

If the file doesn't exist, the bot automatically processes every `acc*.session` in the `sessions/` folder.

---

## Running

**One-shot** (exit after all accounts processed):
```bash
python xphere_daily.py
```

**Looping daemon** (runs forever, auto-retries failures, sleeps to next UTC day):
```bash
python xphere_daily_loop.py
```

Example output:
```
=== XPHERE DAILY CHECK-IN: 26 accounts ===
acc01    ✓ +24 pts total (streak 2)
acc02    ~ already checked in today
acc03    ✗ session unauthorized
…
=== DONE: 25 new check-ins | 1 already | 0 failed ===
```

Loop-specific log (`xphere_daily_loop.log`):
```
=== XPHERE DAILY LOOP — 26 accounts | retry 30m x6 ===
  acc01 +2 (streak 2)
  acc02 already
  …
pass clean: 26 new, 0 already — sleep 9h50m
```

Full results are logged to `xphere_checkin_log.jsonl` (one-shot) or `xphere_daily_loop.jsonl` (loop).

### Scheduling (optional)

If you use the **looping** script, no scheduler is needed — it runs forever.

If you prefer the **one-shot** script, schedule it daily:

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

**systemd (loop as a service):**
```ini
# /etc/systemd/system/xphere.service
[Unit]
Description=Xphere daily check-in loop
After=network-online.target

[Service]
WorkingDirectory=/opt/xphere-daily
ExecStart=/usr/bin/python3 xphere_daily_loop.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now xphere
journalctl -u xphere -f
```

---

## Initial Account Setup (outside this bot)

Before an account can check in, it must be **onboarded** through the Xphere mini app:

1. Open [t.me/Xphere_CommunityBot](https://t.me/Xphere_CommunityBot) → `/start`
2. Tap **Play** → follow the onboarding (agree, connect X, enter an EVM wallet)
3. Complete the one-time missions (Join TG, Follow X, etc.)

Onboarding + X connection automation lives in a **separate repo** (private) since it involves X account credentials. This repo only covers the **daily check-in**, which is repeatable and safe to share.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `session unauthorized` | Session file corrupted/expired | Re-login that session |
| `HTTP 401` from backend | Supabase anon key changed | Update `SUPABASE_ANON_KEY` in `.env` |
| Empty `initData` | Bot refused RequestWebView | Retry, or the session is blocked by the bot |
| `WinError 10061/1231` | Network flap / ISP DNS | Retry in a few minutes |
| Check-in keeps saying `already` | UTC day hasn't rolled over | Check-in resets at **00:00 UTC** |

---

## Security

- **`.session` files = full Telegram account credentials.** Never commit or share them.
- `api_id`/`api_hash` can be shared with a team, but ideally keep them in `.env`.
- This script stores **no passwords or tokens** — everything lives in the encrypted Telethon session file.
- The Supabase URL + anon key are **hardcoded** in the script — they are the **public infrastructure of the Xphere mini app** (exposed to every client, shared by all players). They are not our credentials and not secrets. Zero config needed for Supabase.

---

## License

MIT — use wisely, at your own risk.
