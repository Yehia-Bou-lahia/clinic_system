import pytest
from datetime import date
from database.queries.user_repository import UserRepository
from database.queries.patient_repository import PatientRepository

def test_create_patient(db_cursor, patient_role_id):
    user = UserRepository.create_user(
        email="zohra.benali@example.com",
        password="pass",
        full_name="Zohra Benali",
        phone_number="0666123456",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user['id'],
        date_of_birth=date(1985, 3, 12),
        blood_type="O+",
        city="Algiers"
    )
    assert patient is not None
    assert patient['user_id'] == user['id']

def test_get_patient_by_user_id(db_cursor, patient_role_id):
    user = UserRepository.create_user(
        email="mohamed.belkacem@example.com",
        password="pass",
        full_name="Mohamed Belkacem",
        phone_number="0777123456",
        role_id=patient_role_id
    )
    created = PatientRepository.create_patient_profile(
        user_id=user['id'],
        date_of_birth=date(1990, 7, 22),
        blood_type="A-"
    )
    fetched = PatientRepository.get_patient_by_user_id(user['id'])
    assert fetched is not None
    assert fetched['id'] == created['id']

def test_update_patient(db_cursor, patient_role_id):
    user = UserRepository.create_user(
        email="amira.khelladi@example.com",
        password="pass",
        full_name="Amira Khelladi",
        phone_number="0555987654",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user['id'],
        date_of_birth=date(2000, 1, 1),
        blood_type="B+"
    )
    updated = PatientRepository.update_patient_profile(
        patient['id'],
        city="Oran",
        blood_type="AB-"
    )
    assert updated['city'] == "Oran"
    assert updated['blood_type'] == "AB-"

def test_soft_delete_and_restore(db_cursor, patient_role_id):
    user = UserRepository.create_user(
        email="salah.djebbar@example.com",
        password="pass",
        full_name="Salah Djebbar",
        phone_number="0666777888",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user['id'],
        date_of_birth=date(1975, 12, 5)
    )
    # Soft delete
    deleted = PatientRepository.soft_delete_patient_profile(patient['id'])
    assert deleted is True
    # Normal get should return None
    after_delete = PatientRepository.get_patient_by_id(patient['id'])
    assert after_delete is None
    # Restore
    restored = PatientRepository.restore_patient_profile(patient['id'])
    assert restored is True
    after_restore = PatientRepository.get_patient_by_id(patient['id'])
    assert after_restore is not None