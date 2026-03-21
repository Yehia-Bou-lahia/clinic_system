import uuid
from typing import List, Optional, Dict, Any
from psycopg2 import IntegrityError
from database.connection import db
from core.exceptions import (
    DatabaseError,
    DoctorNotFoundError,
    DuplicateLicenseError,
    UserNotFoundError
)
ALLOWED_UPDATE_FIELDS = {
    'specialty', 'subspecialty', 'consultation_fee',
    'years_of_experience', 'is_active'
}

_SELECT_DOCTOR_FIELDS = """
    SELECT id, user_id, specialty, sub_specialty,
        license_number, consultation_fee, years_of_experience, 
        is_active, created_at, updated_at
    FROM doctor_profiles
"""
class DoctorRepository:
    @staticmethod
    def create_doctor_profile(
        user_id: uuid.UUID,
        specialty: str,
        license_number: str,
        consultation_fee: float,        
        subspecialty: Optional[str] = None,
        years_experience: int = 0,
        is_active: bool = True     
    ) -> Dict[str, Any]:
        if not user_id:
            raise ValueError("user_id is required")
        if not specialty:
            raise ValueError("specialty is required")
        if not license_number:
            raise ValueError("license_number is required")
        if consultation_fee < 0:
            raise ValueError("consultation_fee cannot be negative")
        if years_experience < 0:
            raise ValueError("years_experience cannot be negative")
        query = """ 
            INSERT INTO doctor_profiles(id, user_id, specialty, sub_specialty,
                license_number, consultation_fee, years_experience,
                is_active, deleted_at)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, NULL)
            RETURNING id, user_id, specialty, sub_specialty, 
                license_number, consultation_fee, years_experience, 
                is_active, created_at, updated_at;
            """
        with db.get_cursor() as cursor:
            try:
                cursor.execute(query, (
                    user_id, specialty, subspecialty, 
                    license_number, consultation_fee,
                    years_experience, is_active
                ))
                result = cursor.fetchone()
                if not result:
                    raise DatabaseError("Failed to create doctor profile")
                return result
            except IntegrityError as e:
                if 'foreign key constraint' in str(e):
                    raise UserNotFoundError(f"User with id {user_id} does not exist")
                if 'license_number' in str(e):
                    raise DuplicateLicenseError(f"Doctor with license number {license_number} already exists")
                raise
    
    @staticmethod
    def get_doctor_by_user_id(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        query = _SELECT_DOCTOR_FIELDS + " WHERE user_id = %s AND deleted_at IS NULL;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            if not result:
                raise DoctorNotFoundError(f"Doctor with user_id {user_id} not found")
            return result

    @staticmethod
    def get_doctor_by_id(doctor_id):
        query = _SELECT_DOCTOR_FIELDS + " WHERE id = %s AND deleted_at IS NULL;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (doctor_id,))
            result = cursor.fetchone()
            if not result:
                raise DoctorNotFoundError(f"Doctor with id {doctor_id} not found")
            return result
    
    @staticmethod 
    def update_doctor_profile(
        doctor_id: uuid.UUID,
        **fields: Any
    ) -> Optional[Dict[str, Any]]:
        if not fields:
            return DoctorRepository.get_doctor_by_id(doctor_id)
        set_clauses = []
        values = []
        for key, value in fields.items():
            if key not in ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(doctor_id)

        query = f"""
            UPDATE doctor_profiles
            SET {','.join(set_clauses)}
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id, user_id, specialty, sub_specialty,
                license_number, consultation_fee, years_experience,
                is_active, created_at, updated_at;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, values)
            updated = cursor.fetchone()
            if not updated:
                raise DoctorNotFoundError(f"Doctor profile with id {doctor_id} not found or already deleted")
            return updated
        
    @staticmethod 
    def soft_delete_doctor_profile(doctor_id: uuid.UUID) -> bool:
        query = """
            UPDATE doctor_profiles
            SET deleted_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL
            RETURNING id;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (doctor_id,))
            deleted = cursor.fetchone()
            if not deleted:
                raise DoctorNotFoundError(f"Doctor profile with id {doctor_id} not found or already deleted")
            return deleted is not None
    
    @staticmethod
    def restore_doctor_profile(doctor_id: uuid.UUID) -> bool:
        query = """
            UPDATE doctor_profiles
            SET deleted_at = NULL
            WHERE id = %s AND deleted_at IS NOT NULL
            RETURNING id;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (doctor_id,))
            restored = cursor.fetchone()
            if not restored:
                raise DoctorNotFoundError(f"Doctor profile with id {doctor_id} not found or not deleted")
            return restored is not None
    
    @staticmethod
    def list_active_doctors(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        query = _SELECT_DOCTOR_FIELDS + " WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT %s OFFSET %s;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()
    
    @staticmethod
    def list_all_doctors(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        query = _SELECT_DOCTOR_FIELDS + " ORDER BY created_at DESC LIMIT %s OFFSET %s;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()
    
    @staticmethod
    def list_deleted_doctors(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        query = _SELECT_DOCTOR_FIELDS + " WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT %s OFFSET %s;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()
    