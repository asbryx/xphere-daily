#!/usr/bin/env python3
"""Xphere daily — check-in + daily Twitter missions (LOOPING daemon).

Run sekali, jalan terus:
  1. Pass harian semua akun: checkin (+2) + missions 1/2/3 (+3 each = +11/akun/hari)
     - m1 = comment X, m2 = like X, m3 = retweet X (server gak verify real post!)
     - m5/m6/m8 = one-time (udah kelar saat onboarding, auto-skip via "already")
  2. Gagal network/session → retry tiap 30 menit (maks 6x/hari)
  3. Semua sukses/already → tidur sampai 00:05 UTC (reset harian) → ulangi
Resume-safe: "already" di-skip otomatis.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telethon import TelegramClient, functions


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is not None:
        return v
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("\"").strip("'")
    return default


BASE = Path(__file__).resolve().parent
SESSION_DIR = Path(_env("SESSION_DIR", "./sessions"))
LOG = BASE / "xphere_daily_loop.log"
JSONL = BASE / "xphere_daily_loop.jsonl"
PAIR_FILE = BASE / "xphere_pairing_v2.json"
BOT = _env("BOT_USERNAME", "Xphere_CommunityBot")
WEBAPP_URL = _env("WEBAPP_URL", "https://x-phere.com")
SB = _env("SUPABASE_URL", "https://ltodfynoaozgcaobwcgo.supabase.co").rstrip("/")
DELAY_BETWEEN = float(_env("DELAY_BETWEEN", "4"))
RETRY_INTERVAL = int(_env("RETRY_INTERVAL", "1800"))
MAX_RETRIES = int(_env("MAX_RETRIES", "6"))

# daily missions: checkin +2, m1/m2/m3 +3 each (Twitter comment/like/retweet — click-only)
DAILY_MISSIONS = [1, 2, 3]

_h = urllib.request.urlopen(urllib.request.Request(
    "https://henrykim96.github.io/xphere-mini-app/",
    headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read().decode()
KEY = re.findall(r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", _h)[0]
FN = f"{SB}/functions/v1/dynamic-handler"


def log(msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def call(body: dict) -> dict:
    req = urllib.request.Request(FN, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KEY}",
        "apikey": KEY,
        "User-Agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {"ok": False, "reason": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {str(e)[:70]}"}


async def get_initdata(tg: str) -> str:
    client = TelegramClient(str(SESSION_DIR / tg), api_id=1, api_hash="x" * 32)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("session unauthorized")
        entity = await client.get_entity(BOT)
        res = await client(functions.messages.RequestWebViewRequest(
            peer=entity, bot=entity, platform="android",
            from_bot_menu=True, url=WEBAPP_URL))
        frag = res.url.split("#")[1]
        return dict(urllib.parse.parse_qsl(frag)).get("tgWebAppData", "")
    finally:
        await client.disconnect()


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def seconds_until_next_utc_day() -> int:
    now = datetime.now(timezone.utc)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
    return int((nxt - now).total_seconds())


def run_pass(day: str, tg_list: list[str]) -> dict:
    summary = {"day": day, "ok": [], "already": [], "fail": [], "gained": 0,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for tg in tg_list:
        gained = 0
        try:
            init = asyncio.run(get_initdata(tg))
        except Exception as e:                              # noqa: BLE001
            summary["fail"].append({"tg": tg, "err": f"initdata {type(e).__name__}: {str(e)[:60]}"})
            log(f"  {tg} initdata ERR {type(e).__name__}")
            time.sleep(DELAY_BETWEEN)
            continue
        if not init:
            summary["fail"].append({"tg": tg, "err": "initdata kosong"})
            log(f"  {tg} initdata kosong")
            time.sleep(DELAY_BETWEEN)
            continue

        u = call({"action": "load_user", "initData": init})
        before = ((u or {}).get("user") or {}).get("points") or 0

        c = call({"action": "checkin", "initData": init})
        ck = "ok" if c.get("ok") else c.get("reason", "?")

        mres = []
        for mid in DAILY_MISSIONS:
            m = call({"mission_id": mid, "initData": init})
            mres.append(f"m{mid}:{'ok' if m.get('ok') else m.get('reason', '?')}")

        u2 = call({"action": "load_user", "initData": init})
        after = ((u2 or {}).get("user") or {}).get("points") or 0
        gained = max(0, after - before)
        summary["gained"] += gained

        if all(("already" in m or "ok" in m) for m in mres) and ck in ("ok", "already"):
            summary["ok" if gained else "already"].append(tg)
            log(f"  {tg} +{gained} pts ({ck}, {' '.join(mres)})")
        else:
            summary["fail"].append({"tg": tg, "err": f"{ck} / {' '.join(mres)}"})
            log(f"  {tg} FAIL {ck} / {' '.join(mres)}")
        time.sleep(DELAY_BETWEEN)

    with JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    return summary


def main() -> int:
    if PAIR_FILE.exists():
        tg_list = sorted(json.loads(PAIR_FILE.read_text(encoding="utf-8")).keys())
    else:
        tg_list = sorted(f.stem for f in SESSION_DIR.glob("acc*.session"))
    log(f"=== XPHERE DAILY LOOP — {len(tg_list)} akun | checkin+11pts/akun | retry {RETRY_INTERVAL//60}m x{MAX_RETRIES} ===")

    retries = 0
    current_day = utc_today()
    while True:
        day = utc_today()
        if day != current_day:
            current_day = day
            retries = 0
            log(f"=== HARI BARU UTC: {day} ===")

        s = run_pass(day, tg_list)
        if not s["fail"]:
            retries = 0
            wait = seconds_until_next_utc_day()
            log(f"pass bersih: {len(s['ok'])} baru, {len(s['already'])} already, +{s['gained']} pts — tidur {wait//3600}h{(wait%3600)//60}m")
            time.sleep(wait)
            continue

        retries += 1
        if retries >= MAX_RETRIES:
            wait = seconds_until_next_utc_day()
            log(f"FAIL {len(s['fail'])} akun, retry habis ({MAX_RETRIES}x) — lanjut besok")
            time.sleep(wait)
            retries = 0
            continue
        log(f"{len(s['fail'])} gagal — retry {RETRY_INTERVAL//60}m (attempt {retries}/{MAX_RETRIES})")
        time.sleep(RETRY_INTERVAL)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nstopped by user")
        raise SystemExit(0)
