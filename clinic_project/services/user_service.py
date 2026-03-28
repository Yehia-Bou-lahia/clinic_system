import uuid
import logging
from typing import Optional, Dict, Any
import phonenumbers
from phonenumbers import NumberParseException

from database.connection import db
from database.queries.user_repository import UserRepository
from core.policy_engine import policy_engine
from core.event_bus import EventBus
from core.exceptions import (
    DuplicateEmailError,
    PermissionDenied,
    RoleNotFoundError,
    AuthenticationError
)

logger = logging.getLogger(__name__)

ALLOWED_COUNTRY_CODES = ['SA', 'AE', 'QA', 'KW', 'OM', 'BH']

class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.event_bus = EventBus()

    # ========================================
    # دوال مساعدة خاصة
    # ========================================
    @staticmethod
    def _validate_email(email: str) -> None:
        if not email or '@' not in email or '.' not in email.split('@')[-1]:
            raise ValueError("Invalid email format")

    @staticmethod
    def _validate_password(password: str) -> None:
        if not password:
            raise ValueError("Password cannot be empty")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one digit")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?/~`" for c in password):
            raise ValueError("Password must contain at least one special character (e.g., !@#$%^&*)")

    @staticmethod
    def _validate_phone(phone_number: str) -> None:
        if not phone_number:
            # إذا كان رقم الهاتف إلزامياً، ارفع خطأ؛ وإذا كان اختيارياً، يمكن السماح
            raise ValueError("Phone number is required")
        try:
            parsed = phonenumbers.parse(phone_number, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Invalid phone number")
            country_code = phonenumbers.region_code_for_number(parsed)
            if country_code not in ALLOWED_COUNTRY_CODES:
                allowed_str = ', '.join(ALLOWED_COUNTRY_CODES)
                raise ValueError(f"Phone number must be from one of these countries: {allowed_str}")
        except NumberParseException:
            raise ValueError("Invalid phone number format. Use international format (e.g., +966512345678)")

    @staticmethod
    def _get_role_id(role_name: str) -> uuid.UUID:
        with db.get_cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
            row = cursor.fetchone()
            if not row:
                raise RoleNotFoundError(f"Role '{role_name}' not found")
            return row['id']

    # ========================================
    # الطرق العامة
    # ========================================
    def register(
        self,
        email: str,
        password: str,
        full_name: str,
        phone_number: str,
        role_name: str
    ) -> Dict[str, Any]:
        self._validate_email(email)
        self._validate_password(password)
        self._validate_phone(phone_number)
        if not full_name or not full_name.strip():
            raise ValueError("Full name is required")

        role_id = self._get_role_id(role_name)

        try:
            user = self.user_repo.create_user(email, password, full_name, phone_number, role_id)
        except DuplicateEmailError as e:
            logger.warning(f"Registration failed: {e}")
            raise

        self.event_bus.publish('user.registered', {
            'user_id': user['id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role_name': role_name
        })
        logger.info(f"User {user['id']} registered with role '{role_name}'")
        return user

    def login(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        if not email or not password:
            logger.info("Login attempt with empty credentials")
            return None

        user = self.user_repo.authenticate_user(email, password)
        if user:
            self.event_bus.publish('user.logged_in', {
                'user_id': user['id'],
                'email': email,
            })
            logger.info(f"User {user['id']} logged in")
            return user
        else:
            logger.info(f"Failed login attempt for {email}")
            return None

    def get_profile(self, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        return self.user_repo.get_user_by_id(user_id)

    def update_profile(self, user_id: uuid.UUID, **fields) -> Dict[str, Any]:
        context = {'resource': {'user_id': user_id}}
        policy_engine.enforce(user_id, 'update', 'user_profile', context)

        allowed_fields = {'full_name', 'phone_number'}
        update_data = {}

        for key, value in fields.items():
            if key not in allowed_fields:
                raise ValueError(f"Invalid field: {key}")
            if key == 'phone_number':
                self._validate_phone(value)
            elif key == 'full_name' and (not value or not value.strip()):
                raise ValueError("Full name cannot be empty")
            update_data[key] = value

        if not update_data:
            return self.get_profile(user_id)

        updated = self.user_repo.update_user(user_id, **update_data)

        self.event_bus.publish('user.profile_updated', {
            'user_id': user_id,
            'updated_fields': list(update_data.keys()),
        })
        logger.info(f"User {user_id} profile updated")
        return updated