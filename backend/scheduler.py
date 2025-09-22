import asyncio
import os
import httpx
import time

# Configure how often the worker loops and how it decides to scan
SLEEP_SECONDS = int(os.getenv("SCHEDULER_SLEEP_SECONDS", "300"))  # 5 minutes
SCAN_WHEN_PENDING_LT = int(os.getenv("BATCH_MIN_PENDING", "1"))  # auto-scan if pending < this
API_BASE = (os.getenv("WORKER_API_BASE") or "").rstrip("/")

if not API_BASE:
    raise SystemExit("WORKER_API_BASE is not set. Set it to your backend API public URL, e.g. https://backend-api.up.railway.app")

async def call(method: str, path: str):
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.request(method, url)
        r.raise_for_status()
        if r.headers.get("content-type","").startswith("application/json"):
            return r.json()
        return r.text

async def run_once():
    # 1) Read dashboard to know pending count
    try:
        dash = await call("GET", "/api/dashboard")
    except Exception as e:
        print(f"--- WORKER: dashboard fetch failed: {e}")
        return

    pending = (dash.get("stats", {}).get("products", {}).get("pending") or 0) + \
              (dash.get("stats", {}).get("collections", {}).get("pending") or 0)

    is_paused = dash.get("system", {}).get("is_paused")
    print(f"--- WORKER: pending={pending}, paused={is_paused}")

    if is_paused:
        print("--- WORKER: System paused. Skipping.")
        return

    # 2) Auto-scan if queue looks low
    if pending < SCAN_WHEN_PENDING_LT:
        print("--- WORKER: Queue low. Triggering /api/scan ...")
        try:
            res = await call("POST", "/api/scan")
            print(f"--- WORKER: scan result: {res}")
        except Exception as e:
            print(f"--- WORKER: scan failed: {e}")

    # 3) Trigger a processing batch
    print("--- WORKER: Triggering /api/process-queue ...")
    try:
        res = await call("POST", "/api/process-queue")
        print(f"--- WORKER: process-queue: {res}")
    except Exception as e:
        print(f"--- WORKER: process-queue failed: {e}")

async def loop():
    while True:
        print(f"--- WORKER: cycle start @ {time.strftime('%X')}")
        await run_once()
        print(f"--- WORKER: sleeping {SLEEP_SECONDS}s")
        await asyncio.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    asyncio.run(loop())
