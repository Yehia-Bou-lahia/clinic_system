import uuid
import time 
import logging
import threading
from datetime import date, datetime
from functools import lru_cache
from typing import Dict, Any, Optional, List, Tuple, Callable

from database.connection import db
from core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

class PolicyEngine:

    """
    محرك صلاحيات آمن – يستخدم معالجات شروط محددة مسبقًا (لا تنفيذ كود).
    يدعم TTL للـ cache لتجنب بقاء القواعد القديمة.
    """
    CACHE_TTL = 300 # 5 دقائق   
    USER_ROLE_CACHE_TTL = 300
    
    def __init__(self):
        self._cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}  # cache format: {user_id: (rules, timestamp)}
        self._cache_lock = threading.RLock()# لضمان سلامة الوصول إلى الكاش في بيئة متعددة الخيوط
        #تخزين مؤقت لدور المستخدم معTTL
        self._user_role_cache: Dict[str, Tuple[uuid.UUID, float]] = {}
        self._user_role_lock = threading.RLock()

        # تعريف معالجات الشروط المسموح بها مسبقًا    
    _condition_handlers: Dict[str, Callable[[Dict[str, Any]], bool]] = {
        # المريض يرى ملفه الخاص فقط
        "is_own_patient": lambda ctx: _is_own_patient(ctx),
        # الطبيب يرى ملفات المرضى الذين تم تعيينهم له فقط   
        "is_assigned_doctor": lambda ctx: _is_assigned_doctor(ctx),
        # الممرض يرى ملفات المرضى في نفس القسم فقط
        "is_today_only": lambda ctx: _is_today_only(ctx),
        #يتحقق مما إذا كان المورد مرتبطاً بمريض معين (أي أن للمورد حقل patient_id)، دون مقارنته مع المستخدم.
        "is_for_patient": lambda ctx: _is_for_patient(ctx),
        #يتحقق مما إذا كان المورد مرتبطاً بمريض معين (أي أن للمورد حقل patient_id) وأن تاريخ الوصول هو في المستقبل فقط.
        "is_future_only": lambda ctx: _is_future_only(ctx),  # تم تصحيح الاسم
        "is_any": lambda ctx: True,  # شرط عام يسمح بالوصول دائماً (يمكن استخدامه كقاعدة افتراضية)   
    }

    #---------------------------------
    #  طرق خاصة
    #---------------------------------
    def _get_user_role(self, user_id: uuid.UUID) -> Optional[uuid.UUID]:
        """
            جلب دور المستخدم من قاعدة البيانات مع تخزين مؤقت.
        """
        cache_key = str(user_id)
        now = time.time()
        with self._user_role_lock:
            if cache_key in self._user_role_cache:
                role_id, timestamp = self._user_role_cache[cache_key]
                if now - timestamp < self.USER_ROLE_CACHE_TTL:
                    return role_id  # إرجاع الدور من الكاش إذا كان صالحاً
                
        with db.get_cursor() as cursor:
            cursor.execute("SELECT role_id FROM users WHERE id = %s", (user_id,))
            row = cursor.fetchone()
            role_id = row['role_id'] if row else None  
            
        with self._user_role_lock:
            if role_id is not None:
                self._user_role_cache[cache_key] = (role_id, now)
        return role_id
        
    def _get_cache_key(self, role_id: uuid.UUID, action: str, resource: str) -> str:
        return f"{role_id}:{action}:{resource}"
    
    def _load_policies(self, role_id: uuid.UUID, action: str, resource: str) -> List[Dict[str, Any]]:
        """
            تحميل السياسات من قاعدة البيانات مع TTL Cache.
        """
        cache_key = self._get_cache_key(role_id, action, resource)
        now = time.time()

        with self._cache_lock:
            if cache_key in self._cache:
                policies, timestamp = self._cache[cache_key]
                if now - timestamp < self.CACHE_TTL:
                    return policies  # إرجاع السياسات من الكاش إذا كانت صالحة   
        
        #إستعلام من قاعدة البيانات 
        with db.get_cursor() as cursor:
            cursor.execute("""
                SELECT effect, condition, priority
                FROM policies
                WHERE role_id = %s AND action = %s AND resource = %s AND is_active = true
                ORDER BY priority DESC
            """, (role_id, action, resource))
            rows = cursor.fetchall()
            policies = [dict(row) for row in rows]

        with self._cache_lock:
            self._cache[cache_key] = (policies, now)
        return policies
    
    def _evaluate_condition(self, condition: Optional[str], context: Dict[str, Any]) -> bool:  # تم تصحيح النوع
        """
        تقييم الشرط باستخدام المعالجات المحددة مسبقًا.
        إذا لم يوجد الشرط -> False (رفض آمن).
        إذا كان الشرط غير معروف -> False (رفض آمن)
        """
        if not condition:
            # لا يوجد شرط -> رفض (القاعدة الذهبية)
            logger.debug("Condition is empty -> denied (secure default)")
            return False
        handler = self._condition_handlers.get(condition)
        if handler is None:
            # شرط غير معروف -> رفض آمن
            logger.error(f"Unknown condition handler: '{condition}'")
            return False
        
        try:
            return handler(context)
        except Exception as e:
            logger.error(f"Condition handler '{condition}' failed: {e}")
            return False
        
    #---------------------------------
    #  الطرق العامة
    #---------------------------------
    def can(self,
            user_id: uuid.UUID,
            action: str,
            resource: str,
            context: Optional[Dict[str, Any]] = None) -> bool:
        """
            تحديد ما إذا كان المستخدم يملك صلاحية لتنفيذ action على resource.
            يمكن تمرير سياق إضافي (مثل كائن المورد) لتقييم الشروط.
        """
        #1. جلب دور المستخدم مع تخزين مؤقت(cache)
        role_id = self._get_user_role(user_id)
        if not role_id:
            logger.debug(f"User {user_id} has no role -> denied")
            return False    
        
        #2. جلب السياسات من قاعدة البيانات مع تخزين مؤقت(cache) 
        policies = self._load_policies(role_id, action, resource)

        #3. تجهيز السياق الكامل
        full_context = {
            'user': {'id': user_id, 'role_id': role_id},
            'resource': context or {}
        }
        #4. تقييم السياسات حسب الأولوية
        for policy in policies:
            condition = policy.get('condition')
            if self._evaluate_condition(condition, full_context):
                effect = policy['effect']
                logger.debug(f"User {user_id} (role {role_id}) {action} {resource} -> {effect} (condition = {condition})")
                if effect == 'allow':
                    return True
                elif effect == 'deny':
                    return False
                    # أي effect آخر غير متوقع نكمل
        #5. إذا لم تطابق أي سياسة -> رفض آمن
        logger.debug(f"User {user_id} (role {role_id}) {action} {resource} -> DENIED (no matching policy)")
        return False
    
    def enforce(self,
                user_id: uuid.UUID,
                action: str,
                resource: str,
                context:  Optional[Dict[str, Any]] = None) -> None:
        """ رفع الإستثناء إدا لم تكن الصلاحية متاحة"""
        if not self.can(user_id, action, resource, context):
            raise PermissionDenied(f"User {user_id} is not allowed to {action} on {resource}")
        
    def invalidate_cache(self, role_id: Optional[uuid.UUID] = None) -> None:
        """ إلغاء صلاحية الكاش لسياسات دور معين أو للجميع """
        with self._cache_lock:
            if role_id is None:
                self._cache.clear()
                logger.info("Policy cache cleared entirely.")
            else:
                keys_to_delete = [k for k in self._cache if k.startswith(f"{role_id}:")]
                for key in keys_to_delete:
                    del self._cache[key]
                logger.info(f"PolicyEngine cache cleared for role_id {role_id}.")

    def invalidate_user_role_cache(self,  user_id: Optional[uuid.UUID] = None) -> None:
        """ إلغاء صلاحية الكاش لدور مستخدم معين أو للجميع """
        with self._user_role_lock:
            if user_id is None:
                self._user_role_cache.clear()
                logger.info("User role cache cleared entirely.")
            else:
                self._user_role_cache.pop(str(user_id), None)
                logger.info(f"User role cache cleared for user {user_id}.")


#------------------------------------------------    
# وظائف مساعدة للمعالجات (تعريفها خارج الكلاس لتجنب القيود)
#------------------------------------------------
def _is_own_patient(context: Dict[str, Any]) -> bool:
    """ الشرط:المستخدم هو المريض نفسه"""
    user = context.get('user', {})
    resource = context.get('resource', {})
    return user.get('id') == resource.get('patient_id')

def _is_assigned_doctor(context: Dict[str, Any]) -> bool:
    """الشرط:المستخدم هو الطبيب المعالج"""
    user = context.get('user', {})
    resource = context.get('resource', {})
    return user.get('id') == resource.get('doctor_id')

def _is_today_only(context: Dict[str, Any]) -> bool:
    """
        الشرط: التاريخ في المورد يساوي تاريخ اليوم.
        ملاحظة: إذا لم يكن هناك مورد، نرفض (لأنه لا يمكن التحقق).
        يجب تمرير مورد يحتوي على appointment_datetime.
    """
    resource = context.get('resource')
    if not resource:
        return False
    
    appt_datetime = resource.get('appointment_datetime')
    if not appt_datetime:
        return False
    
    # توحيد المتغير لتخزين التاريخ
    if isinstance(appt_datetime, str):
        try:
            appt_date = datetime.fromisoformat(appt_datetime).date()
        except ValueError:
            return False
    elif isinstance(appt_datetime, datetime):
        appt_date = appt_datetime.date()
    else:
        return False
    
    today = date.today()
    return appt_date == today

def _is_for_patient(context: Dict[str, Any]) -> bool:
    """الشرط: المورد يحتوي على patient_id (اي انه مرتبط بمريض)"""
    resource = context.get('resource', {})
    return resource.get('patient_id') is not None

def _is_future_only(context: Dict[str, Any]) -> bool:
    """  
        الشرط: التاريخ في المورد (مثلاً slot_date) هو في المستقبل (>= اليوم).
        إذا لم يوجد slot_date، يتم الرفض.
    """
    resource = context.get('resource', {})
    slot_date = resource.get('slot_date')
    if not slot_date:
        return False

    if isinstance(slot_date, str):
        try:
            slot_date = datetime.fromisoformat(slot_date).date()
        except ValueError:
            return False
    elif isinstance(slot_date, datetime):
        slot_date = slot_date.date()
    else:
        return False

    today = date.today()
    return slot_date >= today


# ------------------------------------------------------------------
# Singleton instance – يُستخدم في جميع أنحاء التطبيق
# ------------------------------------------------------------------
policy_engine = PolicyEngine()