import asyncio
import os
import httpx
import time

# Configure how often the worker loops and how it decides to scan
SLEEP_SECONDS = int(os.getenv("SCHEDULER_SLEEP_SECONDS", "300"))  # Default 5 minutes
SCAN_WHEN_PENDING_LT = int(os.getenv("BATCH_MIN_PENDING", "10"))  # Auto-scan if pending items are less than 10
API_BASE = (os.getenv("WORKER_API_BASE") or "").rstrip("/")

if not API_BASE:
    raise SystemExit("FATAL: WORKER_API_BASE environment variable is not set. Please set it to your backend API's public URL.")

async def call_api(method: str, path: str):
    """Helper to make API calls to the backend service."""
    url = f"{API_BASE}{path}"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.request(method, url)
            response.raise_for_status() # Raises an exception for 4xx/5xx responses
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return response.text
        except httpx.RequestError as e:
            print(f"--- WORKER: HTTP Request failed: {e.request.method} {e.request.url} - {e}")
            return None
        except httpx.HTTPStatusError as e:
            print(f"--- WORKER: HTTP Status error: {e.response.status_code} - {e.response.text}")
            return None

async def run_once():
    """Performs one cycle of the worker's logic."""
    # 1. Get the current state of the system from the dashboard API
    print("--- WORKER: Fetching current system state from dashboard...")
    dashboard_data = await call_api("GET", "/api/dashboard")
    if not dashboard_data:
        print("--- WORKER: Could not fetch dashboard data. Skipping this cycle.")
        return

    is_paused = dashboard_data.get("system", {}).get("is_paused", False)
    pending_count = (dashboard_data.get("stats", {}).get("products", {}).get("pending", 0)) + \
                    (dashboard_data.get("stats", {}).get("collections", {}).get("pending", 0))

    print(f"--- WORKER: State check -> Pending: {pending_count}, Paused: {is_paused}")

    if is_paused:
        print("--- WORKER: System is paused. Skipping this cycle.")
        return

    # 2. If the queue is low, automatically scan to refill it
    if pending_count < SCAN_WHEN_PENDING_LT:
        print(f"--- WORKER: Pending count ({pending_count}) is below threshold ({SCAN_WHEN_PENDING_LT}). Triggering auto-scan...")
        scan_result = await call_api("POST", "/api/scan")
        print(f"--- WORKER: Auto-scan result: {scan_result}")
        
        # --- LOGIC FIX: Re-check the paused state AFTER the scan ---
        # A large scan might have triggered the auto-pause.
        dashboard_data_after_scan = await call_api("GET", "/api/dashboard")
        if dashboard_data_after_scan and dashboard_data_after_scan.get("system", {}).get("is_paused", False):
            print("--- WORKER: Scan triggered auto-pause. Ending this cycle to respect paused state.")
            return

    # 3. If there are items in the queue (and system is not paused), process a batch
    # Re-fetch the pending count in case the scan just added new items
    dashboard_data_after_scan = await call_api("GET", "/api/dashboard")
    final_pending_count = (dashboard_data_after_scan.get("stats", {}).get("products", {}).get("pending", 0)) + \
                         (dashboard_data_after_scan.get("stats", {}).get("collections", {}).get("pending", 0))
    
    if final_pending_count > 0:
        print(f"--- WORKER: {final_pending_count} items in queue. Triggering processing batch...")
        process_result = await call_api("POST", "/api/process-queue")
        print(f"--- WORKER: Processing triggered: {process_result}")
    else:
        print("--- WORKER: No pending items to process this cycle.")

async def main_loop():
    """The main infinite loop for the worker."""
    while True:
        print(f"\n--- WORKER: Starting cycle at {time.strftime('%Y-%m-%d %H:%M:%S')} ---")
        await run_once()
        print(f"--- WORKER: Cycle finished. Sleeping for {SLEEP_SECONDS} seconds. ---")
        await asyncio.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    asyncio.run(main_loop())
