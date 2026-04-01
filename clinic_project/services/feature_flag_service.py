# services/feature_flag_service.py
import time
import threading
import logging
from typing import Dict, Any, Optional

from database.queries.feature_repository import FeatureRepository

logger = logging.getLogger(__name__)


class FeatureFlagService:
    """
    خدمة التحكم في الميزات (Feature Flags).
    - تقرأ الميزات من قاعدة البيانات.
    - تستخدم cache في الذاكرة مع TTL لتجنب استعلامات DB المتكررة.
    """

    CACHE_TTL = 60

    def __init__(self):
        self.repo = FeatureRepository()
        self._cache: Dict[str, tuple] = {}

    def is_enabled(self, code: str) -> bool:
        """
        التحقق مما إذا كانت الميزة مفعلة.
        - تستخدم cache مع TTL.
        """
        now = time.time()
        cached = self._cache.get(code)
        if cached and now - cached[1] < self.CACHE_TTL:
            return cached[0]

        # استعلام من قاعدة البيانات
        feature = self.repo.get_feature(code)
        if not feature:
            logger.warning(f"Feature '{code}' not found in database")
            return False

        is_enabled = feature['is_enabled']
        self._cache[code] = (is_enabled, now)
        return is_enabled

    def invalidate_cache(self, code: Optional[str] = None) -> None:
        """إبطال cache لميزة واحدة أو لكل الميزات."""
        if code:
            self._cache.pop(code, None)
        else:
            self._cache.clear()
        logger.info(f"Feature flag cache invalidated for {code if code else 'all'}")

    def enable(self, code: str) -> bool:
        """تفعيل ميزة (للاستخدام الإداري)."""
        result = self.repo.enable_feature(code)
        if result:
            self.invalidate_cache(code)
        return result

    def disable(self, code: str) -> bool:
        """إيقاف ميزة (للاستخدام الإداري)."""
        result = self.repo.disable_feature(code)
        if result:
            self.invalidate_cache(code)
        return result

    def get_all_features(self):
        """جلب قائمة جميع الميزات (للاستخدام الإداري)."""
        return self.repo.get_all_features()


# ------------------------------------------------------------
# Singleton للمشروع – Double-Checked Locking للسلامة في الخيوط
# ------------------------------------------------------------
_feature_flag_service_instance = None
_singleton_lock = threading.Lock()

def get_feature_flag_service() -> FeatureFlagService:
    global _feature_flag_service_instance
    if _feature_flag_service_instance is None:
        with _singleton_lock:
            if _feature_flag_service_instance is None:
                _feature_flag_service_instance = FeatureFlagService()
    return _feature_flag_service_instance