import uuid
import logging
from typing import Dict, Any, Optional

from database.queries.notification_repository import NotificationRepository
from database.queries.user_repository import UserRepository
from database.queries.patient_repository import PatientRepository
from database.queries.doctor_repository import DoctorRepository
from core.event_bus import get_event_bus
from core.policy_engine import policy_engine
from services.feature_flag_service import get_feature_flag_service   # ← إضافة
from core.exceptions import FeatureDisabledError                     # ← إضافة (للاستخدام المستقبلي)

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, feature_flag_service=None):
        self.notification_repo = NotificationRepository()
        self.user_repo = UserRepository()
        self.patient_repo = PatientRepository()
        self.doctor_repo = DoctorRepository()
        self.event_bus = get_event_bus()
        self.feature_flags = feature_flag_service or get_feature_flag_service()   # ← إضافة

        self._register_handlers()

    def _register_handlers(self):
        """تسجيل معالجات الأحداث (فقط تلك التي لديها منطق)."""
        self.event_bus.subscribe('appointment.created', self._on_appointment_created)
        self.event_bus.subscribe('user.registered', self._on_user_registered)
        # الأحداث الأخرى ستُضاف لاحقاً عند كتابة معالجاتها

    # ========================================
    # مساعدات داخلية
    # ========================================
    def _send_notification(
        self,
        user_id: uuid.UUID,
        notification_type: str,   # 'email', 'push', 'sms'
        title: str,
        message: str,
        related_to: Optional[str] = None,
        related_id: Optional[uuid.UUID] = None,
    ) -> None:
        """تخزين الإشعار في قاعدة البيانات وإرساله فعلياً."""
        # 0. التحقق من تفعيل نوع الإشعار عبر Feature Flag
        flag_name = f"{notification_type}_notifications"   # مثلاً: email_notifications, push_notifications, sms_notifications
        if not self.feature_flags.is_enabled(flag_name):
            logger.debug(f"Notification type {notification_type} is disabled via feature flag")
            return

        # 1. تخزين في قاعدة البيانات
        try:
            self.notification_repo.create_notification(
                user_id=user_id,
                type=notification_type,
                title=title,
                message=message,
                related_to=related_to,
                related_id=related_id,
            )
        except Exception as e:
            logger.error(f"Failed to store notification for user {user_id}: {e}")
            return

        # 2. إرسال الإشعار الفعلي (محاكاة – يمكن استبداله بمزود حقيقي)
        logger.info(f"[MOCK] Sending {notification_type} to user {user_id}: {title} - {message}")

    def _get_user_preferences(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """جلب تفضيلات الإشعارات (افتراضيات إن لم توجد)."""
        prefs = self.notification_repo.get_preferences(user_id)
        if not prefs:
            return {
                'email_enabled': True,
                'push_enabled': True,
                'sms_enabled': False,
                'quiet_hours_start': None,
                'quiet_hours_end': None,
                'notify_before_appointment': 60,
            }
        return prefs

    # ========================================
    # معالجات الأحداث
    # ========================================
    def _on_appointment_created(self, payload: Dict[str, Any]) -> None:
        """
        عند إنشاء موعد جديد – إرسال إشعار للمريض والطبيب.
        يفترض أن الـ payload يحتوي على:
        - appointment_id, patient_id, patient_user_id, doctor_id, doctor_user_id, datetime
        """
        patient_user_id = payload.get('patient_user_id')
        doctor_user_id = payload.get('doctor_user_id')
        appointment_id = payload.get('appointment_id')
        datetime_str = payload.get('datetime', '')

        if not patient_user_id or not doctor_user_id:
            logger.error(f"Missing user IDs in appointment.created payload: {payload}")
            return

        # رسائل الإشعارات
        patient_title = "موعد جديد"
        patient_msg = f"تم إنشاء موعدك في {datetime_str}. يرجى تأكيده خلال 24 ساعة."

        doctor_title = "موعد جديد"
        doctor_msg = f"لديك موعد جديد مع المريض في {datetime_str}."

        # التحقق من تفضيلات المريض
        patient_prefs = self._get_user_preferences(patient_user_id)
        if patient_prefs.get('email_enabled'):
            self._send_notification(
                user_id=patient_user_id,
                notification_type='email',
                title=patient_title,
                message=patient_msg,
                related_to='appointment',
                related_id=appointment_id,
            )
        if patient_prefs.get('push_enabled'):
            self._send_notification(
                user_id=patient_user_id,
                notification_type='push',
                title=patient_title,
                message=patient_msg,
                related_to='appointment',
                related_id=appointment_id,
            )

        # التحقق من تفضيلات الطبيب
        doctor_prefs = self._get_user_preferences(doctor_user_id)
        if doctor_prefs.get('email_enabled'):
            self._send_notification(
                user_id=doctor_user_id,
                notification_type='email',
                title=doctor_title,
                message=doctor_msg,
                related_to='appointment',
                related_id=appointment_id,
            )

    def _on_user_registered(self, payload: Dict[str, Any]) -> None:
        """عند تسجيل مستخدم جديد – إرسال بريد ترحيبي إذا كان مفعلاً."""
        user_id = payload.get('user_id')
        if not user_id:
            return

        prefs = self._get_user_preferences(user_id)
        if prefs.get('email_enabled'):
            self._send_notification(
                user_id=user_id,
                notification_type='email',
                title="مرحباً بك",
                message="شكراً لتسجيلك في نظام العيادة. يمكنك الآن حجز المواعيد.",
            )