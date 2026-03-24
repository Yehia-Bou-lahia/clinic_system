import pytest
from datetime import datetime, timedelta
from database.queries.user_repository import UserRepository
from database.queries.patient_repository import PatientRepository
from database.queries.doctor_repository import DoctorRepository
from database.queries.appointment_repository import AppointmentRepository

def test_create_appointment(db_cursor, patient_role_id, doctor_role_id):
    # Patient
    user_p = UserRepository.create_user(
        email="mohamed.kaci@example.com",
        password="pass",
        full_name="Mohamed Kaci",
        phone_number="0111111111",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user_p['id'],
        date_of_birth=datetime(1990,1,1).date()
    )
    # Doctor
    user_d = UserRepository.create_user(
        email="djamila.benali@example.com",
        password="pass",
        full_name="Djamila Benali",
        phone_number="0222222222",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user_d['id'],
        specialty="General",
        license_number="LIC-APPT",
        consultation_fee=100
    )
    # Appointment
    dt = datetime.now() + timedelta(days=1)
    appointment = AppointmentRepository.create_appointment(
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        appointment_datetime=dt,
        notes="Test"
    )
    assert appointment is not None
    assert appointment['status'] == 'PENDING'

def test_cancel_appointment(db_cursor, patient_role_id, doctor_role_id):
    # Patient
    user_p = UserRepository.create_user(
        email="lynda.haddad@example.com",
        password="pass",
        full_name="Lynda Haddad",
        phone_number="0333333333",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user_p['id'],
        date_of_birth=datetime(1995,5,5).date()
    )
    # Doctor
    user_d = UserRepository.create_user(
        email="reda.ouali@example.com",
        password="pass",
        full_name="Reda Ouali",
        phone_number="0444444444",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user_d['id'],
        specialty="General",
        license_number="LIC-CANCEL",
        consultation_fee=150
    )
    dt = datetime.now() + timedelta(days=2)
    appointment = AppointmentRepository.create_appointment(
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        appointment_datetime=dt
    )
    cancelled = AppointmentRepository.cancel_appointment(
        appointment['id'],
        reason="Changed mind",
        cancelled_by="patient"
    )
    assert cancelled is not None
    assert cancelled['status'] == 'CANCELLED_BY_PATIENT'
    assert cancelled['cancellation_reason'] == "Changed mind"