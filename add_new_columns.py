#!/usr/bin/env python3
"""
Script to add new columns to the users table in SQLite database.
"""
import sqlite3
import os
from pathlib import Path

def add_columns_to_users_table():
    """Add username and transcription_count columns to users table"""
    db_path = Path(__file__).parent / "users.db"

    if not db_path.exists():
        print(f"Database file {db_path} not found!")
        return

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check if columns already exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'username' not in columns:
            print("Adding username column...")
            cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
        else:
            print("username column already exists")

        if 'transcription_count' not in columns:
            print("Adding transcription_count column...")
            cursor.execute("ALTER TABLE users ADD COLUMN transcription_count INTEGER DEFAULT 0")
        else:
            print("transcription_count column already exists")

        conn.commit()
        print("Database updated successfully!")

        # Show current table structure
        cursor.execute("PRAGMA table_info(users)")
        print("\nCurrent users table structure:")
        for column in cursor.fetchall():
            print(f"  {column[1]}: {column[2]} {'PRIMARY KEY' if column[5] else ''}")

    except Exception as e:
        print(f"Error updating database: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_columns_to_users_table()
