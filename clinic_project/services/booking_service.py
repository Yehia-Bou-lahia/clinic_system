# services/booking_service.py
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from database.connection import db
from database.queries.appointment_repository import AppointmentRepository
from database.queries.doctor_repository import DoctorRepository
from database.queries.patient_repository import PatientRepository
from core.policy_engine import policy_engine
from core.event_bus import get_event_bus
from core.exceptions import (
    DoctorNotAvailableError,
    BookingLimitError,
    PermissionDenied,
    AppointmentNotFoundError,
    InvalidAppointmentStatusError,
    FeatureDisabledError,
)
from services.feature_flag_service import get_feature_flag_service

logger = logging.getLogger(__name__)


class BookingService:
    """
    خدمة إدارة المواعيد (الحجز، الإلغاء، التأكيد، إعادة الجدولة).
    تستخدم PolicyEngine للتحقق من الصلاحيات و EventBus لنشر الأحداث.
    """

    VALID_CANCELLED_BY = {'patient', 'doctor', 'auto'}
    MAX_REASON_LENGTH = 500
    MAX_NOTES_LENGTH = 1000
    MAX_LIST_LIMIT = 100

    def __init__(
        self,
        appointment_repo=None,
        doctor_repo=None,
        patient_repo=None,
        policy_engine=policy_engine,
        event_bus=None,
        feature_flag_service=None,
    ):
        self.appointment_repo = appointment_repo or AppointmentRepository()
        self.doctor_repo = doctor_repo or DoctorRepository()
        self.patient_repo = patient_repo or PatientRepository()
        self.policy_engine = policy_engine
        self.event_bus = event_bus or get_event_bus()
        self.feature_flags = feature_flag_service or get_feature_flag_service()

    # ========================================
    # دوال مساعدة للتحقق
    # ========================================
    def _validate_appointment_datetime(self, dt: datetime) -> None:
        """تأكد من أن تاريخ الموعد في المستقبل."""
        if dt <= datetime.now():
            raise ValueError("Appointment datetime must be in the future")

    def _validate_cancelled_by(self, cancelled_by: str) -> None:
        """تأكد من أن قيمة cancelled_by مسموحة."""
        if cancelled_by not in self.VALID_CANCELLED_BY:
            raise ValueError(f"Invalid cancelled_by value: {cancelled_by}. Allowed: {', '.join(self.VALID_CANCELLED_BY)}")

    def _validate_reason(self, reason: str) -> None:
        """تأكد من أن سبب الإلغاء لا يتجاوز الحد المسموح."""
        if not reason or not reason.strip():
            raise ValueError("Cancellation reason is required")
        if len(reason) > self.MAX_REASON_LENGTH:
            raise ValueError(f"Cancellation reason cannot exceed {self.MAX_REASON_LENGTH} characters")

    def _validate_notes(self, notes: Optional[str]) -> None:
        """تأكد من أن الملاحظات لا تتجاوز الحد المسموح."""
        if notes and len(notes) > self.MAX_NOTES_LENGTH:
            raise ValueError(f"Notes cannot exceed {self.MAX_NOTES_LENGTH} characters")

    # ========================================
    # الدوال الرئيسية
    # ========================================

    def book_appointment(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        appointment_datetime: datetime,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """حجز موعد جديد."""
        # 0. التحقق من تفعيل ميزة الحجز عبر الإنترنت
        if not self.feature_flags.is_enabled('online_booking'):
            raise FeatureDisabledError("Online booking is currently disabled")

        # 0a. التحقق من تاريخ الموعد
        self._validate_appointment_datetime(appointment_datetime)

        # 0b. التحقق من الملاحظات (إن وجدت)
        self._validate_notes(notes)

        # 1. صلاحية
        try:
            self.policy_engine.enforce(user_id, 'create_appointment', 'appointment')
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to create appointment: {e}")
            raise

        # 2. توفر الطبيب
        if not self.doctor_repo.is_available(doctor_id, appointment_datetime):
            logger.info(f"Doctor {doctor_id} is not available at {appointment_datetime}")
            raise DoctorNotAvailableError(f"Doctor {doctor_id} is not available at {appointment_datetime}")

        # 3. حد الحجز اليومي
        pending_count = self.appointment_repo.count_pending_by_patient(patient_id)
        if pending_count >= 3:
            logger.info(f"Patient {patient_id} has reached daily booking limit ({pending_count} pending)")
            raise BookingLimitError("You have reached the daily booking limit of 3 pending appointments")

        # 4. جلب user_id الخاص بالمريض والطبيب (لنشر الحدث)
        patient = self.patient_repo.get_patient_by_id(patient_id)
        doctor = self.doctor_repo.get_doctor_by_id(doctor_id)
        if not patient or not doctor:
            raise ValueError("Patient or doctor profile not found")

        # 5. إنشاء الموعد (ضمن معاملة)
        with db.get_connection() as conn:
            appointment = self.appointment_repo.create_appointment(
                patient_id=patient_id,
                doctor_id=doctor_id,
                appointment_datetime=appointment_datetime,
                notes=notes,
                conn=conn,
            )

        # 6. نشر الحدث
        self.event_bus.publish('appointment.created', {
            'appointment_id': appointment['id'],
            'patient_id': patient_id,
            'patient_user_id': patient['user_id'],
            'doctor_id': doctor_id,
            'doctor_user_id': doctor['user_id'],
            'datetime': appointment_datetime.isoformat(),
            'user_id': user_id,
            'notes': notes,
        })
        logger.info(f"Appointment {appointment['id']} created by user {user_id}")
        return appointment

    def confirm_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """تأكيد الموعد (يجب أن يكون حالته PENDING)."""
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'confirm_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to confirm appointment {appointment_id}: {e}")
            raise

        updated = self.appointment_repo.confirm_appointment(appointment_id)

        self.event_bus.publish('appointment.confirmed', {
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} confirmed by user {user_id}")
        return updated

    def cancel_appointment(
        self,
        user_id: uuid.UUID,
        appointment_id: uuid.UUID,
        reason: str,
        cancelled_by: str,
    ) -> Dict[str, Any]:
        """إلغاء الموعد."""
        # التحقق من المدخلات
        self._validate_cancelled_by(cancelled_by)
        self._validate_reason(reason)

        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'cancel_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to cancel appointment {appointment_id}: {e}")
            raise

        cancelled = self.appointment_repo.cancel_appointment(appointment_id, reason, cancelled_by)

        self.event_bus.publish('appointment.cancelled', {
            'appointment_id': appointment_id,
            'patient_id': cancelled['patient_id'],
            'doctor_id': cancelled['doctor_id'],
            'datetime': cancelled['appointment_datetime'].isoformat(),
            'user_id': user_id,
            'reason': reason,
            'cancelled_by': cancelled_by,
        })
        logger.info(f"Appointment {appointment_id} cancelled by user {user_id} (cancelled_by={cancelled_by}, reason={reason})")
        return cancelled

    def reschedule_appointment(
        self,
        user_id: uuid.UUID,
        appointment_id: uuid.UUID,
        new_datetime: datetime,
        reason: str,
    ) -> Dict[str, Any]:
        """إعادة جدولة الموعد (تغيير الوقت)."""
        # التحقق من تاريخ الموعد الجديد
        self._validate_appointment_datetime(new_datetime)
        self._validate_reason(reason)

        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'reschedule_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to reschedule appointment {appointment_id}: {e}")
            raise

        if not self.doctor_repo.is_available(appointment['doctor_id'], new_datetime):
            raise DoctorNotAvailableError(f"Doctor {appointment['doctor_id']} is not available at {new_datetime}")

        updated = self.appointment_repo.reschedule_appointment(appointment_id, new_datetime)

        self.event_bus.publish('appointment.rescheduled', {
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'old_datetime': appointment['appointment_datetime'].isoformat(),
            'new_datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} rescheduled to {new_datetime} by user {user_id}")
        return updated

    def check_in(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """تسجيل وصول المريض (CONFIRMED → IN_PROGRESS)."""
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'check_in', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to check-in appointment {appointment_id}: {e}")
            raise

        updated = self.appointment_repo.check_in(appointment_id)

        self.event_bus.publish('appointment.checked_in', {
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} checked-in by user {user_id}")
        return updated

    def complete_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """إنهاء الموعد (IN_PROGRESS → COMPLETED)."""
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'complete_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to complete appointment {appointment_id}: {e}")
            raise

        updated = self.appointment_repo.complete_appointment(appointment_id)

        self.event_bus.publish('appointment.completed', {
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} completed by user {user_id}")
        return updated

    def mark_no_show(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """تسجيل عدم حضور المريض (CONFIRMED → NO_SHOW)."""
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'mark_no_show', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to mark no-show for appointment {appointment_id}: {e}")
            raise

        updated = self.appointment_repo.mark_no_show(appointment_id)

        self.event_bus.publish('appointment.no_show', {
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} marked as no-show by user {user_id}")
        return updated

    def get_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """جلب بيانات موعد معين (مع التحقق من صلاحية الوصول)."""
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            self.policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointment {appointment_id}: {e}")
            raise

        return appointment

    def list_appointments_by_patient(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ):
        """جلب مواعيد مريض معين (مع التحقق من الصلاحية)."""
        context = {'resource': {'patient_id': patient_id}}
        try:
            self.policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for patient {patient_id}: {e}")
            raise

        limit = min(limit, self.MAX_LIST_LIMIT)
        return self.appointment_repo.get_appointments_by_patient(patient_id, limit=limit, offset=offset)

    def list_appointments_by_doctor(
        self,
        user_id: uuid.UUID,
        doctor_id: uuid.UUID,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 20,
        offset: int = 0,
    ):
        """جلب مواعيد طبيب معين (مع التحقق من الصلاحية)."""
        context = {'resource': {'doctor_id': doctor_id}}
        try:
            self.policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for doctor {doctor_id}: {e}")
            raise

        limit = min(limit, self.MAX_LIST_LIMIT)
        return self.appointment_repo.get_appointments_by_doctor(
            doctor_id, from_date, to_date, limit, offset
        )