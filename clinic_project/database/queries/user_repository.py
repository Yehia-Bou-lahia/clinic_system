import bcrypt
from psycopg2 import IntegrityError
from core.exceptions import DatabaseError, DuplicateEmailError
from database.connection import db

_DUMMY_HASH = bcrypt.hashpw(b"dummy_password", bcrypt.gensalt(rounds=12))

class UserRepository:
    @staticmethod
    def create_user(email, password, full_name, phone_number, role_id):
        
        salt = bcrypt.gensalt(rounds = 12)
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
    def get_user_by_email(email):
        query = """
        SELECT 
            u.id, u.email, u.password_hash, u.full_name, u.phone_number, 
            u.role_id, u.is_active, u.created_at, u.last_login,r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (email,))
            return cursor.fetchone()
    
    @staticmethod
    def authenticate_user(email: str, password: str):
        query = """
        SELECT u.id, u.email, u.password_hash, u.full_name,
               u.is_active, r.name as role_name
        FROM users u
        JOIN roles r ON u.role_id = r.id
        WHERE u.email = %s
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (email,))
            user = cursor.fetchone()

            if not user:
                # bcrypt يشتغل حتى لو المستخدم غير موجود
                # نفس الوقت دائماً ← المهاجم لا يرى فرقاً
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)
                return None

            if not user['is_active']:
                bcrypt.checkpw(password.encode(), _DUMMY_HASH)
                return None  # نفس الوقت أيضاً

            is_valid = bcrypt.checkpw(
                password.encode(),
                user['password_hash'].encode()
            )

            if not is_valid:
                return None

            # نفس الـ cursor = نفس الـ transaction
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
    def get_user_by_id(user_id):
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
    