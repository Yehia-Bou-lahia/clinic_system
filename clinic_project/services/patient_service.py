import uuid
import logging
from datetime import date
from typing import Optional, Dict, Any, List

from database.connection import db
from database.queries.patient_repository import PatientRepository, ALLOWED_UPDATE_FIELDS
from database.queries.user_repository import UserRepository
from database.queries.appointment_repository import AppointmentRepository
from core.policy_engine import policy_engine
from core.event_bus import get_event_bus
from core.exceptions import (
    PatientNotFoundError,
    PatientProfileAlreadyExistsError,
    PermissionDenied,
    UserNotFoundError,
)

logger = logging.getLogger(__name__)

ALLOWED_BLOOD_TYPES = {'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'}
MAX_LIST_LIMIT = 100


class PatientService:
    def __init__(self):
        self.patient_repo = PatientRepository()
        self.user_repo = UserRepository()
        self.appointment_repo = AppointmentRepository()
        self.event_bus = get_event_bus()

    # ========================================
    # دوال مساعدة (validation)
    # ========================================
    @staticmethod
    def _validate_date_of_birth(dob: date) -> None:
        if dob > date.today():
            raise ValueError("Date of birth cannot be in the future")

    @staticmethod
    def _validate_blood_type(blood_type: Optional[str]) -> None:
        if blood_type and blood_type not in ALLOWED_BLOOD_TYPES:
            raise ValueError(f"Invalid blood type. Allowed: {', '.join(ALLOWED_BLOOD_TYPES)}")

    # ========================================
    # الطرق العامة
    # ========================================
    def create_patient_profile(
        self,
        user_id: uuid.UUID,
        date_of_birth: date,
        blood_type: Optional[str] = None,
        emergency_contact_name: Optional[str] = None,
        emergency_contact: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        chronic_diseases: Optional[str] = None,
        allergies: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 1. التحقق من وجود المستخدم
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # 2. التحقق من الصلاحية
        policy_engine.enforce(user_id, 'create', 'patient_profile')

        # 3. التحقق من صحة المدخلات
        self._validate_date_of_birth(date_of_birth)
        self._validate_blood_type(blood_type)

        # 4. إستخدام معاملة لضمان الدرية  (نشر الحدث بعد ال commit)
        with db.get_connection() as conn:
            try:
                patient = self.patient_repo.create_patient_profile(
                    user_id = user_id,
                    date_of_birth = date_of_birth,
                    blood_type = blood_type,
                    emergency_contact_name = emergency_contact_name,
                    emergency_contact = emergency_contact,
                    address = address,
                    city = city,
                    chronic_diseases = chronic_diseases,
                    allergies = allergies,
                    conn = conn # تمرير -> الاتصال
                )
            except PatientNotFoundError as e:
                logger.warning(f"Patient profile creation failed: {e}")
                raise
            # المعاملة ستلتزم تلقائياً عند الخروج من with (إذا لم يحدث خطأ)
        # بعد نجاح المعاملة، ننشر الحدث
        self.event_bus.publish('patient_profile_created', {
            'user_id': user_id,
            'patient_id': patient['id'],
        })
        logger.info(f"Patient profile created for user {user_id}")
        return patient
    
    def get_patient_by_id(
            self,
            request_id: uuid.UUID,
            patient_id: uuid.UUID,
    ) -> Dict[str, Any]:
        # 1. جلب المريض أولا للتحقق من وجوده وللسياق الكامل
        patient = self.patient_repo.get_patient_by_id(patient_id)
        if not patient:
            raise PatientNotFoundError(f"Patient {patient_id} not found")
        
        # 2. التحقق من الصلاحية بإستخدام الكائن الكامل
        policy_engine.enforce(request_id, 'view', 'patient_profile', context = {'patient': patient})
        return patient
    
    def update_patient_profile(
        self,
        request_id: uuid.UUID,
        patient_id: uuid.UUID,
        **fileds,
    ) -> Dict[str, Any]:
        # 1. جلب القديم للتحقق من وجوده وللسياق
        old_patient = self.patient_repo.get_patient_by_id(patient_id)
        if not old_patient:
            raise PatientNotFoundError(f"Patient {patient_id} not found")
        
        # 2. التحقق من الصلاحية 
        policy_engine.enforce(request_id, 'update', 'patien_profile', context = {'resource': old_patient})

        # 3. بناء بيانات التحديث بإستخدام ALLOWED_UPDATE_FIELDS FROM patient_repository
        update_data = {}
        for key, value in fileds.items():
            if key in ALLOWED_UPDATE_FIELDS:
                raise ValueError(f"Invalid field: {key}")
            if key == 'date_of_birth':
                self._validate_date_of_birth(value)
            elif key == 'blood_type':
                self._validate_blood_type(value)
            update_data[key] = value

        if not update_data:
            return old_patient  # لا يوجد تحديثات، نعيد القديم 
        
        # 4. تحديث الملف (لا يحتاج معاملة منفصلة لأنه عملية واحدة)
        updated = self.patient_repo.update_patient_profile(patient_id, **update_data)

        #5 . نشر الحدث بعد التحديث
        self.event_bus.publish('patient_profile_updated', {
            'user_id': request_id,
            'patient_id': patient_id,
            'updated_fields': list(update_data.keys()),
        })
        logger.info(f"Patient profile {patient_id} updated by user {request_id}")
        return updated
    
    def soft_delete_patient_profile(
        self,
        request_id: uuid.UUID,
        patient_id: uuid.UUID,
    ) -> bool:
        # 1. جلب الملف للسياق
        patient = self.patient_repo.get_patient_by_id(patient_id)
        if not patient:
            raise PatientNotFoundError(f"Patient {patient_id} not found")
        
        # 2. التحقق من الصلاحية
        policy_engine.enforce(request_id, 'soft_delete', 'patient_profile', context = {'resource' : patient})

        # 3. التحقق من عدم وجود مواعيد مستقبلية نشطة
        active_count = self.appointment_repo.count_future_by_patient_id(patient_id)
        if active_count > 0:
            raise ValueError("Cannot delete patient with active appointments")
        
        # 4. تنفيد الحدف المنطقي
        deleted = self.patient_repo.soft_delete_patient_profile(patient_id)
        if deleted:
            self.event_bus.publish('patient_profile_deleted', {
                'user_id': request_id,
                'patient_id': patient_id,
            })
            logger.info(f"Patient profile {patient_id} soft-deleted by user {request_id}")
        return deleted
    
    def list_patients(
            self,
            request_id: uuid.UUID,
            limit: int = 20,
            offset: int = 0,
            include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        
        # 1. التحقق من صلاحية القائمة الأساسية
        policy_engine.enforce(request_id, 'list', 'patient_profiles')

        # 2. فرض الحد الأقصى لل
        limit = min(limit, MAX_LIST_LIMIT)

        # 3. جلب البيانات (مع صلاحية  إضافية للمحدوفين)
        if include_deleted:
            policy_engine.enforce(request_id, 'list_deleted', 'patient_profiles')
            patients = self.patient_repo.list_all_patients(limit, offset)
        else:
            patients = self.patient_repo.list_active_patients(limit, offset)

        return patients
    
    