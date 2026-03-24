import os
from dotenv import load_dotenv
load_dotenv('.env.test')
print(f"🔍 DB_NAME from .env.test: {os.getenv('DB_NAME')}")
import pytest
from psycopg2.extras import RealDictCursor
from database.connection import db


@pytest.fixture(scope="function", autouse=True)
def clean_db():
    with db.get_cursor() as cursor:
        cursor.execute("DELETE FROM visit_reports")
        cursor.execute("DELETE FROM appointments")
        cursor.execute("DELETE FROM patient_profiles")
        cursor.execute("DELETE FROM doctor_profiles")
        cursor.execute("DELETE FROM users WHERE email NOT LIKE '%admin%'")
    yield


@pytest.fixture(scope="function")
def db_cursor():
    with db.get_connection() as conn:
        conn.autocommit = False
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
        finally:
            conn.rollback()
            cursor.close()


@pytest.fixture(scope="function")
def patient_role_id():
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM roles WHERE name = 'patient'")
        row = cursor.fetchone()
        return row['id'] if row else None


@pytest.fixture(scope="function")
def doctor_role_id():
    with db.get_cursor() as cursor:
        cursor.execute("SELECT id FROM roles WHERE name = 'doctor'")
        row = cursor.fetchone()
        return row['id'] if row else None


@pytest.fixture(scope="function")
def test_user(patient_role_id):
    with db.get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO users (id, email, password_hash, full_name, phone_number, role_id)
            VALUES (gen_random_uuid(), 'test@example.com', 'hash', 'Test User', '0555123456', %s)
            RETURNING id, email, full_name, phone_number, role_id
        """, (patient_role_id,))
        return cursor.fetchone()