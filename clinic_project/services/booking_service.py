import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from database.queries.appointment_repository import AppointmentRepository
from database.queries.doctor_repository import DoctorRepository
from database.queries.patient_repository import PatientRepository
from core.policy_engine import policy_engine
from core.event_bus import EventBus
from core.exceptions import (
    DoctorNotAvailableError,
    BookingLimitError,
    PermissionDenied,
    AppointmentNotFoundError,
    InvalidAppointmentStatusError,
    )

logger = logging.getLogger(__name__)

class BookingService:
    """
        خدمة إدارة المواعيد (الحجز، الإلغاء، التأكيد، إعادة الجدولة).
        تستخدم PolicyEngine للتحقق من الصلاحيات و EventBus لنشر الأحداث.
    """

    def __init__(self):
        self.appointment_repo = AppointmentRepository()
        self.doctor_repo = DoctorRepository()
        self.patient_repo = PatientRepository()
        self.event_bus = EventBus() # singleton

        #++++++++++++++++++++++++++++++++++++++
        # الدوال الرئيسية
        #++++++++++++++++++++++++++++++++++++++

    def book_appointment(
            self,
            user_id: uuid.UUID,
            patient_id: uuid.UUID,
            doctor_id: uuid.UUID,
            appointment_datetime: datetime,
            notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """حجز موعد جديد:
            - التحقق من صلاحيات المستخدم (المريض أو الموظف).
            - التحقق من توفر الطبيب في الوقت المحدد.
            - التحقق من عدم تجاوز حد الحجز اليومي للمريض.
            - إنشاء الموعد في قاعدة البيانات.
            - نشر حدث "AppointmentBooked" مع تفاصيل الموعد.
        """
        # 1. صلاحية
        try:
            policy_engine.enforce(user_id, 'create_appointment', 'appointment')
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
            logger.info(f"Patient {patient_id} has reached daily booking limit({pending_count} pending)")
            raise BookingLimitError("You have reached the daily bookin limit of 3 pending appointments")
        
        # 4. إنشاء الموعد
        appointment = self.appointment_repo.create_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            appointment_datetime=appointment_datetime,
            notes=notes
        )
        # 5. نشر الحدث
        self.event_bus.publish('appointment.created', {
            'appointment_id': appointment['id'],
            'patient_id': patient_id,
            'doctor_id': doctor_id,
            'datetime': appointment_datetime.isoformat(),
            'user_id': user_id,
            'notes': notes,
        })
        logger.info(f"Appointment {appointment['id']} created by user {user_id}")
        return appointment
    
    def confirm_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
            تأكيد الموعد (يجب أن يكون حالته PENDING).
            بعد التأكيد، يصبح CONFIRMED.
        """
        #1. جلب الموعد للتحقق من ملكيته(يمكن تمريره في السياق لل policey_engine)
        appointmet = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointmet:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")
        
        #2. صلاحية: يمكن للمريض او الطبيب او الموظف تأكيد الموعد
        # نمرر السياق مع الموعد لتقييم شروط مثل is_own_patient or is_assigned_doctor
        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'confirm_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to confirm appointment {appointment_id}: {e}")
            raise

        #3. التأكيد
        updated = self.appointment_repo.confirm_appointment(appointment_id)

        #4. نشر الحدث
        self.event_bus.publish('appointment.confirmed',{
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
            cancelled_by: str, # 'patient', 'doctor', 'reception'
    ) -> Dict[str, Any]:
        """
            إلغاء الموعد:
            - cancelled_by:من قام بالإلغاء (يستخدم لتحديد الحالة النهائية)
            - يجب أن لا يكون الموعد مكتملاً أو مسجلاً كـ NO_SHOW
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")
        
        # صلاحية: يمكن للمريض او الطبيب او الموظف إلغاء الموعد
        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'cancel_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to cancel appointment {appointment_id}: {e}")
            raise
        # تنفيذ الإلغاء (الـ Repository يقوم بالتحقق من الحالة المسموح إلغاؤها)
        cancelled = self.appointment_repo.cancel_appointment(appointment_id, reason, cancelled_by)
        # نشر الحدث
        self.event_bus.publish('appointment.cancelled',{
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
            reason: str
    ) -> Dict[str, Any]:
        """
            إعادة جدولة الموعد (تغيير الوقت).
                - يجب أن يكون الموعد في حالة PENDING أو CONFIRMED.
                - يجب أن يكون الوقت الجديد متاحاً للطبيب
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment with id {appointment_id} not found")
        
        # صلاحية اعادة الجدولة
        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'reschedule_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to reschedule appointment {appointment_id}: {e}")
            raise

        # التحقق من توفر الطبيب في الوقت الجديد
        if not self.doctor_repo.is_available(appointment['doctor_id'], new_datetime):
            raise DoctorNotAvailableError(f"Doctor {appointment['doctor_id']} is not available at {new_datetime}")
        
        # تنفيذ إعادة الجدولة
        updated = self.appointment_repo.reschedule_appointment(appointment_id, new_datetime)

        # نشر الحدث
        self.event_bus.publish('appointment.rescheduled',{
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
        """
            تسجيل وصول المريض (يقوم به موظف الاستقبال أو الطبيب).
            يجب أن يكون الموعد في حالة CONFIRMED.
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'check_in', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to check-in appointment {appointment_id}: {e}")
            raise

        updated  = self.appointment_repo.check_in(appointment_id)
        self.event_bus.publish('appointment.checked_in',{
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} checked-in by user {user_id}")

        return updated
    
    def complete_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
            إكمال الموعد (يقوم به الطبيب بعد انتهاء الاستشارة).
            يجب أن يكون الموعد في حالة IN_PROGRESS.
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")
        
        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'complete_appointment', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to complete appointment {appointment_id}: {e}")
            raise
        updated = self.appointment_repo.complete_appointment(appointment_id)

        self.event_bus.publish('appointment.completed',{
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} completed by user {user_id}")

        return updated

    def mark_no_show(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
            تسجيل عدم حضور المريض (NO_SHOW).
            يمكن أن يقوم به موظف الاستقبال أو الطبيب بعد وقت الموعد إذا لم يحضر المريض.
            يجب أن يكون الموعد في حالة CONFIRMED.
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")
        
        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'mark_no_show', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to mark no-show for appointment {appointment_id}: {e}")
            raise
        updated = self.appointment_repo.mark_no_show(appointment_id)

        self.event_bus.publish('appointment.no_show',{
            'appointment_id': appointment_id,
            'patient_id': updated['patient_id'],
            'doctor_id': updated['doctor_id'],
            'datetime': updated['appointment_datetime'].isoformat(),
            'user_id': user_id,
        })
        logger.info(f"Appointment {appointment_id} marked as no-show by user {user_id}")

        return updated
    
    def get_appointment(self, user_id: uuid.UUID, appointment_id: uuid.UUID) -> Dict[str, Any]:
        """
        جلب بيانات موعد معين (مع التحقق من صلاحية الوصول).
        """
        appointment = self.appointment_repo.get_appointment_by_id(appointment_id)
        if not appointment:
            raise AppointmentNotFoundError(f"Appointment {appointment_id} not found")

        context = {'resource': appointment}
        try:
            policy_engine.enforce(user_id, 'view', 'appointment', context)
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
        """
        جلب مواعيد مريض معين (مع التحقق من الصلاحية: المريض نفسه أو طبيبه أو موظف).
        """
        # نمرر patient_id في السياق لسياسات مثل is_own_patient أو is_for_patient
        context = {'resource': {'patient_id': patient_id}}
        try:
            policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for patient {patient_id}: {e}")
            raise

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
        """
        جلب مواعيد طبيب معين (مع التحقق من الصلاحية: الطبيب نفسه أو موظف/مدير).
        """
        context = {'resource': {'doctor_id': doctor_id}}
        try:
            policy_engine.enforce(user_id, 'view', 'appointment', context)
        except PermissionDenied as e:
            logger.warning(f"User {user_id} denied to view appointments for doctor {doctor_id}: {e}")
            raise

        return self.appointment_repo.get_appointments_by_doctor(
            doctor_id, from_date, to_date, limit, offset
        )
            