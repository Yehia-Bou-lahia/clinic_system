# services/doctor_service.py
import uuid
import logging
from typing import Optional, Dict, Any, List

from database.connection import db
from database.queries.doctor_repository import DoctorRepository, ALLOWED_UPDATE_FIELDS as DOCTOR_ALLOWED_UPDATE_FIELDS
from database.queries.user_repository import UserRepository
from database.queries.appointment_repository import AppointmentRepository
from core.policy_engine import policy_engine
from core.event_bus import get_event_bus
from core.exceptions import (
    DoctorNotFoundError,
    DuplicateLicenseError,
    PermissionDenied,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)

MAX_LIST_LIMIT = 100


class DoctorService:
    def __init__(self):
        self.doctor_repo = DoctorRepository()
        self.user_repo = UserRepository()
        self.appointment_repo = AppointmentRepository()   # ← للتحقق من المواعيد
        self.event_bus = get_event_bus()

    # ========================================
    # دوال مساعدة (validation)
    # ========================================
    @staticmethod
    def _validate_consultation_fee(fee: float) -> None:
        if fee < 0:
            raise ValueError("Consultation fee cannot be negative")

    @staticmethod
    def _validate_years_experience(years: int) -> None:
        if years < 0:
            raise ValueError("Years of experience cannot be negative")

    # ========================================
    # الطرق العامة
    # ========================================
    def create_doctor_profile(
        self,
        user_id: uuid.UUID,
        specialty: str,
        license_number: str,
        consultation_fee: float,
        sub_specialty: Optional[str] = None,
        years_experience: int = 0,
        is_active: bool = True,
    ) -> Dict[str, Any]:
        """
        إنشاء ملف طبيب جديد لمستخدم موجود.
        """
        # 1. التحقق من وجود المستخدم
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(user_id, 'create', 'doctor_profile')

        # 3. التحقق من صحة المدخلات
        self._validate_consultation_fee(consultation_fee)
        self._validate_years_experience(years_experience)

        # 4. استخدام معاملة لضمان الذرية
        with db.get_connection() as conn:
            try:
                doctor = self.doctor_repo.create_doctor_profile(
                    user_id=user_id,
                    specialty=specialty,
                    license_number=license_number,
                    consultation_fee=consultation_fee,
                    sub_specialty=sub_specialty,
                    years_experience=years_experience,
                    is_active=is_active,
                    conn=conn,   # ← تمرير الاتصال
                )
            except DuplicateLicenseError as e:
                logger.warning(f"Doctor profile creation failed: {e}")
                raise

        # بعد نجاح المعاملة، نشر الحدث
        self.event_bus.publish('doctor.profile_created', {
            'user_id': user_id,
            'doctor_id': doctor['id'],
        })
        logger.info(f"Doctor profile created for user {user_id}")
        return doctor

    def get_my_doctor_profile(self, user_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """
        جلب ملف الطبيب الخاص بالمستخدم الحالي.
        """
        return self.doctor_repo.get_doctor_by_user_id(user_id)

    def get_doctor_by_id(
        self,
        requester_id: uuid.UUID,
        doctor_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        جلب ملف طبيب بواسطة معرفه (مع التحقق من الصلاحية).
        """
        # 1. جلب الطبيب أولاً للتحقق من وجوده وللسياق الكامل
        doctor = self.doctor_repo.get_doctor_by_id(doctor_id)
        if not doctor:
            raise DoctorNotFoundError(f"Doctor {doctor_id} not found")

        # 2. التحقق من الصلاحية باستخدام الكائن الكامل
        policy_engine.enforce(requester_id, 'view', 'doctor_profile', context={'resource': doctor})
        return doctor

    def update_doctor_profile(
        self,
        requester_id: uuid.UUID,
        doctor_id: uuid.UUID,
        **fields,
    ) -> Dict[str, Any]:
        """
        تحديث ملف طبيب.
        الحقول المسموحة محددة في DoctorRepository.ALLOWED_UPDATE_FIELDS.
        """
        # 1. جلب الملف القديم للتحقق من وجوده وللسياق
        old_doctor = self.doctor_repo.get_doctor_by_id(doctor_id)
        if not old_doctor:
            raise DoctorNotFoundError(f"Doctor {doctor_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(requester_id, 'update', 'doctor_profile', context={'resource': old_doctor})

        # 3. بناء بيانات التحديث باستخدام القائمة من الـ Repository
        update_data = {}
        for key, value in fields.items():
            if key not in DOCTOR_ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            if key == 'consultation_fee':
                self._validate_consultation_fee(value)
            elif key == 'years_experience':
                self._validate_years_experience(value)
            update_data[key] = value

        if not update_data:
            return old_doctor

        # 4. تحديث الملف (لا يحتاج معاملة منفصلة)
        updated = self.doctor_repo.update_doctor_profile(doctor_id, **update_data)

        # 5. نشر حدث
        self.event_bus.publish('doctor.profile_updated', {
            'user_id': requester_id,
            'doctor_id': doctor_id,
            'updated_fields': list(update_data.keys()),
        })
        logger.info(f"Doctor profile {doctor_id} updated by user {requester_id}")
        return updated

    def soft_delete_doctor_profile(
        self,
        requester_id: uuid.UUID,
        doctor_id: uuid.UUID,
    ) -> bool:
        """
        حذف منطقي لملف الطبيب (يتطلب صلاحية إدارية).
        يتحقق من عدم وجود مواعيد مستقبلية نشطة.
        """
        # 1. جلب الملف للسياق
        doctor = self.doctor_repo.get_doctor_by_id(doctor_id)
        if not doctor:
            raise DoctorNotFoundError(f"Doctor {doctor_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(requester_id, 'soft_delete', 'doctor_profile', context={'resource': doctor})

        # 3. التحقق من عدم وجود مواعيد مستقبلية نشطة
        active_count = self.appointment_repo.count_future_by_doctor(doctor_id)
        if active_count > 0:
            raise ValueError("Cannot delete doctor with active appointments")

        # 4. تنفيذ الحذف المنطقي
        deleted = self.doctor_repo.soft_delete_doctor_profile(doctor_id)
        if deleted:
            self.event_bus.publish('doctor.profile_deleted', {
                'user_id': requester_id,
                'doctor_id': doctor_id,
            })
            logger.info(f"Doctor profile {doctor_id} soft-deleted by user {requester_id}")
        return deleted

    def list_doctors(
        self,
        requester_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        جلب قائمة الأطباء (للاستخدام الإداري).
        - limit: عدد النتائج (لا يتجاوز MAX_LIST_LIMIT)
        - include_deleted: عرض الأطباء المحذوفين أيضاً (يتطلب صلاحية خاصة)
        """
        # 1. التحقق من صلاحية القائمة الأساسية
        policy_engine.enforce(requester_id, 'list', 'doctor_profile')

        # 2. فرض الحد الأقصى للـ limit
        limit = min(limit, MAX_LIST_LIMIT)

        # 3. جلب البيانات (مع صلاحية إضافية للمحذوفين)
        if include_deleted:
            policy_engine.enforce(requester_id, 'list_deleted', 'doctor_profile')
            doctors = self.doctor_repo.list_all_doctors(limit, offset)
        else:
            doctors = self.doctor_repo.list_active_doctors(limit, offset)

        return doctors