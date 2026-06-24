#!/usr/bin/env python3
"""Automates load testing preparation for ISSUE-088.

Retrieves active users and approved/open fields from the configured Supabase
database and generates JWT tokens for the users. Outputs the results to text files
suitable for consumption by k6.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Align sys.path to backend directory to allow app imports
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import dotenv

# Load environment variables from the backend directory before importing app config
DOTENV_PATH = BACKEND_DIR / ".env"
if DOTENV_PATH.exists():
    dotenv.load_dotenv(DOTENV_PATH)
else:
    print(f"Warning: .env file not found at {DOTENV_PATH}. Falling back to system environment variables.")

from app.auth.jwt import create_access_token
from app.db.supabase import get_supabase_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automatically prepare JWT tokens and approved field IDs for load testing."
    )
    parser.add_argument(
        "--tokens-out",
        type=Path,
        default=BACKEND_DIR / "load_tests" / "tokens.txt",
        help="Path where the JWT tokens text file will be saved.",
    )
    parser.add_argument(
        "--fields-out",
        type=Path,
        default=BACKEND_DIR / "load_tests" / "field_ids.txt",
        help="Path where the field IDs text file will be saved.",
    )
    parser.add_argument(
        "--limit-users",
        type=int,
        default=50,
        help="Maximum number of active users to generate JWTs for.",
    )
    parser.add_argument(
        "--limit-fields",
        type=int,
        default=50,
        help="Maximum number of approved fields to retrieve.",
    )
    args = parser.parse_args()

    # 1. Initialize Supabase client
    try:
        supabase = get_supabase_client()
    except Exception as e:
        print(f"Error: Failed to initialize Supabase client: {e}")
        sys.exit(1)

    print("Connecting to Supabase and querying data...")

    # 2. Query approved, verified, open fields
    try:
        fields_res = (
            supabase.table("fields")
            .select("id")
            .eq("verified", True)
            .eq("approval_status", "approved")
            .eq("status", "open")
            .limit(args.limit_fields)
            .execute()
        )
        fields = fields_res.data or []
    except Exception as e:
        print(f"Error: Failed to retrieve fields from database: {e}")
        sys.exit(1)

    # 3. Query active users
    try:
        users_res = (
            supabase.table("users")
            .select("id, email")
            .eq("status", "active")
            .limit(args.limit_users)
            .execute()
        )
        users = users_res.data or []
    except Exception as e:
        print(f"Error: Failed to retrieve users from database: {e}")
        sys.exit(1)

    print(f"Found {len(fields)} approved, open field(s).")
    print(f"Found {len(users)} active user(s).")

    if not fields:
        print("Warning: No approved, open fields were found. field_ids.txt will be empty.")
    if not users:
        print("Warning: No active users were found. tokens.txt will be empty.")

    # 4. Generate JWT tokens
    tokens = []
    for user in users:
        user_id = user.get("id")
        email = user.get("email")
        if user_id and email:
            try:
                token = create_access_token(user_id, email)
                tokens.append(token)
            except Exception as e:
                print(f"Warning: Failed to generate token for user {user_id}: {e}")

    # 5. Write to files
    try:
        args.tokens_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.tokens_out, "w", encoding="utf-8") as f:
            for token in tokens:
                f.write(f"{token}\n")
        print(f"Successfully generated {len(tokens)} JWT token(s) and wrote to {args.tokens_out}")
    except Exception as e:
        print(f"Error: Failed to write tokens file: {e}")
        sys.exit(1)

    try:
        args.fields_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.fields_out, "w", encoding="utf-8") as f:
            for field in fields:
                field_id = field.get("id")
                if field_id:
                    f.write(f"{field_id}\n")
        print(f"Successfully wrote {len(fields)} field ID(s) to {args.fields_out}")
    except Exception as e:
        print(f"Error: Failed to write field IDs file: {e}")
        sys.exit(1)

    print("\nLoad test data preparation completed successfully!")


if __name__ == "__main__":
    main()
