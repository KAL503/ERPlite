"""
QERP - Database Connection Module
Provides PostgreSQL connection pooling and utility functions.
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import os
from contextlib import contextmanager

# Connection pool
connection_pool = None


def init_db_pool():
    """Initialize the database connection pool."""
    global connection_pool

    if connection_pool is None:
        try:
            connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,   # minconn
                20,  # maxconn
                host=os.getenv('DB_HOST', 'localhost'),
                port=os.getenv('DB_PORT', '5432'),
                database=os.getenv('DB_NAME', 'qerp'),
                user=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', '')
            )
            print("Database connection pool created successfully.")
        except Exception as e:
            print(f"Error creating connection pool: {e}")
            raise


def close_db_pool():
    """Close all database connections in the pool."""
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        print("Database connection pool closed.")


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Automatically returns the connection to the pool when done.

    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users")
                results = cur.fetchall()
    """
    conn = connection_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        connection_pool.putconn(conn)


@contextmanager
def get_db_cursor(commit=True):
    """
    Context manager for a database cursor using RealDictCursor.
    Returns results as dictionaries for easier access.

    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            # Access as: user['username'], user['full_name'], etc.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()


def execute_query(query, params=None, fetch_one=False, fetch_all=False):
    """
    Execute a SQL query and return results.

    Args:
        query:     SQL query string
        params:    Query parameters (tuple or dict), optional
        fetch_one: If True, return a single row as a dict
        fetch_all: If True, return all rows as a list of dicts

    Returns:
        Single row dict, list of dicts, or None
    """
    with get_db_cursor() as cur:
        cur.execute(query, params)

        if fetch_one:
            return cur.fetchone()
        elif fetch_all:
            return cur.fetchall()
        return None
