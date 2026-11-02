#!/usr/bin/env python3
"""Xphere CommunityBot — daily check-in untuk seluruh akun Telegram fleet.

Flow per akun:
  1. Muat session Telethon (folder SESSION_DIR, file accNN.session)
  2. Minta initData ke @Xphere_CommunityBot via RequestWebView (tanpa browser)
  3. POST {action: "checkin", initData} ke Supabase Edge Function
  4. Catat hasil ke xphere_checkin_log.jsonl + summary di stdout

Butuh:
  - Python 3.11+, `pip install telethon`
  - Folder berisi file sesi Telethon bernama acc01.session .. accNN.session
    (sudah login/authorized). Lihat .env.example untuk variabel yang diisi.

Tidak menyimpan kredensial apapun di repo: session + mapping dipasang lewat
.env / folder lokal. Supabase anon key adalah kunci publik milik mini app.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from telethon import TelegramClient, functions

# ---------------------------------------------------------------- config (.env)
def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is not None:
        return v
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return default


SESSION_DIR = _env("SESSION_DIR", "./sessions")          # folder berisi accNN.session
STATE_FILE = _env("STATE_FILE", "./xphere_state.json")   # mapping + status onboarded
LOG_FILE = _env("LOG_FILE", "./xphere_checkin_log.jsonl")
TG_API_ID = int(_env("TG_API_ID", "1"))                  # bebas utk session yang sudah ada
TG_API_HASH = _env("TG_API_HASH", "x" * 32)
BOT_USERNAME = _env("BOT_USERNAME", "Xphere_CommunityBot")
WEBAPP_URL = _env("WEBAPP_URL", "https://x-phere.com")
SB_URL = _env("SUPABASE_URL", "https://ltodfynoaozgcaobwcgo.supabase.co")
SB_FN = "dynamic-handler"

# Supabase anon key mini app (publik, dibundel di index.html mini app).
# Kalau project owner ganti key, update di sini.
SB_ANON_KEY = _env(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0b2RmeW5vYW96Z2Nhb2J3Y2dvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjM0MzY0MDAsImV4cCI6MjAzOTAxMjQwMH0.qVGRd8RRBJfTBlPGCNLJcQFRkG0Rr2SjmWkRiTCxCak"
)

DELAY_BETWEEN = float(_env("DELAY_BETWEEN", "3"))         # detik jeda antar akun
TIMEOUT_S = 25


def call_backend(body: dict) -> dict:
    req = urllib.request.Request(
        f"{SB_URL}/functions/v1/{SB_FN}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SB_ANON_KEY}",
            "apikey": SB_ANON_KEY,
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "reason": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:80]}"}


async def get_initdata(session_path: str) -> str:
    """Minta initData Telegram WebApp untuk 1 session (tanpa browser)."""
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy()) \
        if sys.platform == "win32" else None
    client = TelegramClient(session_path, api_id=TG_API_ID, api_hash=TG_API_HASH)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("session unauthorized — login ulang session ini")
        entity = await client.get_entity(BOT_USERNAME)
        res = await client(functions.messages.RequestWebViewRequest(
            peer=entity, bot=entity, platform="android",
            from_bot_menu=True, url=WEBAPP_URL,
        ))
        frag = res.url.split("#")[1]
        return dict(urllib.parse.parse_qsl(frag)).get("tgWebAppData", "")
    finally:
        await client.disconnect()


def load_accounts() -> list[dict]:
    """Baca daftar akun dari state file. Format: {"accounts": {"acc01": {...}}}.
    Minimal tiap entry punya onboarded/x_connected biar bisa difilter."""
    if not Path(STATE_FILE).exists():
        # fallback: scan folder sessions
        out = []
        for f in sorted(Path(SESSION_DIR).glob("acc*.session")):
            out.append({"tg": f.stem})
        return out
    st = json.loads(Path(STATE_FILE).read_text(encoding="utf-8"))
    accs = st.get("accounts") or {}
    return [{"tg": tg, **(v or {})} for tg, v in sorted(accs.items())]


def main() -> int:
    accounts = load_accounts()
    if not accounts:
        print(f"tidak ada akun — cek STATE_FILE ({STATE_FILE}) atau SESSION_DIR ({SESSION_DIR})")
        return 1
    print(f"=== XPHERE DAILY CHECK-IN: {len(accounts)} akun ===")

    ok = already = fail = 0
    for a in accounts:
        tg = a["tg"]
        sess = str(Path(SESSION_DIR) / f"{tg}.session")
        if not Path(sess).exists():
            print(f"{tg:<8} SKIP — session file tidak ada")
            fail += 1
            continue
        try:
            init = asyncio.run(get_initdata(sess))
        except Exception as e:  # noqa: BLE001
            print(f"{tg:<8} ERR initdata: {type(e).__name__}: {str(e)[:80]}")
            fail += 1
            time.sleep(DELAY_BETWEEN)
            continue
        if not init:
            print(f"{tg:<8} ERR initdata kosong")
            fail += 1
            time.sleep(DELAY_BETWEEN)
            continue

        r = call_backend({"action": "checkin", "initData": init})
        if r.get("ok"):
            print(f"{tg:<8} ✓ +{r.get('points', '?')} pts total (streak {r.get('streak', '?')})")
            ok += 1
        elif r.get("reason") == "already":
            print(f"{tg:<8} ~ sudah checkin hari ini")
            already += 1
        else:
            print(f"{tg:<8} ✗ {r.get('reason', '?')}")
            fail += 1

        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"tg": tg, "res": r, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
                                ensure_ascii=False) + "\n")
        time.sleep(DELAY_BETWEEN)

    print(f"\n=== SELESAI: {ok} checkin baru | {already} sudah | {fail} gagal ===")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
