# services/booking_service.py
import uuid
import logging
import time
from functools import wraps
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from clinic_project.services.settings_service import SettingsService
from database.connection import db
from database.queries.appointment_repository import AppointmentRepository
from database.queries.doctor_repository import DoctorRepository
from database.queries.patient_repository import PatientRepository
from database.queries.idempotency_repository import IdempotencyRepository
from core.policy_engine import policy_engine
from core.event_bus import get_event_bus
from core.exceptions import (
    DoctorNotAvailableError,
    BookingLimitError,
    PermissionDenied,
    AppointmentNotFoundError,
    FeatureDisabledError,
    AppointmentConflictError,
)
from services.feature_flag_service import get_feature_flag_service

logger = logging.getLogger(__name__)


def retry_on_transient_error(max_retries=3, delay=0.1):
    """إعادة المحاولة فقط للأخطاء العابرة (deadlock, timeout, connection) وليس لتعارض الحجز."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except AppointmentConflictError:
                    # لا نعيد المحاولة على تعارض الحجز (لن ينجح)
                    raise
                except Exception as e:
                    error_str = str(e).lower()
                    is_transient = any(x in error_str for x in ['deadlock', 'timeout', 'connection', 'operationalerror'])
                    if is_transient and attempt < max_retries - 1:
                        wait = delay * (2 ** attempt)
                        time.sleep(wait)
                        continue
                    raise
            raise last_exception
        return wrapper
    return decorator


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
        idempotency_repo=None,
        policy_engine=policy_engine,
        event_bus=None,
        feature_flag_service=None,
    ):
        self.appointment_repo = appointment_repo or AppointmentRepository()
        self.doctor_repo = doctor_repo or DoctorRepository()
        self.patient_repo = patient_repo or PatientRepository()
        self.idempotency_repo = idempotency_repo or IdempotencyRepository()
        self.policy_engine = policy_engine
        self.event_bus = event_bus or get_event_bus()
        self.feature_flags = feature_flag_service or get_feature_flag_service()
        self.settings = SettingsService()

    # ========================================
    # دوال مساعدة للتحقق والتوحيد
    # ========================================
    def _validate_appointment_datetime(self, dt: datetime) -> None:
        """تأكد من أن تاريخ الموعد في المستقبل (باستخدام UTC)."""
        if dt <= datetime.now(timezone.utc):
            raise ValueError("Appointment datetime must be in the future")

    def _validate_cancelled_by(self, cancelled_by: str) -> None:
        if cancelled_by not in self.VALID_CANCELLED_BY:
            raise ValueError(f"Invalid cancelled_by value: {cancelled_by}. Allowed: {', '.join(self.VALID_CANCELLED_BY)}")

    def _validate_reason(self, reason: str) -> None:
        if not reason or not reason.strip():
            raise ValueError("Cancellation reason is required")
        if len(reason) > self.MAX_REASON_LENGTH:
            raise ValueError(f"Cancellation reason cannot exceed {self.MAX_REASON_LENGTH} characters")

    def _validate_notes(self, notes: Optional[str]) -> None:
        if notes and len(notes) > self.MAX_NOTES_LENGTH:
            raise ValueError(f"Notes cannot exceed {self.MAX_NOTES_LENGTH} characters")

    def _get_and_authorize(self, user_id: uuid.UUID, appointment_id: uuid.UUID, action: str) -> Dict[str, Any]:
        """
        جلب الموعد والتحقق من صلاحية المستخدم لتنفيذ action.
        تعيد بيانات الموعد إذا نجحت، وإلا ترفع استثناء.
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")
        context = {'resource': appointment}
        self.policy_engine.enforce(user_id, action, 'appointment', context)
        return appointment

    def _build_event_payload(self, event_type: str, appointment: Dict[str, Any], actor_id: uuid.UUID, extra: Optional[Dict] = None) -> Dict[str, Any]:
        """بناء حمولة الحدث بشكل موحد."""
        payload = {
            "event_type": event_type,
            "appointment": {
                "id": appointment['id'],
                "patient_id": appointment['patient_id'],
                "doctor_id": appointment['doctor_id'],
                "datetime": appointment['appointment_datetime'].isoformat() if isinstance(appointment['appointment_datetime'], datetime) else appointment['appointment_datetime'],
                "status": appointment['status'],
            },
            "actor": str(actor_id),
        }
        if extra:
            payload.update(extra)
        return payload

    # ========================================
    # الدوال الرئيسية
    # ========================================

    @retry_on_transient_error(max_retries=3, delay=0.1)
    def book_appointment(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        doctor_id: uuid.UUID,
        appointment_datetime: datetime,
        notes: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """حجز موعد جديد – مع Idempotency ومعاملة لمنع race condition."""
        logger.debug("Booking appointment", extra={"correlation_id": correlation_id, "user_id": str(user_id)})

        # 0. Idempotency
        if idempotency_key:
            cached = self.idempotency_repo.get(idempotency_key)
            if cached:
                logger.info("Idempotent request, returning cached response", extra={"correlation_id": correlation_id, "idempotency_key": idempotency_key})
                return cached

        # 1. التحقق من تفعيل ميزة الحجز عبر الإنترنت
        if not self.feature_flags.is_enabled('online_booking'):
            raise FeatureDisabledError("Online booking is currently disabled")

        # 2. التحقق من تاريخ الموعد والملاحظات
        self._validate_appointment_datetime(appointment_datetime)
        self._validate_notes(notes)

        # 3. صلاحية
        try:
            self.policy_engine.enforce(user_id, 'create_appointment', 'appointment')
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to create appointment", extra={"correlation_id": correlation_id})
            raise

        # 4. جلب بيانات المريض والطبيب (لنشر الحدث)
        patient = self.patient_repo.get_patient_by_id(patient_id)
        doctor = self.doctor_repo.get_doctor_by_id(doctor_id)
        if not patient or not doctor:
            raise ValueError("Patient or doctor profile not found")

        # 5. استخدام معاملة واحدة مع الاعتماد على القيد الفريد لمنع الحجز المزدوج
        with db.get_connection() as conn:
            try:
                appointment = self.appointment_repo.create_appointment_with_lock(
                    patient_id=patient_id,
                    doctor_id=doctor_id,
                    appointment_datetime=appointment_datetime,
                    notes=notes,
                    conn=conn,
                )
            except AppointmentConflictError as e:
                raise DoctorNotAvailableError(f"Doctor {doctor_id} is not available at {appointment_datetime}") from e

            # التحقق من حد الحجز اليومي (يُقرأ من قاعدة البيانات)
            max_pending = self.policy_engine.get_config('max_pending_appointments', default=3)
            pending_count = self.appointment_repo.count_pending_by_patient(patient_id)
            if pending_count >= max_pending:
                raise BookingLimitError(f"You have reached the daily booking limit of {max_pending} pending appointments")

            # تخزين idempotency key (نفس المعاملة)
            if idempotency_key:
                self.idempotency_repo.save(idempotency_key, appointment, conn=conn)

        # 6. نشر الحدث (بعد المعاملة)
        event_payload = self._build_event_payload(
            event_type="appointment.created",
            appointment=appointment,
            actor_id=user_id,
            extra={"patient_user_id": str(patient['user_id']), "doctor_user_id": str(doctor['user_id']), "notes": notes}
        )
        self.event_bus.publish('appointment.created', event_payload)
        logger.info(
            "appointment_created",
            extra={
                "correlation_id": correlation_id,
                "user_id": str(user_id),
                "appointment_id": str(appointment['id']),
                "doctor_id": str(doctor_id),
                "patient_id": str(patient_id),
                "datetime": appointment_datetime.isoformat(),
            }
        )
        return appointment

    def confirm_appointment(
            self, 
            user_id: uuid.UUID, 
            appointment_id: uuid.UUID, 
            correlation_id: Optional[str] = None,
            ) -> Dict[str, Any]:
        logger.debug("Confirming appointment", extra={"correlation_id": correlation_id, "user_id": str(user_id), "appointment_id": str(appointment_id)})
        appointment = self._get_and_authorize(user_id, appointment_id, 'confirm_appointment')
        updated = self.appointment_repo.confirm_appointment(appointment_id)
        event_payload = self._build_event_payload("appointment.confirmed", updated, user_id)
        self.event_bus.publish('appointment.confirmed', event_payload)
        logger.info(f"Appointment {appointment_id} confirmed by user {user_id}", extra={"correlation_id": correlation_id})
        return updated

    def cancel_appointment(
        self,
        user_id: uuid.UUID,
        appointment_id: uuid.UUID,
        reason: str,
        cancelled_by: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_cancelled_by(cancelled_by)
        self._validate_reason(reason)
        appointment = self._get_and_authorize(user_id, appointment_id, 'cancel_appointment')
        cancelled = self.appointment_repo.cancel_appointment(appointment_id, reason, cancelled_by)
        event_payload = self._build_event_payload("appointment.cancelled", cancelled, user_id, extra={"reason": reason, "cancelled_by": cancelled_by})
        self.event_bus.publish('appointment.cancelled', event_payload)
        logger.info(f"Appointment {appointment_id} cancelled by user {user_id} (cancelled_by={cancelled_by})", extra={"correlation_id": correlation_id})
        return cancelled

    def reschedule_appointment(
        self,
        user_id: uuid.UUID,
        appointment_id: uuid.UUID,
        new_datetime: datetime,
        reason: str,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._validate_appointment_datetime(new_datetime)
        self._validate_reason(reason)
        appointment = self._get_and_authorize(user_id, appointment_id, 'reschedule_appointment')
        old_datetime = appointment['appointment_datetime']
        if not self.doctor_repo.is_available(appointment['doctor_id'], new_datetime):
            raise DoctorNotAvailableError(f"Doctor {appointment['doctor_id']} not available at {new_datetime}")
        updated = self.appointment_repo.reschedule_appointment(appointment_id, new_datetime)
        event_payload = self._build_event_payload("appointment.rescheduled", updated, user_id, extra={"old_datetime": old_datetime.isoformat(), "reason": reason})
        self.event_bus.publish('appointment.rescheduled', event_payload)
        logger.info(f"Appointment {appointment_id} rescheduled to {new_datetime} by user {user_id}", extra={"correlation_id": correlation_id})
        return updated

    def check_in(
            self, 
            user_id: uuid.UUID, 
            appointment_id: uuid.UUID, 
            correlation_id: Optional[str] = None,
            ) -> Dict[str, Any]:
        appointment = self._get_and_authorize(user_id, appointment_id, 'check_in')
        updated = self.appointment_repo.check_in(appointment_id)
        event_payload = self._build_event_payload("appointment.checked_in", updated, user_id)
        self.event_bus.publish('appointment.checked_in', event_payload)
        logger.info(f"Appointment {appointment_id} checked-in by user {user_id}", extra={"correlation_id": correlation_id})
        return updated

    def complete_appointment(
            self, 
            user_id: uuid.UUID, 
            appointment_id: uuid.UUID, 
            correlation_id: Optional[str] = None,
            ) -> Dict[str, Any]:
        appointment = self._get_and_authorize(user_id, appointment_id, 'complete_appointment')
        updated = self.appointment_repo.complete_appointment(appointment_id)
        event_payload = self._build_event_payload("appointment.completed", updated, user_id)
        self.event_bus.publish('appointment.completed', event_payload)
        logger.info(f"Appointment {appointment_id} completed by user {user_id}", extra={"correlation_id": correlation_id})
        return updated

    def mark_no_show(
            self, 
            user_id: uuid.UUID, 
            appointment_id: uuid.UUID, 
            correlation_id: Optional[str] = None,
            ) -> Dict[str, Any]:
        appointment = self._get_and_authorize(user_id, appointment_id, 'mark_no_show')
        updated = self.appointment_repo.mark_no_show(appointment_id)
        event_payload = self._build_event_payload("appointment.no_show", updated, user_id)
        self.event_bus.publish('appointment.no_show', event_payload)
        logger.info(f"Appointment {appointment_id} marked as no-show by user {user_id}", extra={"correlation_id": correlation_id})
        return updated

    def get_appointment(
            self, 
            user_id: uuid.UUID, 
            appointment_id: uuid.UUID, 
            correlation_id: Optional[str] = None,
            ) -> Dict[str, Any]:
        return self._get_and_authorize(user_id, appointment_id, 'view')

    def list_appointments_by_patient(
        self,
        user_id: uuid.UUID,
        patient_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        correlation_id: Optional[str] = None,
    ):
        context = {'resource': {'patient_id': patient_id}}
        try:
            self.policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for patient {patient_id}", extra={"correlation_id": correlation_id})
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
        correlation_id: Optional[str] = None,
    ):
        context = {'resource': {'doctor_id': doctor_id}}
        try:
            self.policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for doctor {doctor_id}", extra={"correlation_id": correlation_id})
            raise
        limit = min(limit, self.MAX_LIST_LIMIT)
        return self.appointment_repo.get_appointments_by_doctor(doctor_id, from_date, to_date, limit, offset)