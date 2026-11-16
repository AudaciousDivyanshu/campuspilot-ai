"""Database initialization module for CampusPilot AI.

Creates the SQLite tables if they do not exist and populates initial sample laboratories
and library discussion rooms without duplicating records on repeated runs.
"""

from pathlib import Path
import sqlite3

from app.database.connection import get_db_context, get_db_path

SAMPLE_LABS = [
    {
        "lab_name": "Computer Lab 1",
        "capacity": 40,
        "location": "Block A - First Floor",
    },
    {
        "lab_name": "AI Lab",
        "capacity": 30,
        "location": "Block B - Second Floor",
    },
    {
        "lab_name": "Networking Lab",
        "capacity": 35,
        "location": "Block A - Second Floor",
    },
]

SAMPLE_ROOMS = [
    {
        "room_name": "Discussion Room 1",
        "capacity": 4,
        "location": "Library 1st Floor - East Wing",
    },
    {
        "room_name": "Discussion Room 2",
        "capacity": 6,
        "location": "Library 2nd Floor - West Wing",
    },
    {
        "room_name": "Discussion Room 3",
        "capacity": 8,
        "location": "Library 3rd Floor - Quiet Zone",
    },
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Create labs, bookings, discussion_rooms, and room_bookings tables if they do not exist."""
    cursor = conn.cursor()

    # Laboratory tables
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS labs (
            lab_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_name TEXT NOT NULL UNIQUE,
            capacity INTEGER NOT NULL,
            location TEXT
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            lab_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            FOREIGN KEY (lab_id) REFERENCES labs (lab_id) ON DELETE CASCADE
        );
        """
    )

    # Library discussion room tables
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS discussion_rooms (
            room_id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_name TEXT NOT NULL UNIQUE,
            capacity INTEGER NOT NULL,
            location TEXT
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS room_bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            room_id INTEGER NOT NULL,
            booking_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            FOREIGN KEY (room_id) REFERENCES discussion_rooms (room_id) ON DELETE CASCADE
        );
        """
    )


def seed_sample_laboratories(conn: sqlite3.Connection) -> int:
    """Insert initial sample laboratories safely without creating duplicates.

    Returns the number of new laboratories inserted.
    """
    cursor = conn.cursor()
    inserted_count = 0

    for lab in SAMPLE_LABS:
        cursor.execute(
            """
            INSERT OR IGNORE INTO labs (lab_name, capacity, location)
            VALUES (?, ?, ?);
            """,
            (lab["lab_name"], lab["capacity"], lab["location"]),
        )
        if cursor.rowcount > 0:
            inserted_count += 1

    return inserted_count


def seed_sample_discussion_rooms(conn: sqlite3.Connection) -> int:
    """Insert initial sample discussion rooms safely without creating duplicates.

    Returns the number of new discussion rooms inserted.
    """
    cursor = conn.cursor()
    inserted_count = 0

    for room in SAMPLE_ROOMS:
        cursor.execute(
            """
            INSERT OR IGNORE INTO discussion_rooms (room_name, capacity, location)
            VALUES (?, ?, ?);
            """,
            (room["room_name"], room["capacity"], room["location"]),
        )
        if cursor.rowcount > 0:
            inserted_count += 1

    return inserted_count


def init_db(db_path: str | Path | None = None) -> Path:
    """Initialize the SQLite database, ensuring tables and initial seed data exist.

    Safe to run repeatedly without overwriting existing data or duplicating entries.
    """
    target_path = get_db_path(db_path)
    with get_db_context(target_path) as conn:
        create_tables(conn)
        seed_sample_laboratories(conn)
        seed_sample_discussion_rooms(conn)

    return target_path


if __name__ == "__main__":
    db_file = init_db()
    print(f"Database initialized successfully at: {db_file}")
