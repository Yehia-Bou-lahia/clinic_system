# core/exceptions.py

# قاعدة لأخطاء قاعدة البيانات
class DatabaseError(Exception):
    pass
class RoleNotFoundError(DatabaseError):
    """Raised when a role does not exist in the database"""
    pass

# أخطاء قاعدة البيانات (تنشأ من الـ Repository)
class ConnectionError(DatabaseError):
    pass

class UserNotFoundError(DatabaseError):
    pass

class DuplicateEmailError(DatabaseError):
    pass

class PatientNotFoundError(DatabaseError):
    pass

class PatientProfileAlreadyExistsError(DatabaseError):
    pass

class DoctorNotFoundError(DatabaseError):
    pass

class DuplicateLicenseError(DatabaseError):
    pass

class AppointmentNotFoundError(DatabaseError):
    pass

class AppointmentConflictError(DatabaseError):
    pass

class InvalidAppointmentStatusError(DatabaseError):
    pass

class VisitReportNotFoundError(DatabaseError):
    pass

class VisitReportAlreadyExistsError(DatabaseError):
    pass

# أخطاء منطق الأعمال (تنشأ من الـ Service أو Policy)
class PermissionDenied(Exception):
    """Raised when a user is not allowed to perform an action"""
    pass

class DoctorNotAvailableError(Exception):
    """Raised when a doctor is not available for a given time slot"""
    pass

class BookingLimitError(Exception):
    """Raised when a patient exceeds the maximum number of pending appointments"""
    pass

# قد تُستخدم لاحقاً
class AccountDisabledError(Exception):
    pass

class AuthenticationError(Exception):
    pass
class RoleNotFoundError(DatabaseError):
    """Raised when a role does not exist in the database"""
    pass

