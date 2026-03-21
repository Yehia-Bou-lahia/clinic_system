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