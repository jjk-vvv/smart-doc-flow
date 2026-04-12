import asyncio
import asyncpg
import os

async def check_connection():
    # Try 127.0.0.1 to avoid IPv6 issues
    host = "127.0.0.1"
    port = 5433
    db = "intelligent_insight_system"
    
    candidates = [
        {"user": "postgres", "password": "", "label": "Empty Password", "db": db},
        {"user": "postgres", "password": "postgres", "label": "Password 'postgres'", "db": db},
        {"user": "postgres", "password": "", "label": "Empty Password (Default DB)", "db": "postgres"},
    ]
    
    print(f"--- Testing Connection to {host}:{port} ---")
    
    for cand in candidates:
        target_db = cand['db']
        dsn = f"postgresql://{cand['user']}:{cand['password']}@{host}:{port}/{target_db}"
        print(f"\nTrying: {cand['label']} (DB: {target_db})...")
        try:
            # Try without SSL first (common for local dev)
            print("  Attempt 1: SSL=disable")
            conn = await asyncpg.connect(dsn, ssl='disable', timeout=5)
            print(f"✅ SUCCESS! Connected to {target_db} (SSL=disable).")
            await conn.close()
            break
        except Exception as e:
             print(f"  ❌ Failed (SSL=disable): {str(e)}")

        try:
            # Try with default SSL
            print("  Attempt 2: Default SSL")
            conn = await asyncpg.connect(dsn, timeout=5)
            print(f"✅ SUCCESS! Connected to {target_db} (Default SSL).")
            await conn.close()
            break
        except Exception as e:
            print(f"  ❌ Failed (Default SSL): {str(e)}")

    # Try to list databases to find the correct name
    print("\n--- Listing Databases ---")
    try:
        sys_dsn = f"postgresql://postgres:@{host}:{port}/postgres"
        conn = await asyncpg.connect(sys_dsn, ssl='disable')
        rows = await conn.fetch("SELECT datname FROM pg_database;")
        print("Available Databases:")
        found = False
        for row in rows:
            print(f" - {row['datname']}")
            if row['datname'] == db:
                found = True
            elif row['datname'].lower() == db.lower():
                print(f"   (Did you mean '{row['datname']}'?)")
        await conn.close()
        
        if found:
            print(f"\nTarget database '{db}' exists.")
        else:
            print(f"\nTarget database '{db}' NOT found in list.")
            
    except Exception as e:
        print(f"❌ Failed to list databases: {str(e)}")

if __name__ == "__main__":
    asyncio.run(check_connection())
