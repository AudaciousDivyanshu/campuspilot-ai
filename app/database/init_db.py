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
            location TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 1
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
            purpose TEXT DEFAULT '',
            rejection_reason TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            location TEXT,
            is_enabled INTEGER NOT NULL DEFAULT 1
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
            purpose TEXT DEFAULT '',
            rejection_reason TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES discussion_rooms (room_id) ON DELETE CASCADE
        );
        """
    )

    # Student profiles table for dynamic identity management
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS student_profiles (
            user_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            department TEXT DEFAULT 'Engineering & Technology',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # User accounts table for local SQLite authentication and role management
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_accounts (
            user_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            display_name TEXT,
            account_type TEXT NOT NULL DEFAULT 'Student',
            student_id TEXT,
            university TEXT DEFAULT 'Lovely Professional University',
            department TEXT DEFAULT 'Computer Science & Engineering',
            avatar TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Leave requests table (Student submission & Automated Acceptance policy)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leave_requests (
            leave_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            student_name TEXT NOT NULL,
            student_email TEXT NOT NULL,
            leave_type TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Approved (Auto-Accepted)',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


SAMPLE_PROFILES = [
    {
        "user_id": "student_arnav_001",
        "full_name": "Arnav",
        "email": "arnav@campus.edu",
        "department": "Computer Science & Engineering",
    },
    {
        "user_id": "student_rahul_002",
        "full_name": "Rahul",
        "email": "rahul@campus.edu",
        "department": "AI & Data Science",
    },
]


def seed_sample_student_profiles(conn: sqlite3.Connection) -> int:
    """Insert initial sample demonstration student profiles safely without creating duplicates."""
    cursor = conn.cursor()
    inserted_count = 0
    for prof in SAMPLE_PROFILES:
        cursor.execute(
            """
            INSERT OR IGNORE INTO student_profiles (user_id, full_name, email, department)
            VALUES (?, ?, ?, ?);
            """,
            (prof["user_id"], prof["full_name"], prof["email"], prof["department"]),
        )
        if cursor.rowcount > 0:
            inserted_count += 1

    # Seed isolated sample reservations for Arnav and Rahul
    cursor.execute(
        """
        INSERT OR IGNORE INTO bookings (booking_id, student_id, student_name, lab_id, booking_date, start_time, end_time, status)
        VALUES (101, 'student_arnav_001', 'Arnav', 1, '2026-11-20', '10:00', '12:00', 'confirmed');
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO room_bookings (booking_id, student_id, student_name, room_id, booking_date, start_time, end_time, status)
        VALUES (201, 'student_rahul_002', 'Rahul', 2, '2026-11-20', '14:00', '16:00', 'confirmed');
        """
    )

    return inserted_count




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


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Safely migrate SQLite database schema non-destructively to support approval workflows."""
    cursor = conn.cursor()

    # Migrate bookings table
    cursor.execute("PRAGMA table_info(bookings);")
    booking_cols = [row["name"] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
    if "purpose" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN purpose TEXT DEFAULT '';")
    if "rejection_reason" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN rejection_reason TEXT DEFAULT '';")
    if "created_at" not in booking_cols:
        cursor.execute("ALTER TABLE bookings ADD COLUMN created_at TEXT DEFAULT '';")

    # Migrate room_bookings table
    cursor.execute("PRAGMA table_info(room_bookings);")
    room_cols = [row["name"] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
    if "purpose" not in room_cols:
        cursor.execute("ALTER TABLE room_bookings ADD COLUMN purpose TEXT DEFAULT '';")
    if "rejection_reason" not in room_cols:
        cursor.execute("ALTER TABLE room_bookings ADD COLUMN rejection_reason TEXT DEFAULT '';")
    if "created_at" not in room_cols:
        cursor.execute("ALTER TABLE room_bookings ADD COLUMN created_at TEXT DEFAULT '';")

    # Migrate labs table
    cursor.execute("PRAGMA table_info(labs);")
    lab_cols = [row["name"] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
    if "is_enabled" not in lab_cols:
        cursor.execute("ALTER TABLE labs ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1;")

    # Migrate discussion_rooms table
    cursor.execute("PRAGMA table_info(discussion_rooms);")
    disc_cols = [row["name"] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
    if "is_enabled" not in disc_cols:
        cursor.execute("ALTER TABLE discussion_rooms ADD COLUMN is_enabled INTEGER NOT NULL DEFAULT 1;")


def init_db(db_path: str | Path | None = None) -> Path:
    """Initialize the SQLite database, ensuring tables and initial seed data exist.

    Safe to run repeatedly without overwriting existing data or duplicating entries.
    """
    target_path = get_db_path(db_path)
    with get_db_context(target_path) as conn:
        create_tables(conn)
        migrate_schema(conn)
        seed_sample_laboratories(conn)
        seed_sample_discussion_rooms(conn)
        seed_sample_student_profiles(conn)

    return target_path


if __name__ == "__main__":
    db_file = init_db()
    print(f"Database initialized successfully at: {db_file}")
