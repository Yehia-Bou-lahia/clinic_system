import uuid
from datetime import date
from typing import Optional, Dict, Any, List
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor
from database.connection import db
from core.exceptions import (
    DatabaseError,
    VisitReportNotFoundError,
    VisitReportAlreadyExistsError
)

# قائمة الأعمدة (مع deleted_at للاستعلامات الإدارية)
VISIT_REPORT_COLUMNS = """
    id, appointment_id, patient_id, doctor_id, diagnosis,
    prescription, lab_tests, radiology, notes, follow_up_date,
    created_at, updated_at, deleted_at
"""

# قائمة الأعمدة بدون deleted_at للاستعلامات العامة
VISIT_REPORT_ACTIVE_COLUMNS = """
    id, appointment_id, patient_id, doctor_id, diagnosis,
    prescription, lab_tests, radiology, notes, follow_up_date,
    created_at, updated_at
"""

ALLOWED_UPDATE_FIELDS = {
    'diagnosis', 'prescription', 'lab_tests',
    'radiology', 'notes', 'follow_up_date'
}

class VisitReportRepository:
    """التعامل مع جدول visit_reports"""

    @staticmethod
    def _execute_create(cursor, appointment_id, patient_id, doctor_id,
                        diagnosis, prescription, lab_tests, radiology,
                        notes, follow_up_date):
        """تنفيذ INSERT مشترك."""
        query = f"""
        INSERT INTO visit_reports (
            appointment_id, patient_id, doctor_id, diagnosis,
            prescription, lab_tests, radiology, notes, follow_up_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {VISIT_REPORT_ACTIVE_COLUMNS};
        """
        cursor.execute(query, (
            appointment_id, patient_id, doctor_id, diagnosis,
            prescription, lab_tests, radiology, notes, follow_up_date
        ))
        return cursor.fetchone()

    @staticmethod
    def create_visit_report(
        appointment_id: uuid.UUID,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        diagnosis: str,
        prescription: Optional[str] = None,
        lab_tests: Optional[str] = None,
        radiology: Optional[str] = None,
        notes: Optional[str] = None,
        follow_up_date: Optional[date] = None,
        conn: Optional[Any] = None,   # ← معامل اختياري للمعاملة
    ) -> Dict[str, Any]:
        """
        إنشاء تقرير زيارة جديد (نشط).
        """
        if not appointment_id or not patient_id or not doctor_id or not diagnosis:
            raise ValueError("appointment_id, patient_id, doctor_id, and diagnosis are required")

        try:
            if conn:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                result = VisitReportRepository._execute_create(
                    cursor, appointment_id, patient_id, doctor_id,
                    diagnosis, prescription, lab_tests, radiology,
                    notes, follow_up_date
                )
            else:
                with db.get_cursor() as cursor:
                    result = VisitReportRepository._execute_create(
                        cursor, appointment_id, patient_id, doctor_id,
                        diagnosis, prescription, lab_tests, radiology,
                        notes, follow_up_date
                    )
            if not result:
                raise DatabaseError("Failed to create visit report")
            return result
        except IntegrityError as e:
            if 'unique constraint' in str(e).lower():
                raise VisitReportAlreadyExistsError(
                    f"Report for appointment {appointment_id} already exists"
                )
            raise

    @staticmethod
    def get_report_by_id(report_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """جلب تقرير نشط بواسطة المعرف."""
        query = f"""
        SELECT {VISIT_REPORT_ACTIVE_COLUMNS}
        FROM visit_reports
        WHERE id = %s AND deleted_at IS NULL;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (report_id,))
            return cursor.fetchone()

    @staticmethod
    def get_report_by_appointment(appointment_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """جلب تقرير نشط بواسطة معرف الموعد."""
        query = f"""
        SELECT {VISIT_REPORT_ACTIVE_COLUMNS}
        FROM visit_reports
        WHERE appointment_id = %s AND deleted_at IS NULL;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (appointment_id,))
            return cursor.fetchone()

    @staticmethod
    def get_reports_by_patient(
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """جلب تقارير المريض النشطة."""
        query = f"""
        SELECT {VISIT_REPORT_ACTIVE_COLUMNS}
        FROM visit_reports
        WHERE patient_id = %s AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (patient_id, limit, offset))
            return cursor.fetchall()

    @staticmethod
    def get_reports_by_doctor(
        doctor_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """جلب التقارير التي كتبها طبيب معين (النشطة)."""
        query = f"""
        SELECT {VISIT_REPORT_ACTIVE_COLUMNS}
        FROM visit_reports
        WHERE doctor_id = %s AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (doctor_id, limit, offset))
            return cursor.fetchall()

    @staticmethod
    def update_visit_report(
        report_id: uuid.UUID,
        **fields: Any
    ) -> Dict[str, Any]:
        """
        تحديث حقل أو أكثر في التقرير النشط.
        الحقول المسموحة: ALLOWED_UPDATE_FIELDS.
        """
        if not fields:
            return VisitReportRepository.get_report_by_id(report_id)

        set_clauses = []
        values = []
        for key, value in fields.items():
            if key not in ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            set_clauses.append(f"{key} = %s")
            values.append(value)

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.append(report_id)

        query = f"""
        UPDATE visit_reports
        SET {', '.join(set_clauses)}
        WHERE id = %s AND deleted_at IS NULL
        RETURNING {VISIT_REPORT_ACTIVE_COLUMNS};
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, values)
            updated = cursor.fetchone()
            if not updated:
                raise VisitReportNotFoundError(f"Report {report_id} not found or already deleted")
            return updated

    @staticmethod
    def soft_delete_report(report_id: uuid.UUID) -> bool:
        """حذف منطقي للتقرير."""
        query = """
        UPDATE visit_reports
        SET deleted_at = CURRENT_TIMESTAMP
        WHERE id = %s AND deleted_at IS NULL
        RETURNING id;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (report_id,))
            return cursor.fetchone() is not None

    @staticmethod
    def restore_report(report_id: uuid.UUID) -> bool:
        """استعادة تقرير محذوف."""
        query = """
        UPDATE visit_reports
        SET deleted_at = NULL
        WHERE id = %s AND deleted_at IS NOT NULL
        RETURNING id;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (report_id,))
            return cursor.fetchone() is not None

    @staticmethod
    def list_active_reports(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """قائمة التقارير النشطة (للاستخدام العام)."""
        query = f"""
        SELECT {VISIT_REPORT_ACTIVE_COLUMNS}
        FROM visit_reports
        WHERE deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()

    @staticmethod
    def list_all_reports(limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """قائمة جميع التقارير (بما فيها المحذوفة) – للاستخدام الإداري."""
        query = f"""
        SELECT {VISIT_REPORT_COLUMNS}
        FROM visit_reports
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s;
        """
        with db.get_cursor() as cursor:
            cursor.execute(query, (limit, offset))
            return cursor.fetchall()