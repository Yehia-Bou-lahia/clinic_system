import os
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


class DatabasePool:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabasePool, cls).__new__(cls) ## create a new instance of the class singleton
            cls._instance._initialize_pool()
        return cls._instance
    
    def _initialize_pool(self):
        try:
            self._pool = pool.SimpleConnectionPool(
                1, 20,
                database = os.getenv('DB_NAME'),
                user = os.getenv('DB_USER'),
                password = os.getenv('DB_PASSWORD'),
                host = os.getenv('DB_HOST'),
                port = os.getenv('DB_PORT','5432'),
                sslmode = os.getenv('DB_SSLMODE', 'disable')
            )
            print("Database connection pool created successfully.")
        except Exception as e:
            print(f"Error creating database connection pool: {e}")
            raise
        
    @contextmanager
    def get_connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(self, cursor_factory = RealDictCursor):
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory = cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()
    
db = DatabasePool()