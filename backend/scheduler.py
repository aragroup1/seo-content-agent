import asyncio
from main import process_pending_items, SessionLocal, init_system_state, SystemState

async def run():
    """
    This is the dedicated function that the Railway Cron Job will execute.
    It's a simplified, direct version of the processing logic.
    """
    print("--- AUTONOMOUS SCHEDULER: STARTING RUN ---")
    db = SessionLocal()
    try:
        # Check if the system is paused before doing anything
        state = db.query(SystemState).first()
        if not state:
            state = init_system_state(db)
        
        if state.is_paused:
            print("--- AUTONOMOUS SCHEDULER: System is paused. Skipping run. ---")
            return

        print("--- AUTONOMOUS SCHEDULER: System is active. Starting processing... ---")
        # Directly call the main processing function from your main.py
        await process_pending_items(db)

        print("--- AUTONOMOUS SCHEDULER: Processing batch complete. ---")

    except Exception as e:
        print(f"--- AUTONOMOUS SCHEDULER: An error occurred: {e} ---")
    finally:
        db.close()
        print("--- AUTONOMOUS SCHEDULER: RUN FINISHED ---")


if __name__ == "__main__":
    print("Running scheduler script manually...")
    asyncio.run(run())
