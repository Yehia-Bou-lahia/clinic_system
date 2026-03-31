import uuid
import logging
from datetime import date
from typing import Optional, Dict, Any, List

from database.connection import db
from database.queries.visit_report_repository import VisitReportRepository, ALLOWED_UPDATE_FIELDS as VISIT_REPORT_ALLOWED_UPDATE_FIELDS
from database.queries.appointment_repository import AppointmentRepository
from core.policy_engine import policy_engine
from core.event_bus import get_event_bus
from core.exceptions import (
    VisitReportNotFoundError,
    VisitReportAlreadyExistsError,
    AppointmentNotFoundError,
)

logger = logging.getLogger(__name__)

MAX_LIST_LIMIT = 100


class VisitReportService:
    def __init__(self):
        self.report_repo = VisitReportRepository()
        self.appointment_repo = AppointmentRepository()
        self.event_bus = get_event_bus()

    # ========================================
    # دوال مساعدة (validation)
    # ========================================
    @staticmethod
    def _validate_diagnosis(diagnosis: str) -> None:
        if not diagnosis or not diagnosis.strip():
            raise ValueError("Diagnosis cannot be empty")

    # ========================================
    # الطرق العامة
    # ========================================
    def create_report(
        self,
        requester_id: uuid.UUID,
        appointment_id: uuid.UUID,
        diagnosis: str,
        prescription: Optional[str] = None,
        lab_tests: Optional[str] = None,
        radiology: Optional[str] = None,
        notes: Optional[str] = None,
        follow_up_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        إنشاء تقرير زيارة لموعد معين.
        يجب أن يكون الموعد في حالة COMPLETED.
        """
        # 1. التحقق من وجود الموعد وحالته
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")
        if appointment['status'] != 'COMPLETED':
            raise ValueError("Report can only be created for completed appointments")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(requester_id, 'create', 'visit_report', context={'resource': appointment})

        # 3. التحقق من المدخلات
        self._validate_diagnosis(diagnosis)

        # 4. إنشاء التقرير ضمن معاملة
        with db.get_connection() as conn:
            try:
                report = self.report_repo.create_visit_report(
                    appointment_id=appointment_id,
                    patient_id=appointment['patient_id'],
                    doctor_id=appointment['doctor_id'],
                    diagnosis=diagnosis,
                    prescription=prescription,
                    lab_tests=lab_tests,
                    radiology=radiology,
                    notes=notes,
                    follow_up_date=follow_up_date,
                    conn=conn,   # تمرير الاتصال لاستخدامه في المعاملة
                )
            except VisitReportAlreadyExistsError as e:
                logger.warning(f"Report creation failed: {e}")
                raise

        # 5. نشر حدث بعد نجاح المعاملة
        self.event_bus.publish('visit_report.created', {
            'report_id': report['id'],
            'appointment_id': appointment_id,
            'patient_id': appointment['patient_id'],
            'doctor_id': appointment['doctor_id'],
            'user_id': requester_id,
        })
        logger.info(f"Visit report {report['id']} created for appointment {appointment_id}")
        return report

    def get_report_by_id(
        self,
        requester_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        جلب تقرير بواسطة معرفه (مع التحقق من الصلاحية).
        """
        # 1. جلب التقرير أولاً
        report = self.report_repo.get_report_by_id(report_id)
        if not report:
            raise VisitReportNotFoundError(f"Report {report_id} not found")

        # 2. التحقق من الصلاحية باستخدام التقرير الكامل
        policy_engine.enforce(requester_id, 'view', 'visit_report', context={'resource': report})
        return report

    def get_reports_by_patient(
        self,
        requester_id: uuid.UUID,
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        جلب تقارير مريض معين (مع التحقق من الصلاحية).
        """
        context = {'resource': {'patient_id': patient_id}}
        policy_engine.enforce(requester_id, 'view', 'visit_report', context)
        return self.report_repo.get_reports_by_patient(patient_id, limit, offset)

    def get_reports_by_doctor(
        self,
        requester_id: uuid.UUID,
        doctor_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        جلب تقارير طبيب معين (مع التحقق من الصلاحية).
        """
        context = {'resource': {'doctor_id': doctor_id}}
        policy_engine.enforce(requester_id, 'view', 'visit_report', context)
        return self.report_repo.get_reports_by_doctor(doctor_id, limit, offset)

    def update_report(
        self,
        requester_id: uuid.UUID,
        report_id: uuid.UUID,
        **fields,
    ) -> Dict[str, Any]:
        """
        تحديث تقرير. الحقول المسموحة محددة في VisitReportRepository.ALLOWED_UPDATE_FIELDS.
        """
        # 1. جلب التقرير القديم للتحقق من وجوده وللسياق
        old_report = self.report_repo.get_report_by_id(report_id)
        if not old_report:
            raise VisitReportNotFoundError(f"Report {report_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(requester_id, 'update', 'visit_report', context={'resource': old_report})

        # 3. بناء بيانات التحديث باستخدام القائمة من الـ Repository
        update_data = {}
        for key, value in fields.items():
            if key not in VISIT_REPORT_ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            if key == 'diagnosis':
                self._validate_diagnosis(value)
            update_data[key] = value

        if not update_data:
            return old_report

        # 4. تحديث التقرير (عملية منفردة، لا تحتاج معاملة)
        updated = self.report_repo.update_visit_report(report_id, **update_data)

        # 5. نشر حدث
        self.event_bus.publish('visit_report.updated', {
            'report_id': report_id,
            'user_id': requester_id,
            'updated_fields': list(update_data.keys()),
        })
        logger.info(f"Visit report {report_id} updated by user {requester_id}")
        return updated

    def soft_delete_report(
        self,
        requester_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> bool:
        """
        حذف منطقي للتقرير (يتطلب صلاحية إدارية).
        """
        # 1. جلب التقرير للسياق
        report = self.report_repo.get_report_by_id(report_id)
        if not report:
            raise VisitReportNotFoundError(f"Report {report_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(requester_id, 'soft_delete', 'visit_report', context={'resource': report})

        # 3. تنفيذ الحذف المنطقي
        deleted = self.report_repo.soft_delete_report(report_id)
        if deleted:
            self.event_bus.publish('visit_report.deleted', {
                'report_id': report_id,
                'user_id': requester_id,
            })
            logger.info(f"Visit report {report_id} soft-deleted by user {requester_id}")
        return deleted

    def list_reports(
        self,
        requester_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        جلب قائمة التقارير (للاستخدام الإداري).
        - include_deleted: عرض التقارير المحذوفة (يتطلب صلاحية خاصة)
        """
        # 1. التحقق من صلاحية القائمة الأساسية
        policy_engine.enforce(requester_id, 'list', 'visit_report')

        # 2. فرض الحد الأقصى للـ limit
        limit = min(limit, MAX_LIST_LIMIT)

        # 3. جلب البيانات (مع صلاحية إضافية للمحذوفين)
        if include_deleted:
            policy_engine.enforce(requester_id, 'list_deleted', 'visit_report')
            reports = self.report_repo.list_all_reports(limit, offset)
        else:
            reports = self.report_repo.list_active_reports(limit, offset)

        return reports