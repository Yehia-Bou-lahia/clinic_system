# database/queries/patient_repository.py
import uuid
from datetime import date
from typing import Optional, Dict, Any, List
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor
from database.connection import db
from core.exceptions import (
    DatabaseError,
    PatientNotFoundError,
    PatientProfileAlreadyExistsError,
    UserNotFoundError
)

ALLOWED_UPDATE_FIELDS = {
    'date_of_birth', 'blood_type', 'emergency_contact_name',
    'emergency_contact', 'address', 'city', 
    'chronic_diseases', 'allergies'
}

class PatientRepository:
    @staticmethod
    def _execute_create(cursor, user_id, date_of_birth, blood_type,
                        emergency_contact_name, emergency_contact,
                        address, city, chronic_diseases, allergies):
        query = """
            INSERT INTO patient_profiles (
                id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies,
                deleted_at
            ) VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
            RETURNING id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at;
        """
        cursor.execute(query, (
            user_id, date_of_birth, blood_type,
            emergency_contact_name, emergency_contact,
            address, city, chronic_diseases, allergies
        ))
        return cursor.fetchone()

    @staticmethod
    def create_patient_profile(
        user_id: uuid.UUID, 
        date_of_birth: date, 
        blood_type: Optional[str] = None,
        emergency_contact_name: Optional[str] = None,
        emergency_contact: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        chronic_diseases: Optional[str] = None,
        allergies: Optional[str] = None,
        conn: Optional[Any] = None,   # ← أضف هذا
    ) -> Dict[str, Any]:
        if not user_id:
            raise ValueError("user_id is required")
        if not date_of_birth:
            raise ValueError("date_of_birth is required")
        if date_of_birth > date.today():
            raise ValueError("date_of_birth cannot be in the future")

        try:
            if conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                result = PatientRepository._execute_create(
                    cursor, user_id, date_of_birth, blood_type,
                    emergency_contact_name, emergency_contact,
                    address, city, chronic_diseases, allergies
                )
            else:
                with db.get_cursor() as cursor:
                    result = PatientRepository._execute_create(
                        cursor, user_id, date_of_birth, blood_type,
                        emergency_contact_name, emergency_contact,
                        address, city, chronic_diseases, allergies
                    )
            if not result:
                raise DatabaseError("Failed to create patient profile")
            return result
        except IntegrityError as e:
            if 'foreign key constraint' in str(e):
                raise UserNotFoundError(f"User with id {user_id} does not exist")
            if 'unique constraint' in str(e):
                raise PatientProfileAlreadyExistsError(
                    f"Patient profile for user {user_id} already exists"
                )
            raise

    @staticmethod
    def get_patient_by_user_id(user_id: uuid.UUID, conn: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at
            FROM patient_profiles
            WHERE user_id = %s AND deleted_at IS NULL;
        """
        if conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, (user_id,))
            return cursor.fetchone()
        else:
            with db.get_cursor() as cursor:
                cursor.execute(query, (user_id,))
                return cursor.fetchone()

    @staticmethod
    def get_patient_by_id(patient_id: uuid.UUID, conn: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at
            FROM patient_profiles
            WHERE id = %s AND deleted_at IS NULL;
        """
        if conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, (patient_id,))
            return cursor.fetchone()
        else:
            with db.get_cursor() as cursor:
                cursor.execute(query, (patient_id,))
                return cursor.fetchone()