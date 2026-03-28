# database/queries/user_repository.py
from typing import Any, Dict, Optional
import uuid
import bcrypt
from psycopg2 import IntegrityError
from core.exceptions import DatabaseError, DuplicateEmailError, UserNotFoundError
from database.connection import db

# ثابت لحماية هجمات التوقيت (dummy hash)
_DUMMY_HASH = bcrypt.hashpw(b"dummy_password", bcrypt.gensalt(rounds=12))

class UserRepository:
    @staticmethod
    def create_user(email: str, password: str, full_name: str, phone_number: str, role_id: uuid.UUID) -> Dict[str, Any]:
        """إنشاء مستخدم جديد مع تشفير كلمة المرور."""
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

        query = """
        INSERT INTO users (id, email, password_hash, full_name, phone_number, role_id)
        VALUES (gen_random_uuid(), %s, %s, %s, %s, %s)
        RETURNING id, email, full_name, phone_number, role_id, created_at;
        """
        with db.get_cursor() as cursor:
            try:
                cursor.execute(query, (email, password_hash, full_name, phone_number, role_id))
                user = cursor.fetchone()
                if not user:
                    raise DatabaseError("Failed to create user.")
                return user
            except IntegrityError:
                raise DuplicateEmailError("Email already exists.")

    @staticmethod
    def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        """جلب المستخدم بالبريد (بدون password_hash)."""
        query = """
        SELECT 
            u.id, u.email, u.full_name, u.phone_number,
            u.role_id, u.is_active, u.created_at, u.last_login,
            r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (email,))
            return cursor.fetchone()

    @staticmethod
    def get_user_for_auth(email: str) -> Optional[Dict[str, Any]]:
        """جلب المستخدم للمصادقة (مع password_hash)."""
        query = """
        SELECT 
            u.id, u.email, u.password_hash, u.full_name, u.phone_number,
            u.role_id, u.is_active, u.created_at, u.last_login,
            r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (email,))
            return cursor.fetchone()

    @staticmethod
    def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
        """مصادقة المستخدم مع حماية Timing Attack."""
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT u.id, u.email, u.password_hash, u.full_name,
                       u.is_active, r.name as role_name
                FROM users u
                JOIN roles r ON u.role_id = r.id
                WHERE u.email = %s
            """, (email,))
            user = cursor.fetchone()

            if not user:
                # تأخير ثابت (لا توجد معلومات)
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)
                return None

            if not user['is_active']:
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)
                return None

            is_valid = bcrypt.checkpw(
                password.encode(),
                user['password_hash'].encode()
            )

            if not is_valid:
                return None

            # تحديث last_login (نفس المعاملة)
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                (user['id'],)
            )

            return {
                'id': user['id'],
                'email': user['email'],
                'full_name': user['full_name'],
                'role_name': user['role_name'],
            }

    @staticmethod
    def get_user_by_id(user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """جلب المستخدم بواسطة المعرف (بدون password_hash)."""
        query = """
        SELECT
            u.id, u.email, u.full_name, u.phone_number, u.role_id, u.is_active,
            r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.id = %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            return cursor.fetchone()

    @staticmethod
    def update_user(user_id: uuid.UUID, **fields) -> Dict[str, Any]:
        """تحديث بيانات المستخدم (full_name, phone_number)."""
        allowed = {'full_name', 'phone_number'}
        set_clauses = []
        values = []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Invalid field: {key}")
            set_clauses.append(f"{key} = %s")
            values.append(value)

        if not set_clauses:
            return UserRepository.get_user_by_id(user_id)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(user_id)

        query = f"""
            UPDATE users
            SET {', '.join(set_clauses)}
            WHERE id = %s
            RETURNING id, email, full_name, phone_number, role_id, created_at, updated_at
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, values)
            updated = cursor.fetchone()
            if not updated:
                raise UserNotFoundError(f"User {user_id} not found")
            return updated

    @staticmethod
    def update_password(user_id: uuid.UUID, new_password: str) -> Dict[str, Any]:
        """تحديث كلمة مرور المستخدم مع تشفير جديد."""
        salt = bcrypt.gensalt(rounds=12)
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')  # تم إزالة الفاصلة

        query = """
            UPDATE users
            SET password_hash = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, email, full_name, phone_number, role_id, created_at, updated_at
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (password_hash, user_id))
            updated = cursor.fetchone()
            if not updated:
                raise UserNotFoundError(f"User {user_id} not found")
            return updated