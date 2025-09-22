import asyncio
import os
from main import SessionLocal, init_system_state, SystemState, Product
from main import bulk_scan, process_pending_items

SLEEP_SECONDS = int(os.getenv("SCHEDULER_SLEEP_SECONDS", "300"))  # default 5 minutes
BATCH_MIN_PENDING = int(os.getenv("BATCH_MIN_PENDING", "1"))     # if queue empty, auto-scan

async def run_once():
    db = SessionLocal()
    try:
        state = db.query(SystemState).first() or init_system_state(db)
        if state.is_paused:
            print("--- WORKER: System paused. Skipping this cycle.")
            return

        pending = db.query(Product).filter(Product.status.in_(["pending", "failed"])).count()
        print(f"--- WORKER: Pending/Failed in queue: {pending}")

        if pending < BATCH_MIN_PENDING:
            # Auto-scan to refill queue
            counts = await bulk_scan(db)
            print(f"--- WORKER: Auto-scan complete. New queued -> products: {counts['new_products']}, collections: {counts['new_collections']}")
            pending = db.query(Product).filter(Product.status.in_(["pending", "failed"])).count()

        if pending > 0:
            await process_pending_items(db)
        else:
            print("--- WORKER: Nothing to process this cycle.")

    finally:
        db.close()

async def loop():
    while True:
        print("--- WORKER: Cycle start ---")
        await run_once()
        print(f"--- WORKER: Sleeping {SLEEP_SECONDS}s ---")
        await asyncio.sleep(SLEEP_SECONDS)

if __name__ == "__main__":
    asyncio.run(loop())
