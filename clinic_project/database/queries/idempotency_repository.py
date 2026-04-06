import uuid
import json
from typing import Dict, Any, Optional
from database.connection import db

class IdempotencyRepository:
    @staticmethod
    def get(key: str) -> Optional[Dict[str, Any]]:
        """جلب نتيجة طلب سابق باستخدام مفتاح idempotency."""
        query = """
            SELECT response FROM idempotency_keys
            WHERE key = %s AND expires_at > CURRENT_TIMESTAMP
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (key,))
            row = cursor.fetchone()
            if row:
                return row['response']  # مخزنة كـ JSONB
            return None

    @staticmethod
    def save(key: str, response: Dict[str, Any], conn: Optional[Any] = None) -> None:
        """تخزين نتيجة طلب ناجح مع مفتاح idempotency (صلاحية 24 ساعة)."""
        query = """
            INSERT INTO idempotency_keys (key, response, expires_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP + INTERVAL '24 hours')
            ON CONFLICT (key) DO NOTHING
        """
        if conn:
            cursor = conn.cursor()
            cursor.execute(query, (key, json.dumps(response)))
        else:
            with db.get_cursor() as cursor:
                cursor.execute(query, (key, json.dumps(response)))