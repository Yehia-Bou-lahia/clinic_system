import uuid
from typing import Dict, Any, Optional, List
from database.connection import db

class FeatureRepository:
    @staticmethod
    def get_feature(code: str) -> Optional[Dict[str, Any]]:
        """جلب ميزة واحدة بواسطة الكود."""
        query = """
            SELECT id, code, name, description, is_enabled, created_at, updated_at
            FROM features
            WHERE code = %s
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (code,))
            return cursor.fetchone()

    @staticmethod
    def get_all_features() -> List[Dict[str, Any]]:
        """جلب جميع الميزات (للاستخدام الإداري)."""
        query = """
            SELECT id, code, name, description, is_enabled, created_at, updated_at
            FROM features
            ORDER BY code
        """
        with db.get_cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    @staticmethod
    def enable_feature(code: str) -> bool:
        """تفعيل ميزة."""
        query = """
            UPDATE features
            SET is_enabled = true, updated_at = CURRENT_TIMESTAMP
            WHERE code = %s
            RETURNING id
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (code,))
            return cursor.fetchone() is not None

    @staticmethod
    def disable_feature(code: str) -> bool:
        """إيقاف ميزة."""
        query = """
            UPDATE features
            SET is_enabled = false, updated_at = CURRENT_TIMESTAMP
            WHERE code = %s
            RETURNING id
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (code,))
            return cursor.fetchone() is not None

    @staticmethod
    def create_feature(code: str, name: str, description: Optional[str] = None, is_enabled: bool = False) -> Dict[str, Any]:
        """إنشاء ميزة جديدة."""
        query = """
            INSERT INTO features (id, code, name, description, is_enabled)
            VALUES (gen_random_uuid(), %s, %s, %s, %s)
            RETURNING id, code, name, description, is_enabled, created_at, updated_at
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (code, name, description, is_enabled))
            return cursor.fetchone()