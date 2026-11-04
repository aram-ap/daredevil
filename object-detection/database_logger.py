"""
Project Daredevil - SQLite3 Database Logging Module
Handles initialisation and obstacle/YOLO event logging.

Tables
------
obstacle_logs  : raw zone-based depth readings (original pipeline)
yolo_logs      : per-detection YOLO events (class, confidence, zone, depth)
"""

import time
import sqlite3

DB_NAME = "daredevil_object_log.db"


def init_db(db_path=DB_NAME):
    """Create (or open) the SQLite database and ensure all tables exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Original zone-based depth table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS obstacle_logs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp           REAL    NOT NULL,
            zone                TEXT    NOT NULL,
            nearest_distance_m  REAL    NOT NULL
        )
    ''')

    # YOLO detection table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS yolo_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   REAL    NOT NULL,
            label       TEXT    NOT NULL,
            confidence  REAL    NOT NULL,
            zone        TEXT    NOT NULL,
            distance_m  REAL            -- NULL when no valid depth reading
        )
    ''')

    conn.commit()
    return conn


def log_obstacle_event(conn, zone, distance_m):
    """Log a zone-level obstacle reading (original depth pipeline)."""
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO obstacle_logs (timestamp, zone, nearest_distance_m) VALUES (?,?,?)',
        (time.time(), zone, round(float(distance_m), 3))
    )
    conn.commit()


def log_yolo_event(conn, label: str, confidence: float, zone: str, distance_m):
    """Log a single YOLO detection with its depth reading and zone assignment."""
    cursor = conn.cursor()
    dist = round(float(distance_m), 3) if distance_m is not None else None
    cursor.execute(
        '''INSERT INTO yolo_logs (timestamp, label, confidence, zone, distance_m)
           VALUES (?, ?, ?, ?, ?)''',
        (time.time(), label, round(float(confidence), 4), zone, dist)
    )
    conn.commit()
