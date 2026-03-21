import uuid
from datetime import date
from typing import Optional, Dict, Any, List
from psycopg2 import IntegrityError
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
    def create_patient_profile(
        user_id: uuid.UUID, 
        date_of_birth: date, 
        blood_type: Optional[str] = None,
        emergency_contact_name: Optional[str] = None,
        emergency_contact: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        chronic_diseases: Optional[str] = None,
        allergies: Optional[str] = None
    ) -> Dict[str, Any]:
        if not user_id:
            raise ValueError("user_id is required")
        if not date_of_birth:
            raise ValueError("date_of_birth is required")
        if date_of_birth > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        
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
        with db.get_cursor() as cursor:
            try:
                cursor.execute(query, (
                    user_id, date_of_birth, blood_type,
                    emergency_contact_name, emergency_contact,
                    address, city, chronic_diseases, allergies
                ))
                result = cursor.fetchone()
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
    def get_patient_by_user_id(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at
            FROM patient_profiles
            WHERE user_id = %s AND deleted_at IS NULL;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            if not result:
                raise PatientNotFoundError(f"No patient profile found for user_id {user_id}")
            return result
    
    @staticmethod
    def get_patient_by_id(patient_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at
            FROM patient_profiles
            WHERE id = %s AND deleted_at IS NULL;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (patient_id,))
            result = cursor.fetchone()
            if not result:
                raise PatientNotFoundError(f"No patient profile found for patient_id {patient_id}")
            return result
    
    @staticmethod
    def update_patient_profile(
        patient_id: uuid.UUID,
        **fields: Any
    ) -> Optional[Dict[str, Any]]:
        
        if not fields:
            return PatientRepository.get_patient_by_id(patient_id)

        # بناء جملة SET مع placeholders
        set_clauses = []
        values = []
        for key, value in fields.items():
            if key not in ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            set_clauses.append(f"{key} = %s")
            values.append(value)

        # إضافة updated_at
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(patient_id)  # لـ WHERE

        query = f"""
        UPDATE patient_profiles
        SET {', '.join(set_clauses)}
        WHERE id = %s AND deleted_at IS NULL
        RETURNING id, user_id, date_of_birth, blood_type,
                  emergency_contact, emergency_contact_name,
                  address, city, chronic_diseases, allergies,
                  created_at, updated_at;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, values)
            updated = cursor.fetchone()
            if not updated:
                raise PatientNotFoundError(f"Patient profile with id {patient_id} not found or already deleted")
            return updated

    @staticmethod
    def soft_delete_patient_profile(patient_id: uuid.UUID) -> bool:
        query = """
            UPDATE patient_profiles
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (patient_id,))
            deleted = cursor.fetchone()
            if not deleted:
                raise PatientNotFoundError(f"Patient profile with id {patient_id} not found or already deleted")
            return True
        
    @staticmethod
    def list_active_patients(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at
            FROM patient_profiles
            WHERE deleted_at IS NULL
            ORDER BY created_at DESC LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()

    @staticmethod
    def list_deleted_patients(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
            SELECT id, user_id, date_of_birth, blood_type,
                emergency_contact_name, emergency_contact,
                address, city, chronic_diseases, allergies, 
                created_at, updated_at, deleted_at
            FROM patient_profiles
            WHERE deleted_at IS NOT NULL
            ORDER BY deleted_at DESC LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()