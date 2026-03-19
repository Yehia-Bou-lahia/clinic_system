from database.queries.user_repository import UserRepository
from database.connection import db

def test_create_user():
    try:
    #نجلب UUID الخاص بالدور الذي نريد تعيينه للمستخدم
        with db.get_cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE name = 'patient'")
            result = cursor.fetchone()
            if not result:
                raise Exception("Role 'patient' not found in the database.")
            patient_role_id = result['id']
        print(f"Found patient role UUID: {patient_role_id}")

        # second step: create a new user with the retrieved role UUID
        user = UserRepository.create_user(
            email="test@example.com",
            password="secure123",
            full_name="Test User",
            phone_number="0123456789",
            role_id=patient_role_id
        )
        print("User created successfully:", user)
    except Exception as e:
        print("Error creating user:", e)
    
if __name__ == "__main__":
    test_create_user()
        