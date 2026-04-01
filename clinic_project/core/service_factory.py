# core/service_factory.py
import threading
from core.event_bus import get_event_bus
from core.policy_engine import policy_engine
from services.feature_flag_service import get_feature_flag_service
from services.user_service import UserService
from services.patient_service import PatientService
from services.doctor_service import DoctorService
from services.booking_service import BookingService
from services.visit_report_service import VisitReportService
from services.notification_service import NotificationService
from services.audit_service import AuditService

# قفل ومثيلات الخدمات التي يجب أن تكون مفردة (Singleton)
_lock = threading.Lock()
_instances = {}

def _singleton(key, factory):
    """إنشاء مثيل واحد للخدمات التي تحتاج إلى أن تكون مفردة."""
    if key not in _instances:
        with _lock:
            if key not in _instances:
                _instances[key] = factory()
    return _instances[key]

# ------------------------------------------------------------------
# خدمات عادية – يتم إنشاء مثيل جديد لكل طلب (لا تحتوي على حالة)
# ------------------------------------------------------------------
def get_user_service():
    return UserService()

def get_patient_service():
    return PatientService()

def get_doctor_service():
    return DoctorService()

def get_booking_service():
    return BookingService(
        feature_flag_service=get_feature_flag_service()
    )

def get_visit_report_service():
    return VisitReportService()

# ------------------------------------------------------------------
# خدمات تحتاج إلى مثيل واحد (تسجل في EventBus، أو تحتفظ بحالة)
# ------------------------------------------------------------------
def get_notification_service():
    return _singleton('notification', NotificationService)

def get_audit_service():
    return _singleton('audit', AuditService)