# core/event_bus.py
import concurrent.futures
import threading
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any, Tuple, Union
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """هيكل الحدث المنظم."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    payload: Any = None
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """
    ناقل أحداث محسن:
    - دعم المستمعين المتزامنين (sync) وغير المتزامنين (async).
    - آلية إعادة المحاولة للمستمعين غير المتزامنين.
    - مراقبة زمن التنفيذ وتحذير البطء.
    - منع تكرار التسجيل.
    - حماية من الضغط العالي (rate limiting).
    - تخزين الأحداث الفاشلة (dead letter).
    - قابل للاختبار (لا يعتمد كلياً على Singleton).
    """

    MAX_LISTENERS_PER_EVENT = 50
    MAX_PENDING_PER_EVENT = 100       # للـ rate limiting (قيد التنفيذ)
    DEFAULT_RETRY_ATTEMPTS = 2
    DEFAULT_RETRY_BACKOFF = 1.0       # ثواني

    def __init__(self, max_workers: int = 10):
        """
        :param max_workers: عدد الخيوط في تجمع المستمعين غير المتزامنين.
        """
        self._sync_listeners: Dict[str, List[Callable]] = {}
        self._async_listeners: Dict[str, List[Callable]] = {}
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="EventBusAsync"
        )
        self._lock = threading.RLock()
        # للمراقبة والـ rate limiting
        self._pending_counts: Dict[str, int] = {}        # عدد الأحداث قيد التنفيذ لكل نوع
        self._audit_log: List[Dict] = []                 # سجل نتائج الأحداث (يمكن استبداله بقاعدة بيانات)
        self._dead_letter: List[Tuple[Event, Exception]] = []  # الأحداث الفاشلة

    # ------------------------------------------------------------------
    # طرق التسجيل والنشر
    # ------------------------------------------------------------------
    def subscribe(self, event_name: str, handler: Callable, sync: bool = False) -> Callable[[], None]:
        """
            تسجيل مستمع لحدث معين.
            إذا sync = True → ينفذ في نفس الخيط (حجب).
            إذا sync = False → ينفذ في تجمع الخيوط (غير حجب).
            تعيد دالة يمكن استدعاؤها لإلغاء الاشتراك.
        """
        with self._lock:
            listeners = self._sync_listeners if sync else self._async_listeners
            if len(listeners.get(event_name, [])) >= self.MAX_LISTENERS_PER_EVENT:
                raise RuntimeError(f"Too many listeners for event {event_name}")

            # منع تكرار نفس المستمع
            if handler in listeners.get(event_name, []):
                logger.warning(f"Handler {self._handler_name(handler)} already subscribed to {event_name}")
            else:
                listeners.setdefault(event_name, []).append(handler)

        logger.debug(f"Subscribed {self._handler_name(handler)} to event {event_name} (sync={sync})")

        def unsubscribe():
            with self._lock:
                try:
                    listeners[event_name].remove(handler)
                    if not listeners[event_name]:
                        del listeners[event_name]
                except (KeyError, ValueError):
                    pass
            logger.debug(f"Unsubscribed {self._handler_name(handler)} from event {event_name}")

        return unsubscribe

    def publish(self, event: Union[Event, str], payload: Any = None) -> None:
        """
        نشر حدث. يمكن استدعاؤها بـ (Event) أو (event_name, payload).
        """
        if isinstance(event, str):
            event = Event(name=event, payload=payload)

        # التحقق من حدود الضغط العالي (قيد التنفيذ)
        with self._lock:
            pending = self._pending_counts.get(event.name, 0)
            if pending >= self.MAX_PENDING_PER_EVENT:
                logger.warning(f"Too many pending events for {event.name}: {pending}")
                return   # أو يمكن رفع استثناء
            self._pending_counts[event.name] = pending + 1

        try:
            with self._lock:
                sync_handlers = list(self._sync_listeners.get(event.name, []))
                async_handlers = list(self._async_listeners.get(event.name, []))

            if not sync_handlers and not async_handlers:
                logger.debug(f"No listeners for event {event.name}")
                return

            logger.info(f"Publishing event {event.name} (id={event.id}) "
                        f"sync={len(sync_handlers)}, async={len(async_handlers)}")

            # تنفيذ المتزامنين
            for handler in sync_handlers:
                self._run_sync_handler(handler, event)

            # إطلاق غير المتزامنين
            for handler in async_handlers:
                self._executor.submit(self._run_async_handler, handler, event)

        finally:
            with self._lock:
                self._pending_counts[event.name] -= 1
                if self._pending_counts[event.name] == 0:
                    del self._pending_counts[event.name]

    # ------------------------------------------------------------------
    # تنفيذ المستمعين
    # ------------------------------------------------------------------
    def _run_sync_handler(self, handler: Callable, event: Event) -> None:
        """تنفيذ المستمع المتزامن – استثناءاته لا تُحجب غيرها."""
        start = time.time()
        try:
            # تمرير الـ payload فقط للتوافق مع الخدمات الحالية
            handler(event.payload)
            self._log_audit(event, handler, start, success=True)
        except Exception as e:
            self._log_audit(event, handler, start, success=False, error=e)
            logger.error(f"Sync handler {self._handler_name(handler)} for {event.name} failed: {e}")
            # لا نعيد رفع الاستثناء لتجنب تعطيل المتزامنين الآخرين

    def _run_async_handler(self, handler: Callable, event: Event) -> None:
        """تنفيذ المستمع غير المتزامن مع إعادة المحاولة."""
        attempt = 0
        last_error = None
        while attempt < self.DEFAULT_RETRY_ATTEMPTS:
            start = time.time()
            try:
                handler(event.payload)
                self._log_audit(event, handler, start, success=True)
                return
            except Exception as e:
                last_error = e
                duration = time.time() - start
                logger.error(f"Async handler {self._handler_name(handler)} for {event.name} "
                             f"attempt {attempt+1} failed after {duration:.3f}s: {e}")
                attempt += 1
                if attempt < self.DEFAULT_RETRY_ATTEMPTS:
                    wait = self.DEFAULT_RETRY_BACKOFF * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {wait:.2f}s...")
                    time.sleep(wait)

        # جميع المحاولات فشلت
        self._log_audit(event, handler, start, success=False, error=last_error, retries=attempt)
        self._dead_letter.append((event, last_error))
        logger.critical(f"Async handler {self._handler_name(handler)} for {event.name} "
                        f"failed after {self.DEFAULT_RETRY_ATTEMPTS} attempts; moved to dead letter.")

    # ------------------------------------------------------------------
    # أدوات مساعدة
    # ------------------------------------------------------------------
    @staticmethod
    def _handler_name(handler: Callable) -> str:
        """استخراج اسم المستمع بأمان (يتعامل مع lambda و partial)."""
        if hasattr(handler, '__name__'):
            return handler.__name__
        if hasattr(handler, 'func'):  # partial
            return handler.func.__name__
        return str(handler)

    def _log_audit(self, event: Event, handler: Callable, start: float,
                   success: bool, error: Exception = None, retries: int = 0) -> None:
        """تسجيل تفاصيل تنفيذ المستمع في سجل التدقيق."""
        duration = time.time() - start
        status = "SUCCESS" if success else "FAILURE"
        self._audit_log.append({
            "event_id": event.id,
            "event_name": event.name,
            "handler": self._handler_name(handler),
            "duration": duration,
            "status": status,
            "error": str(error) if error else None,
            "retries": retries,
            "timestamp": time.time()
        })
        if duration > 1.0:  # أكثر من ثانية
            logger.warning(f"Handler {self._handler_name(handler)} took {duration:.2f}s for {event.name}")

    # ------------------------------------------------------------------
    # إدارة الإغلاق
    # ------------------------------------------------------------------
    def shutdown(self, wait: bool = True) -> None:
        """إيقاف تجمع الخيوط وتنظيف الموارد."""
        self._executor.shutdown(wait=wait)
        with self._lock:
            self._sync_listeners.clear()
            self._async_listeners.clear()
            self._pending_counts.clear()
        logger.info("EventBus shutdown complete.")

    # ------------------------------------------------------------------
    # طرق للاختبار والمراقبة
    # ------------------------------------------------------------------
    def get_dead_letter(self) -> List[Tuple[Event, Exception]]:
        """إرجاع قائمة الأحداث الفاشلة (للمراقبة)."""
        return self._dead_letter.copy()

    def get_audit_log(self) -> List[Dict]:
        """إرجاع سجل التدقيق (للتطبيقات)."""
        return self._audit_log.copy()

    def clear_audit_log(self) -> None:
        """مسح سجل التدقيق."""
        self._audit_log.clear()


# ------------------------------------------------------------
# Singleton للمشروع – لكن يمكن إنشاء كائنات منفصلة للاختبار
# ------------------------------------------------------------
_event_bus_instance = None

def get_event_bus(max_workers: int = 10) -> EventBus:
    global _event_bus_instance
    if _event_bus_instance is None:
        _event_bus_instance = EventBus(max_workers=max_workers)
    return _event_bus_instance