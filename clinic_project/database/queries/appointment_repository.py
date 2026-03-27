import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from psycopg2 import IntegrityError
from database.connection import db
from core.exceptions import (
    DatabaseError,
    AppointmentNotFoundError,
    AppointmentConflictError,
)

ALLOWED_UPDATE_FIELDS = {
    'notes', 'is_paid', 'payment_amount'
}

APPOINTMENT_COLUMNS = """
    id, patient_id, doctor_id, appointment_datetime, status,
    cancellation_reason, confirmation_deadline, confirmed_at,
    checked_in_at, no_show_at, completed_at, notes, is_paid,
    payment_amount, created_at, updated_at
"""
_SELECT_APPOINTMENT = f"SELECT {APPOINTMENT_COLUMNS} FROM appointments"


class AppointmentRepository:
    @staticmethod
    def create_appointment(
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        appointment_datetime: datetime,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        إنشاء موعد جديد، الحالة PENDING تلقائياً.
        لا يقوم بالتحقق من التعارض – هذا دور الـ Service.
        """
        if not patient_id or not doctor_id or not appointment_datetime:
            raise ValueError("Patient ID, Doctor ID, and Appointment DateTime are required.")

        query = f"""
            INSERT INTO appointments (
                id, patient_id, doctor_id, appointment_datetime,
                status, confirmation_deadline, notes
            )
            VALUES (
                gen_random_uuid(), %s, %s, %s, 'PENDING',
                CURRENT_TIMESTAMP + INTERVAL '24 HOURS', %s
            )
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            try:
                cursor.execute(query, (patient_id, doctor_id, appointment_datetime, notes))
                result = cursor.fetchone()
                if not result:
                    raise DatabaseError("Failed to create appointment.")
                return result
            except IntegrityError as e:
                if 'unique constraint' in str(e):
                    raise AppointmentConflictError("Time slot is already booked for this doctor.")
                raise

    @staticmethod
    def get_appointment_by_id(appointment_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        جلب موعد بواسطة المعرف.
        تعيد None إذا لم يوجد.
        """
        query = _SELECT_APPOINTMENT + " WHERE id = %s;"
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            return cursor.fetchone()   # تعيد None إذا لم يوجد

    @staticmethod
    def get_appointments_by_patient(
        patient_id: uuid.UUID,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        جلب مواعيد مريض معين، مع فلترة اختيارية حسب الحالة.
        """
        query = _SELECT_APPOINTMENT + " WHERE patient_id = %s"
        params = [patient_id]

        if status:
            query += " AND status = %s"
            params.append(status)
        query += " ORDER BY appointment_datetime DESC LIMIT %s OFFSET %s;"
        params.extend([limit, offset])

        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def get_appointments_by_doctor(
        doctor_id: uuid.UUID,
        from_datetime: Optional[datetime] = None,
        to_datetime: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        جلب مواعيد طبيب معين، مع فلترة اختيارية حسب الفترة الزمنية.
        """
        query = _SELECT_APPOINTMENT + " WHERE doctor_id = %s"
        params = [doctor_id]

        if from_datetime:
            query += " AND appointment_datetime >= %s"
            params.append(from_datetime)
        if to_datetime:
            query += " AND appointment_datetime <= %s"
            params.append(to_datetime)
        query += " ORDER BY appointment_datetime DESC LIMIT %s OFFSET %s;"
        params.extend([limit, offset])

        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def list_all_appointments(
        status: Optional[str] = None,
        from_datetime: Optional[datetime] = None,
        to_datetime: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        جلب جميع المواعيد (للاستخدام الإداري)، مع فلترة اختيارية.
        """
        query = _SELECT_APPOINTMENT + " WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        if from_datetime:
            query += " AND appointment_datetime >= %s"
            params.append(from_datetime)
        if to_datetime:
            query += " AND appointment_datetime <= %s"
            params.append(to_datetime)

        query += " ORDER BY appointment_datetime DESC LIMIT %s OFFSET %s;"
        params.extend([limit, offset])

        with db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

    @staticmethod
    def count_pending_by_patient(patient_id: uuid.UUID) -> int:
        """
        عدد المواعيد المعلقة (PENDING) لمريض معين.
        """
        query = """
            SELECT COUNT(*) as cnt FROM appointments
            WHERE patient_id = %s AND status = 'PENDING'
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (patient_id,))
            row = cursor.fetchone()
            return row['cnt'] if row else 0

    @staticmethod
    def confirm_appointment(appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        تأكيد الموعد (PENDING → CONFIRMED).
        """
        query = f"""
            UPDATE appointments
            SET status = 'CONFIRMED', confirmed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'PENDING'
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} not found or not in PENDING state."
                )
            return updated

    @staticmethod
    def cancel_appointment(appointment_id: uuid.UUID, reason: str, cancelled_by: str) -> Dict[str, Any]:
        """
        إلغاء موعد.
        cancelled_by: 'patient', 'doctor', 'auto'
        """
        status_map = {
            'patient': 'CANCELLED_BY_PATIENT',
            'doctor': 'CANCELLED_BY_DOCTOR',
            'auto': 'CANCELLED_AUTO'
        }
        if cancelled_by not in status_map:
            raise ValueError("cancelled_by must be one of 'patient', 'doctor', or 'auto'.")
        new_status = status_map[cancelled_by]

        invalid_statuses = ('CANCELLED_BY_PATIENT', 'CANCELLED_BY_DOCTOR', 'CANCELLED_AUTO', 'COMPLETED', 'NO_SHOW')

        query = f"""
            UPDATE appointments
            SET status = %s, cancellation_reason = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status NOT IN %s
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (new_status, reason, appointment_id, invalid_statuses))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} cannot be cancelled (already completed, no-show, or already cancelled)."
                )
            return updated

    @staticmethod
    def check_in(appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        تسجيل وصول المريض (CONFIRMED → IN_PROGRESS).
        """
        query = f"""
            UPDATE appointments
            SET status = 'IN_PROGRESS', checked_in_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'CONFIRMED'
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} not found or not in CONFIRMED state."
                )
            return updated

    @staticmethod
    def complete_appointment(appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        إنهاء الموعد (IN_PROGRESS → COMPLETED).
        """
        query = f"""
            UPDATE appointments
            SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'IN_PROGRESS'
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} not found or not in IN_PROGRESS state."
                )
            return updated

    @staticmethod
    def mark_no_show(appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        تسجيل عدم حضور المريض (CONFIRMED → NO_SHOW).
        """
        query = f"""
            UPDATE appointments
            SET status = 'NO_SHOW', no_show_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND status = 'CONFIRMED'
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} not found or not in CONFIRMED state."
                )
            return updated

    @staticmethod
    def reschedule_appointment(
        appointment_id: uuid.UUID,
        new_datetime: datetime
    ) -> Dict[str, Any]:
        """
        إعادة جدولة الموعد (تغيير الوقت).
        لا يقوم بالتحقق من التعارض – هذا دور الـ Service.
        """
        query = f"""
            UPDATE appointments
            SET appointment_datetime = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            try:
                cursor.execute(query, (new_datetime, appointment_id))
                updated = cursor.fetchone()
                if not updated:
                    raise AppointmentNotFoundError(
                        f"Appointment with ID {appointment_id} not found."
                    )
                return updated
            except IntegrityError as e:
                if 'unique constraint' in str(e):
                    raise AppointmentConflictError("Time slot is already booked for this doctor.")
                raise

    @staticmethod
    def update_appointment(
        appointment_id: uuid.UUID,
        **fields: Any
    ) -> Dict[str, Any]:
        """
        تحديث الحقول المسموحة (notes, is_paid, payment_amount).
        """
        if not fields:
            return AppointmentRepository.get_appointment_by_id(appointment_id)

        set_clauses = []
        values = []
        for key, value in fields.items():
            if key not in ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field for update: {key}")
            set_clauses.append(f"{key} = %s")
            values.append(value)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(appointment_id)

        query = f"""
            UPDATE appointments
            SET {', '.join(set_clauses)}
            WHERE id = %s
            RETURNING {APPOINTMENT_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, tuple(values))
            updated = cursor.fetchone()
            if not updated:
                raise AppointmentNotFoundError(
                    f"Appointment with ID {appointment_id} not found."
                )
            return updated