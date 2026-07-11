import os
import httpx
import random
import asyncio

API_URL = os.getenv("API_URL", "https://liveboard-1arv.onrender.com")
LB_ID = "coding_contest"

async def run_bot():
    print(f"Starting Bot Simulator against {API_URL}")
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Ensure leaderboard exists
        try:
            await client.post(f"{API_URL}/leaderboards", json={"id": LB_ID, "name": "Live Coding Contest"})
        except Exception as e:
            print(f"Error ensuring leaderboard: {e}")

        while True:
            try:
                # Fetch all users
                resp = await client.get(f"{API_URL}/users")
                if resp.status_code == 200:
                    users = resp.json()
                    if users:
                        user = random.choice(users)
                        points = random.randint(10, 150)
                        
                        score_resp = await client.post(f"{API_URL}/scores/{LB_ID}/scores", json={
                            "user_id": user["id"],
                            "delta": points
                        })
                        
                        if score_resp.status_code in [200, 201]:
                            print(f"[BOT] Added {points} pts to {user['username']}")
                        else:
                            print(f"[BOT] Failed to add points: {score_resp.status_code}")
                    else:
                        print("[BOT] No users found, waiting...")
                else:
                    print(f"[BOT] Failed to fetch users: {resp.status_code}")
                    
            except Exception as e:
                print(f"[BOT] Error during loop: {e}")
                
            # Wait a bit before the next random score
            await asyncio.sleep(random.uniform(1.0, 3.0))

if __name__ == "__main__":
    asyncio.run(run_bot())
