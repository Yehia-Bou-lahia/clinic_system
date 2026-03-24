import pytest
from database.queries.user_repository import UserRepository
from core.exceptions import DuplicateEmailError

def test_create_user(db_cursor, patient_role_id):
    user = UserRepository.create_user(
        email="karim.bensalah@example.com",
        password="secure123",
        full_name="Karim Bensalah",
        phone_number="0555123456",
        role_id=patient_role_id
    )
    assert user is not None
    assert user['email'] == "karim.bensalah@example.com"
    assert 'password_hash' not in user

def test_duplicate_email(db_cursor, patient_role_id):
    UserRepository.create_user(
        email="fatima.ouali@example.com",
        password="pass",
        full_name="Fatima Ouali",
        phone_number="0666123456",
        role_id=patient_role_id
    )
    with pytest.raises(DuplicateEmailError):
        UserRepository.create_user(
            email="fatima.ouali@example.com",
            password="other",
            full_name="Fatima Ouali",
            phone_number="0777123456",
            role_id=patient_role_id
        )

def test_authenticate_user(db_cursor, patient_role_id):
    UserRepository.create_user(
        email="rachid.mebarki@example.com",
        password="correct",
        full_name="Rachid Mebarki",
        phone_number="0777123456",
        role_id=patient_role_id
    )
    auth = UserRepository.authenticate_user("rachid.mebarki@example.com", "correct")
    assert auth is not None
    assert auth['email'] == "rachid.mebarki@example.com"

    wrong = UserRepository.authenticate_user("rachid.mebarki@example.com", "wrong")
    assert wrong is None