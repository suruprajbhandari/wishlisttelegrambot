import sqlite3
from typing import Tuple, Optional

DB_NAME = "wishlist.db"

def init_db():
    """Initializes the database and creates the wishlist table if it doesn't exist."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                price REAL NOT NULL
            )
        ''')
        conn.commit()

def add_item(item_name: str, price: float):
    """Inserts a new item into the wishlist table."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO wishlist (item_name, price) VALUES (?, ?)",
            (item_name, price)
        )
        conn.commit()

def get_total_cost() -> float:
    """Queries the database for the sum of all prices."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(price) FROM wishlist")
        result = cursor.fetchone()
        return result[0] if result[0] is not None else 0.0
