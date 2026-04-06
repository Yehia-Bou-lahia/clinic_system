import json
from typing import Any, Optional
from database.connection import db

class SettingsRepository:
    @staticmethod
    def get(key: str) -> Optional[str]:
        """جلب قيمة إعداد كسلسلة نصية"""
        query = "SELECT value FROM settings WHERE key = %s"
        with db.get_cursor() as cursor:
            cursor.execute(query, (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
        
    @staticmethod
    def get_int(key: str, default: int = 0) -> int:
        """جلب قيمة إعداد وتحويلها الى (int)"""
        val = SettingsRepository.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            return default

    @staticmethod
    def get_bool(key: str, default: bool = False) -> bool:
        """جلب قيمة إعداد وتحويلها الى (bool)"""
        val = SettingsRepository.get(key)
        if val is None:
            return default
        return val.lower() in ('true', '1', 'yes', 'on')

    @staticmethod
    def set(key: str, value: str) -> None:
        """تعيين قيمة إعداد (للإستخدام الإداري.)"""
        query = """
            INSERT INTO settings (key, value, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (key, value))