import pytest
from database.queries.user_repository import UserRepository
from database.queries.doctor_repository import DoctorRepository
from core.exceptions import DuplicateLicenseError

def test_create_doctor(db_cursor, doctor_role_id):
    user = UserRepository.create_user(
        email="karim.daoud@example.com",
        password="pass",
        full_name="Karim Daoud",
        phone_number="0888888888",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user['id'],
        specialty="Cardiology",
        license_number="LIC-123",
        consultation_fee=300
    )
    assert doctor is not None
    assert doctor['user_id'] == user['id']

def test_duplicate_license(db_cursor, doctor_role_id):
    user1 = UserRepository.create_user(
        email="ahmed.mansouri@example.com",
        password="pass",
        full_name="Ahmed Mansouri",
        phone_number="0999999999",
        role_id=doctor_role_id
    )
    DoctorRepository.create_doctor_profile(
        user_id=user1['id'],
        specialty="Dermatology",
        license_number="LIC-DUP",
        consultation_fee=400
    )
    user2 = UserRepository.create_user(
        email="nadia.belkacem@example.com",
        password="pass",
        full_name="Nadia Belkacem",
        phone_number="0101010101",
        role_id=doctor_role_id
    )
    with pytest.raises(DuplicateLicenseError):
        DoctorRepository.create_doctor_profile(
            user_id=user2['id'],
            specialty="Radiology",
            license_number="LIC-DUP",
            consultation_fee=500
        )

def test_update_doctor(db_cursor, doctor_role_id):
    user = UserRepository.create_user(
        email="slimane.hadji@example.com",
        password="pass",
        full_name="Slimane Hadji",
        phone_number="0222222222",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user['id'],
        specialty="Pediatrics",
        license_number="LIC-456",
        consultation_fee=250
    )
    updated = DoctorRepository.update_doctor_profile(
        doctor['id'],
        consultation_fee=300,
        years_experience=5
    )
    assert updated['consultation_fee'] == 300
    assert updated['years_experience'] == 5