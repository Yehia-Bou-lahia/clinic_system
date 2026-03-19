import bcrypt
from database.connection import db

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
            cursor.execute(query, (email, password_hash, full_name, phone_number, role_id))
            user =  cursor.fetchone()
            if not user:
                raise Exception("Failed to create user.")
            return user
    
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
    def authenticate_user(email, password):
        user = UserRepository.get_user_by_email(email)
        if not user:
            return None
        # Check password
        stored_hash = user['password_hash'].encode('utf-8')
        if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
            # update last login time
            with db.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET last_login = NOW() WHERE id = %s",
                    (user['id'],)
                )
                return user
        return None
    
    @staticmethod
    def update_user(user_id):
        # update last login time
        query = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s RETURNING last_loginL;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (user_id,))
            return cursor.fetchone()
    
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
    