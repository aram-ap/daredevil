"""
Project Daredevil - SQLite3 Database Logging Module 
Handles Initialization and obstacle event logging
"""

import time
import sqlite3

DB_NAME = "daredevil_object_log.db"

def init_db(db_path=DB_NAME):
    # Initialize SQLite database table for recording obstacle events
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOTE EXISTS obstacle_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            zone TEXT NOT NULL,
            nearest_distance_m REAL NOT NULL
        )
    ''')
    conn.commit()
    return conn

def log_obstacle_event(conn, zone, distance_m):
    # Logs the timestamp, zone, and distance readings to the SQLite database
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO obstacle_logs (timestamp, zone, nearest_distance_m) VALUES (?,?,?)',
        (time.time(), zone, round(float(distance_m), 3))
    )
    conn.commit()