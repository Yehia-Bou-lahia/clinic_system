import uuid
import json
from typing import Dict, Any, Optional
from database.connection import db

class AuditRepository:
    @staticmethod
    def create_audit_log(
        user_id: Optional[uuid.UUID],
        action: str,
        model_name: str,
        object_id: Optional[uuid.UUID] = None,
        object_repr: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        إنشاء سجل تدقيق.
        - changes: dict سيتم تحويله إلى JSONB.
        """
        query = """
            INSERT INTO audit_log (
                id, user_id, action, model_name, object_id,
                object_repr, changes, ip_address, user_agent
            )
            VALUES (
                gen_random_uuid(), %s, %s, %s, %s,
                %s, %s, %s, %s
            )
            RETURNING id, user_id, action, model_name, object_id,
                      object_repr, changes, ip_address, user_agent, timestamp
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (
                user_id, action, model_name, object_id,
                object_repr, json.dumps(changes) if changes else None,
                ip_address, user_agent
            ))
            return cursor.fetchone()