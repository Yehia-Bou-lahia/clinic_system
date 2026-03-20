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