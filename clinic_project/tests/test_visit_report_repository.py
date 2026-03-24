import pytest
from datetime import datetime, timedelta, date
from database.queries.user_repository import UserRepository
from database.queries.patient_repository import PatientRepository
from database.queries.doctor_repository import DoctorRepository
from database.queries.appointment_repository import AppointmentRepository
from database.queries.visit_report_repository import VisitReportRepository
from core.exceptions import VisitReportAlreadyExistsError

def test_create_visit_report(db_cursor, patient_role_id, doctor_role_id):
    # Patient
    user_p = UserRepository.create_user(
        email="samia.boudiaf@example.com",
        password="pass",
        full_name="Samia Boudiaf",
        phone_number="0555555555",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user_p['id'],
        date_of_birth=date(1988, 6, 15)
    )
    # Doctor
    user_d = UserRepository.create_user(
        email="hocine.zerrouki@example.com",
        password="pass",
        full_name="Hocine Zerrouki",
        phone_number="0666666666",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user_d['id'],
        specialty="Cardiology",
        license_number="LIC-REPORT",
        consultation_fee=200
    )
    # Appointment
    dt = datetime.now() + timedelta(days=1)
    appointment = AppointmentRepository.create_appointment(
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        appointment_datetime=dt
    )
    # Visit report
    report = VisitReportRepository.create_visit_report(
        appointment_id=appointment['id'],
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        diagnosis="Hypertension",
        prescription="Medication A",
        notes="Follow up in 2 weeks"
    )
    assert report is not None
    assert report['diagnosis'] == "Hypertension"

def test_get_report_by_appointment(db_cursor, patient_role_id, doctor_role_id):
    # Similar setup (using new emails)
    user_p = UserRepository.create_user(
        email="nadir.meziane@example.com",
        password="pass",
        full_name="Nadir Meziane",
        phone_number="0777777777",
        role_id=patient_role_id
    )
    patient = PatientRepository.create_patient_profile(
        user_id=user_p['id'],
        date_of_birth=date(1992, 9, 20)
    )
    user_d = UserRepository.create_user(
        email="fatima.zohra@example.com",
        password="pass",
        full_name="Fatima Zohra",
        phone_number="0888888888",
        role_id=doctor_role_id
    )
    doctor = DoctorRepository.create_doctor_profile(
        user_id=user_d['id'],
        specialty="Pediatrics",
        license_number="LIC-GET",
        consultation_fee=150
    )
    dt = datetime.now() + timedelta(days=2)
    appointment = AppointmentRepository.create_appointment(
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        appointment_datetime=dt
    )
    report = VisitReportRepository.create_visit_report(
        appointment_id=appointment['id'],
        patient_id=patient['id'],
        doctor_id=doctor['id'],
        diagnosis="Fever"
    )
    fetched = VisitReportRepository.get_report_by_appointment(appointment['id'])
    assert fetched is not None
    assert fetched['id'] == report['id']