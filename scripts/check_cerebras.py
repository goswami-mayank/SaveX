"""Verify Cerebras with synthetic data, without database writes or notifications."""

from datetime import date, timedelta
import sys

from dotenv import load_dotenv

from backend.llm import CerebrasProvider, make_plan, parse_items


def main():
    load_dotenv()
    today = date.today()
    provider = CerebrasProvider()
    items = parse_items("Bought milk and eggs today, both last two days, keep in the fridge.", today, provider)
    if len(items) < 2:
        raise ValueError("Expected at least two extracted grocery items")
    pantry = [
        {"name": "milk", "expiry_date": (today + timedelta(days=2)).isoformat(), "status": "active"},
        {"name": "eggs", "expiry_date": (today + timedelta(days=2)).isoformat(), "status": "active"},
    ]
    result = make_plan(pantry, today, provider)
    if len(result["meals"]) != 3:
        raise ValueError("Expected three validated meals")
    print("Cerebras extraction and validated three-meal planning succeeded.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Cerebras verification failed ({type(exc).__name__}). Check key, model access, and provider status.", file=sys.stderr)
        sys.exit(1)
