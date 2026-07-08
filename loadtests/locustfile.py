"""Locust load test for LiveBoard API.

Tasks (weighted):
  - POST /scores  (10x) — the hot path
  - GET /top      (3x)  — leaderboard reads
  - GET /rank     (1x)  — individual rank queries

Run:
  locust -f loadtests/locustfile.py --host=http://localhost:8000

Then open http://localhost:8089, set users=100, ramp to 500.
"""

import os
import random

from locust import HttpUser, between, task

# Load pre-created user IDs
IDS_FILE = os.path.join(os.path.dirname(__file__), "user_ids.txt")
try:
    with open(IDS_FILE) as f:
        USER_IDS = [line.strip() for line in f if line.strip()]
except FileNotFoundError:
    raise RuntimeError(
        "user_ids.txt not found. Run 'python loadtests/setup_load_test.py' first."
    )

LB_ID = "load_test_lb"


class LeaderboardUser(HttpUser):
    """Simulates a player interacting with the leaderboard."""

    wait_time = between(0.01, 0.05)  # 20–100 req/sec per simulated user

    def on_start(self):
        """Each Locust user picks a random pre-created user ID."""
        self.user_id = random.choice(USER_IDS)

    @task(10)
    def update_score(self):
        """POST score update — the primary hot-path operation."""
        self.client.post(
            f"/leaderboards/{LB_ID}/scores",
            json={
                "user_id": self.user_id,
                "delta": round(random.uniform(1, 100), 2),
            },
            name="/leaderboards/[lb]/scores",
        )

    @task(3)
    def get_top(self):
        """GET top leaderboard — tests Redis ZREVRANGE."""
        segment = random.choice(["all_time", "daily", "weekly"])
        self.client.get(
            f"/leaderboards/{LB_ID}/top?segment={segment}&limit=50",
            name="/leaderboards/[lb]/top",
        )

    @task(1)
    def get_my_rank(self):
        """GET individual rank + surrounding users."""
        self.client.get(
            f"/leaderboards/{LB_ID}/rank/{self.user_id}",
            name="/leaderboards/[lb]/rank/[uid]",
        )
