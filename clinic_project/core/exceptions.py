# أخطاء قاعدة البيانات
class DatabaseError(Exception):
    pass

class ConnectionError(DatabaseError):
    pass

# أخطاء المستخدم
class UserNotFoundError(Exception):
    pass

class AccountDisabledError(Exception):
    pass

class DuplicateEmailError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class PatientNotFoundError(Exception):
    pass

class PatientProfileAlreadyExistsError(Exception):
    pass
class DoctorNotFoundError(DatabaseError):
    """Raised when a doctor profile is not found"""
    pass

class DuplicateLicenseError(DatabaseError):
    """Raised when trying to create a doctor with an existing license number"""
    pass
class AppointmentNotFoundError(DatabaseError):
    """Raised when an appointment is not found"""
    pass

class AppointmentConflictError(DatabaseError):
    """Raised when trying to book an already taken slot"""
    pass

class InvalidAppointmentStatusError(DatabaseError):
    """Raised when trying to change to an invalid status"""
    pass

class VisitReportNotFoundError(DatabaseError):
    """Raised when a visit report is not found"""
    pass

class VisitReportAlreadyExistsError(DatabaseError):
    """Raised when trying to create a report for an appointment that already has one"""
    pass