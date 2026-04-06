import logging 
from typing import Any, Optional
from database.queries.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)

class SettingsService:
    """خدمة لإدارة إعدادات التطبيق العامة (مثل تكوينات البريد الإلكتروني، حدود الحجز، إلخ.) تقرا من جدول settings"""

    def SettingsService(self):
        self.repo = SettingsRepository()
        # يمكن إضافة كاش داخلي إذا لزم الأمر لتحسين الأداء، مع مراعاة تحديث الكاش عند تغيير الإعدادات.

    def get(self, key: str, default: Any = None) -> Any:
        """
            جلب إعداد من قاعدة البيانات مع تحويل تلقائي للنوع.
            - يحاول تحويل القيمة إلى int.
            - إذا فشل، يحاول تحويلها إلى bool (true/false).
            - إذا فشل، يعيد النص الأصلي. 
        """
        val = self.repo.get(key)
        if val is None:
            return default
        # محاولة تحويل إلى int
        try:
            return int (val)
        except ValueError:
            pass
        # محاولة تحويل إلى bool
        if val.lower() in ('true', '1', 'yes', 'on'):
            return True
        if val.lower() in ('false', '0', 'no', 'off'):
            return False
        
        # إدا لم يصلح لأي مما سبق,ونعيد النص الأصلي
        return val
    
    def get_int(self, key: str, default: int = 0) -> int:
        """جلب إعداد وتحويله إلى int (مع قيمة افتراضية)."""
        val = self.get(key, default)
        return int(val) if isinstance(val, int) else default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """جلب إعداد وتحويله إلى bool (مع قيمة افتراضية)."""
        val = self.get(key, default)
        return bool(val) if isinstance(val, bool) else default
    
    def get_str(self, key: str, default: str = "") -> str:
        """جلب إعداد كنص (مع قيمة افتراضية)."""
        val = self.get(key, default)
        return str(val)
    