import uuid
import logging
from typing import Dict, Any, Optional, List
from database.connection import db

logger = logging.getLogger(__name__)


class NotificationRepository:
    """التعامل مع جداول notifications و notification_preferences."""

    @staticmethod
    def create_notification(
        user_id: uuid.UUID,
        type: str,          # 'email', 'push', 'sms'
        title: str,
        message: str,
        related_to: Optional[str] = None,
        related_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        """
        إنشاء سجل إشعار جديد.
        """
        query = """
            INSERT INTO notifications (id, user_id, type, title, message, related_to, related_id)
            VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s)
            RETURNING id, user_id, type, title, message, related_to, related_id, created_at, is_read;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id, type, title, message, related_to, related_id))
            return cursor.fetchone()

    @staticmethod
    def get_preferences(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        جلب تفضيلات الإشعارات لمستخدم معين.
        تعيد None إذا لم توجد تفضيلات.
        """
        query = """
            SELECT email_enabled, push_enabled, sms_enabled,
                   quiet_hours_start, quiet_hours_end, notify_before_appointment
            FROM notification_preferences
            WHERE user_id = %s
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            return cursor.fetchone()

    # دوال إضافية (اختيارية) يمكن استخدامها لاحقاً
    @staticmethod
    def get_notifications_by_user(
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        only_unread: bool = False,
    ) -> List[Dict[str, Any]]:
        """جلب قائمة إشعارات المستخدم."""
        query = """
            SELECT id, user_id, type, title, message, related_to, related_id,
                   created_at, is_read, read_at
            FROM notifications
            WHERE user_id = %s
        """
        params = [user_id]
        if only_unread:
            query += " AND is_read = false"
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def mark_as_read(notification_id: uuid.UUID) -> bool:
        """تعليم إشعار كمقروء."""
        query = """
            UPDATE notifications
            SET is_read = true, read_at = CURRENT_TIMESTAMP
            WHERE id = %s AND is_read = false
            RETURNING id
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (notification_id,))
            return cursor.fetchone() is not None

    @staticmethod
    def update_preferences(user_id: uuid.UUID, **prefs) -> bool:
        """
        تحديث تفضيلات الإشعارات (upsert).
        """
        # التحقق من وجود تفضيلات مسبقاً
        existing = NotificationRepository.get_preferences(user_id)
        if existing:
            # تحديث
            set_clauses = []
            values = []
            allowed = {
                'email_enabled', 'push_enabled', 'sms_enabled',
                'quiet_hours_start', 'quiet_hours_end', 'notify_before_appointment'
            }
            for key, value in prefs.items():
                if key not in allowed:
                    raise ValueError(f"Invalid preference field: {key}")
                set_clauses.append(f"{key} = %s")
                values.append(value)
            if not set_clauses:
                return True
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            values.append(user_id)
            query = f"""
                UPDATE notification_preferences
                SET {', '.join(set_clauses)}
                WHERE user_id = %s
                RETURNING user_id
            """
            with db.get_cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchone() is not None
        else:
            # إدراج
            allowed = {
                'email_enabled', 'push_enabled', 'sms_enabled',
                'quiet_hours_start', 'quiet_hours_end', 'notify_before_appointment'
            }
            columns = ['user_id']
            placeholders = ['%s']
            values = [user_id]
            for key, value in prefs.items():
                if key not in allowed:
                    raise ValueError(f"Invalid preference field: {key}")
                columns.append(key)
                placeholders.append('%s')
                values.append(value)
            query = f"""
                INSERT INTO notification_preferences ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING user_id
            """
            with db.get_cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchone() is not None