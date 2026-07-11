import httpx
import random
import time
import asyncio

API_URL = "https://liveboard-1arv.onrender.com"
LB_ID = "coding_contest"

users_to_create = [
    {"username": "alex_storm", "display_name": "Alex Storm", "region": "US-EAST"},
    {"username": "maya_fire", "display_name": "Maya Fire", "region": "EU-WEST"},
    {"username": "kai_zen", "display_name": "Kai Zen", "region": "ASIA"},
    {"username": "nova_star", "display_name": "Nova Star", "region": "US-WEST"},
    {"username": "zara_light", "display_name": "Zara Light", "region": "EU-WEST"},
    {"username": "leo_runner", "display_name": "Leo Runner", "region": "US-EAST"},
    {"username": "chloe_hacker", "display_name": "Chloe Hacker", "region": "US-WEST"},
    {"username": "david_script", "display_name": "David Script", "region": "ASIA"},
    {"username": "emma_code", "display_name": "Emma Code", "region": "EU-EAST"},
    {"username": "ryan_dev", "display_name": "Ryan Dev", "region": "US-CENTRAL"},
]

async def seed_data():
    async with httpx.AsyncClient() as client:
        print("Checking leaderboard...")
        # Create leaderboard if doesn't exist
        await client.post(f"{API_URL}/leaderboards", json={"id": LB_ID, "name": "Live Coding Contest"})

        print("Fetching/Creating users...")
        user_ids = []
        for u in users_to_create:
            resp = await client.post(f"{API_URL}/users", json=u)
            if resp.status_code in [200, 201]:
                user_ids.append(resp.json()["id"])
            else:
                print(f"Failed to fetch {u['username']}: {resp.status_code}")

        if not user_ids:
            print("No users found. Aborting.")
            return

        print(f"Got {len(user_ids)} users. Simulating scores...")
        
        # Give everyone a base score
        for uid in user_ids:
            await client.post(f"{API_URL}/scores/{LB_ID}/scores", json={
                "user_id": uid,
                "delta": random.randint(100, 500)
            })
            
        # Simulate some rapid live changes
        for _ in range(15):
            uid = random.choice(user_ids)
            points = random.randint(10, 100)
            await client.post(f"{API_URL}/scores/{LB_ID}/scores", json={
                "user_id": uid,
                "delta": points
            })
            print(f"Added {points} points to user {uid}")
            await asyncio.sleep(0.5)

        print("Data seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
