# services/audit_service.py
import uuid
import logging
from typing import Dict, Any, Tuple, Optional
import json

from database.queries.audit_repository import AuditRepository
from core.event_bus import get_event_bus
from services.feature_flag_service import get_feature_flag_service

logger = logging.getLogger(__name__)


class AuditService:
    """
        خدمة تسجيل العمليات (Audit Logging).
        - تتابع جميع الأحداث المهمة في النظام وتحفظها في قاعدة البيانات.
        - تستخدم Feature Flags للتحكم في تفعيل/تعطيل التسجيل.
        - توفر معالجات منفصلة لكل نوع حدث للوضوح والمرونة.
    """

    # خريطة الأحداث: (action, model_name, id_key)
    # تستخدم لتحديد نوع الإجراء والموديل والمفتاح المتعلق بالحدث
    _EVENT_MAP: Dict[str, Tuple[str, str, str]] = {
        'user.registered':          ('REGISTER',   'user',            'user_id'),
        'user.logged_in':           ('LOGIN',      'user',            'user_id'),
        'user.profile_updated':     ('UPDATE',     'user',            'user_id'),
        'appointment.created':      ('CREATE',     'appointment',     'appointment_id'),
        'appointment.confirmed':    ('CONFIRM',    'appointment',     'appointment_id'),
        'appointment.cancelled':    ('CANCEL',     'appointment',     'appointment_id'),
        'appointment.rescheduled':  ('RESCHEDULE', 'appointment',     'appointment_id'),
        'appointment.checked_in':   ('CHECK_IN',   'appointment',     'appointment_id'),
        'appointment.completed':    ('COMPLETE',   'appointment',     'appointment_id'),
        'appointment.no_show':      ('NO_SHOW',    'appointment',     'appointment_id'),
        'patient.profile_created':  ('CREATE',     'patient_profile', 'patient_id'),
        'patient.profile_updated':  ('UPDATE',     'patient_profile', 'patient_id'),
        'patient.profile_deleted':  ('SOFT_DELETE','patient_profile', 'patient_id'),
        'doctor.profile_created':   ('CREATE',     'doctor_profile',  'doctor_id'),
        'doctor.profile_updated':   ('UPDATE',     'doctor_profile',  'doctor_id'),
        'doctor.profile_deleted':   ('SOFT_DELETE','doctor_profile',  'doctor_id'),
        'visit_report.created':     ('CREATE',     'visit_report',    'report_id'),
        'visit_report.updated':     ('UPDATE',     'visit_report',    'report_id'),
    }

    # ================================================================
    # ثوابت التكوين
    # ================================================================
    AUDIT_LOGGING_FEATURE_FLAG = 'audit_logging_enabled'
    MAX_CHANGES_SIZE = 1000   # الحد الأقصى لطول سلسلة JSON للتغييرات

    def __init__(self, audit_repo: Optional[AuditRepository] = None, feature_flag_service=None):
        """
        إنشاء خدمة التسجيل.
        - audit_repo: مستودع التسجيل (يمكن حقنه للاختبار)
        - feature_flag_service: خدمة الميزات (يمكن حقنها للاختبار)
        """
        self.audit_repo = audit_repo or AuditRepository()
        self.feature_flags = feature_flag_service or get_feature_flag_service()
        self.event_bus = get_event_bus()
        self._register_handlers()

    def _register_handlers(self):
        """تسجيل معالجات الأحداث لكل نوع حدث معروف."""
        try:
            for event_name in self._EVENT_MAP:
                # استخدام closure لربط اسم الحدث مع المعالج
                handler = self._make_handler(event_name)
                self.event_bus.subscribe(event_name, handler)
            logger.info("AuditService handlers registered successfully")
        except Exception as e:
            logger.error(f"Failed to register audit handlers: {e}")

    def _make_handler(self, event_name: str):
        """
        إنشاء معالج خاص بنوع حدث معين.
        - يقضي على الحاجة لتمرير اسم الحدث عبر الـ payload.
        - كل معالج يعرف بالفعل اسم الحدث الخاص به.
        """
        def handler(payload: Dict[str, Any]) -> None:
            self._handle_event(event_name, payload)
        return handler

    def _handle_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """
        معالج الأحداث الرئيسي.
        - يتحقق من تفعيل Feature Flag قبل التسجيل.
        - يستخرج البيانات من الـ payload ويسجلها.
        """
        # 0. التحقق من تفعيل التسجيل عبر Feature Flag
        if not self.feature_flags.is_enabled(self.AUDIT_LOGGING_FEATURE_FLAG):
            logger.debug(f"Audit logging is disabled for event {event_name}")
            return

        # 1. البحث عن تكوين الحدث
        config = self._EVENT_MAP.get(event_name)
        if not config:
            logger.debug(f"No mapping for event '{event_name}'")
            return

        action, model_name, id_key = config

        # 2. استخراج معرف الكائن
        object_id = payload.get(id_key)
        if not object_id:
            logger.warning(f"Missing object ID key '{id_key}' for event '{event_name}'")

        # 3. تسجيل الحدث
        try:
            self._log(
                event_name=event_name,
                action=action,
                model_name=model_name,
                object_id=object_id,
                object_repr=f"{model_name} {object_id}" if object_id else None,
                user_id=payload.get('user_id'),
                ip=payload.get('ip'),
                user_agent=payload.get('user_agent'),
                changes=payload.get('changes'),
            )
        except Exception as e:
            logger.error(f"Failed to process audit event '{event_name}': {e}")

    def _log(
        self,
        event_name: str,
        action: str,
        model_name: str,
        object_id: Optional[uuid.UUID] = None,
        object_repr: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        user_id: Optional[uuid.UUID] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
            تسجيل حدث في audit_log.
            - يتعامل مع أي أخطاء في الكتابة بشكل آمن.
            - يحد من حجم حقل التغييرات إلى MAX_CHANGES_SIZE حرف.
        """
        # معالجة التغييرات لتجنب تخزين كميات كبيرة من البيانات
        if changes is not None:
            try:
                changes_json = json.dumps(changes, ensure_ascii=False, default=str)
                if len(changes_json) > self.MAX_CHANGES_SIZE:
                    logger.warning(
                        f"Changes for event '{event_name}' exceed size limit ({len(changes_json)} > {self.MAX_CHANGES_SIZE}), "
                        "storing truncated version"
                    )
                    changes = {
                        "truncated": True,
                        "original_size": len(changes_json),
                        "message": "Changes truncated due to size limit"
                    }
            except Exception as e:
                logger.error(f"Failed to serialize changes for event '{event_name}': {e}")
                changes = None

        try:
            self.audit_repo.create_audit_log(
                user_id=user_id,
                action=action,
                model_name=model_name,
                object_id=object_id,
                object_repr=object_repr,
                changes=changes,
                ip_address=ip,
                user_agent=user_agent,
            )
            logger.debug(f"Audit log created for event '{event_name}' (action={action}, model={model_name})")
        except Exception as e:
            logger.error(f"Failed to write audit log for event '{event_name}': {e}")