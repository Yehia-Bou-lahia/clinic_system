CREATE TABLE IF NOT EXISTS patient_profiles(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, -- حذف الملف الشخصي للمريض عند حذف المستخدم
    date_of_birth DATE NOT NULL,
    blood_type VARCHAR(5) CHECK (blood_type IN('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
    emergency_contact VARCHAR(50),-- رقم هاتف جهة الاتصال في حالة الطوارئ
    emergency_contact_name VARCHAR(255),-- اسم جهة الاتصال في حالة الطوارئ
    address TEXT,
    city VARCHAR(100),
    chronic_diseases TEXT,-- قائمة الأمراض المزمنة والحساسية كنصوص مفصولة بفواصل
    allergies TEXT,-- قائمة الأمراض المزمنة والحساسية كنصوص مفصولة بفواصل
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS doctor_profiles(
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, -- حذف الملف الشخصي للطبيب عند حذف المستخدم
    specialization VARCHAR(255) NOT NULL,-- تخصص الطبيب
    qualifications TEXT,-- قائمة المؤهلات العلمية كنصوص مفصولة بفواصل       
    years_of_experience INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patient_profiles_user_id ON patient_profiles(user_id); -- index for user_id in patient_profiles

CREATE TABLE IF NOT EXISTS doctor_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,-- حذف الملف الشخصي للطبيب عند حذف المستخدم
    specialty VARCHAR(255) NOT NULL,
    sub_specialty VARCHAR(255),
    license_number VARCHAR(100) UNIQUE NOT NULL,
    consultation_fee DECIMAL(10,2) NOT NULL CHECK (consultation_fee >= 0),-- يجب أن يكون السعر غير سالب
    rating DECIMAL(3,2) DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    years_experience INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_doctor_profiles_user ON doctor_profiles(user_id);-- index for user_id in doctor_profiles
CREATE INDEX idx_doctor_profiles_specialty ON doctor_profiles(specialty);-- index for specialty in doctor_profiles
CREATE INDEX idx_doctor_profiles_license ON doctor_profiles(license_number);--index for license_number in doctor_profiles

CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,-- حذف الموعد عند حذف الملف الشخصي للمريض
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE, -- حذف الموعد عند حذف الملف الشخصي للطبيب
    appointment_datetime TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','CONFIRMED','IN_PROGRESS','COMPLETED',
                          'CANCELLED_BY_PATIENT','CANCELLED_BY_DOCTOR','CANCELLED_AUTO','NO_SHOW')),
    cancellation_reason TEXT,
    confirmation_deadline TIMESTAMP,
    confirmed_at TIMESTAMP,
    checked_in_at TIMESTAMP,
    no_show_at TIMESTAMP,-- وقت تسجيل عدم الحضور
    completed_at TIMESTAMP,
    notes TEXT,
    is_paid BOOLEAN DEFAULT false,
    payment_amount DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_appointments_patient ON appointments(patient_id); -- index for patient_id in appointments
CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);--  index for doctor_id in appointments
CREATE INDEX idx_appointments_datetime ON appointments(appointment_datetime);-- index for appointment_datetime in appointments
CREATE INDEX idx_appointments_status ON appointments(status);-- index for status in appointments

CREATE TABLE IF NOT EXISTS schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE, -- حذف الجدول عند حذف الملف الشخصي للطبيب 
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),-- 0=Sunday, 1=Monday, ..., 6=Saturday
    start_time TIME NOT NULL,
    end_time TIME NOT NULL CHECK (end_time > start_time), -- يجب أن يكون وقت الانتهاء بعد وقت البدء 
    break_start TIME, 
    break_end TIME,
    slot_duration INTEGER NOT NULL DEFAULT 30 CHECK (slot_duration > 0), -- مدة الحجز بالدقائق يجب أن تكون موجبة    
    is_working_day BOOLEAN DEFAULT true,
    valid_from DATE DEFAULT CURRENT_DATE,
    valid_to DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_break CHECK (break_start IS NULL OR break_end IS NULL OR break_end > break_start),
    CONSTRAINT valid_range CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX idx_schedules_doctor ON schedules(doctor_id); -- index for doctor_id in schedules
CREATE INDEX idx_schedules_day ON schedules(day_of_week); -- index for day_of_week in schedules

CREATE TABLE IF NOT EXISTS time_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE, -- حذف الفتحة الزمنية عند حذف الملف الشخصي للطبيب 
    schedule_id UUID REFERENCES schedules(id) ON DELETE SET NULL, -- إذا تم حذف الجدول، يتم تعيين schedule_id إلى NULL بدلاً من حذف الفتحة الزمنية
    slot_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL CHECK (end_time > start_time), -- يجب أن يكون وقت الانتهاء بعد وقت البدء 
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doctor_id, slot_date, start_time) -- ضمان عدم وجود فتحتين زمنيتين متداخلتين لنفس الطبيب في نفس الوقت 
);

CREATE INDEX idx_time_slots_doctor_date ON time_slots(doctor_id, slot_date); -- index for doctor_id and slot_date in time_slots
CREATE INDEX idx_time_slots_availability ON time_slots(is_available); -- index for is_available in time_slots

CREATE TABLE IF NOT EXISTS visit_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID UNIQUE NOT NULL REFERENCES appointments(id) ON DELETE CASCADE, -- حذف التقرير عند حذف الموعد
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,-- حذف التقرير عند حذف الملف الشخصي للمريض
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE, -- حذف التقرير عند حذف الملف الشخصي للطبيب
    diagnosis TEXT NOT NULL, -- تشخيص الحالة الطبية للمريض
    prescription TEXT,-- وصفة طبية تحتوي على الأدوية الموصوفة والجرعات
    lab_tests TEXT,-- قائمة الفحوصات المخبرية المطلوبة كنصوص مفصولة بفواصل
    radiology TEXT,-- قائمة الفحوصات الإشعاعية المطلوبة كنصوص مفصولة بفواصل
    notes TEXT,-- ملاحظات إضافية من الطبيب حول الزيارة
    follow_up_date DATE,-- تاريخ المتابعة الموصى به للمريض
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_visit_reports_appointment ON visit_reports(appointment_id);-- index for appointment_id in visit_reports
CREATE INDEX idx_visit_reports_patient ON visit_reports(patient_id); -- index for patient_id in visit_reports
CREATE INDEX idx_visit_reports_doctor ON visit_reports(doctor_id); -- index for doctor_id in visit_reports

CREATE TABLE IF NOT EXISTS attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    visit_report_id UUID NOT NULL REFERENCES visit_reports(id) ON DELETE CASCADE, -- حذف المرفق عند حذف تقرير الزيارة
    file_name VARCHAR(255) NOT NULL, -- اسم الملف الأصلي للمرفق 
    file_type VARCHAR(100),-- نوع الملف (مثل 'image/jpeg' أو 'application/pdf')
    description TEXT,-- وصف اختياري للمرفق (مثل "صورة الأشعة" أو "نتائج الفحوصات المخبرية")
    file_path VARCHAR(500) NOT NULL,-- مسار تخزين الملف على الخادم أو في خدمة التخزين السحابي
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- وقت رفع المرفق
);

CREATE INDEX idx_attachments_report ON attachments(visit_report_id); -- index for visit_report_id in attachments

CREATE TABLE IF NOT EXISTS medical_history (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE, -- حذف السجل الطبي عند حذف الملف الشخصي للمريض  
    doctor_id UUID REFERENCES doctor_profiles(id) ON DELETE SET NULL, -- إذا تم حذف الملف الشخصي للطبيب، يتم تعيين doctor_id إلى NULL بدلاً من حذف السجل الطبي
    record_type VARCHAR(50) NOT NULL CHECK (record_type IN ('allergy','medication','surgery','chronic_disease')), -- نوع السجل الطبي (حساسية، دواء، جراحة، مرض مزمن)        
    title VARCHAR(255) NOT NULL, -- عنوان مختصر للسجل الطبي (مثل "حساسية البنسلين" أو "جراحة القلب المفتوح")    
    description TEXT, -- وصف تفصيلي للسجل الطبي (مثل تفاصيل الحساسية أو نوع الجراحة والتاريخ)   
    date_diagnosed DATE, -- تاريخ تشخيص الحالة الطبية (مثل تاريخ اكتشاف الحساسية أو إجراء الجراحة)
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_medical_history_patient ON medical_history(patient_id); -- index for patient_id in medical_history

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, -- حذف الإشعارات عند حذف المستخدم 
    type VARCHAR(50) NOT NULL CHECK (type IN ('email','push','sms')),-- نوع الإشعار (بريد إلكتروني، إشعار دفع، رسالة نصية)
    title VARCHAR(255) NOT NULL, -- عنوان مختصر للإشعار (مثل "تذكير بالموعد" أو "نتائج الفحوصات جاهزة") 
    message TEXT NOT NULL, -- محتوى الإشعار التفصيلي (مثل تفاصيل الموعد أو نتائج الفحوصات)      
    related_to VARCHAR(50),-- نوع الكيان المرتبط بالإشعار (مثل "appointment" أو "visit_report")
    related_id UUID, -- معرف الكيان المرتبط بالإشعار (مثل معرف الموعد أو تقرير الزيارة)
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notifications_user ON notifications(user_id);-- index for user_id in notifications
CREATE INDEX idx_notifications_read ON notifications(is_read);-- index for is_read in notifications 

CREATE TABLE IF NOT EXISTS notification_preferences (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,-- حذف تفضيلات الإشعارات عند حذف المستخدم
    email_enabled BOOLEAN DEFAULT true,-- تمكين الإشعارات عبر البريد الإلكتروني 
    push_enabled BOOLEAN DEFAULT true,-- تمكين إشعارات الدفع
    sms_enabled BOOLEAN DEFAULT false,-- تمكين الرسائل النصية
    quiet_hours_start TIME,-- وقت بدء ساعات الهدوء (فترة عدم تلقي الإشعارات)
    quiet_hours_end TIME,-- وقت نهاية ساعات الهدوء (فترة عدم تلقي الإشعارات)
    notify_before_appointment INTEGER DEFAULT 60,-- عدد الدقائق قبل الموعد لتلقي تذكير بالموعد
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP-- وقت آخر تحديث لتفضيلات الإشعارات
);

CREATE TABLE IF NOT EXISTS waiting_list (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,-- حذف من قائمة الانتظار عند حذف الملف الشخصي للمريض
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE,-- حذف من قائمة الانتظار عند حذف الملف الشخصي للطبيب
    preferred_days JSONB DEFAULT '[]',-- قائمة الأيام المفضلة للموعد (مثال: ["Monday", "Wednesday"])
    preferred_times JSONB DEFAULT '[]',-- قائمة الأوقات المفضلة للموعد (مثال: ["Morning", "Afternoon"])
    is_active BOOLEAN DEFAULT true,-- حالة قائمة الانتظار (نشطة أو غير نشطة)
    notified_at TIMESTAMP,-- وقت آخر مرة تم فيها إخطار المريض بتوفر موعد    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,-- وقت إنشاء سجل قائمة الانتظار
    UNIQUE(patient_id, doctor_id)-- ضمان عدم وجود سجل مكرر لنفس المريض والطبيب في قائمة الانتظار
);

CREATE INDEX idx_waiting_list_patient ON waiting_list(patient_id);-- index for patient_id in waiting_list
CREATE INDEX idx_waiting_list_doctor ON waiting_list(doctor_id); -- index for doctor_id in waiting_list

CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL, -- إذا تم حذف المستخدم، يتم تعيين user_id إلى NULL بدلاً من حذف سجل السجل التدقيقي
    action VARCHAR(100) NOT NULL, -- نوع الإجراء الذي تم تسجيله (مثل "CREATE_APPOINTMENT" أو "UPDATE_PROFILE")
    model_name VARCHAR(100) NOT NULL,-- اسم النموذج أو الجدول المتأثر بالإجراء (مثل "Appointment" أو "PatientProfile")
    object_id UUID,-- معرف الكائن المتأثر بالإجراء (مثل معرف الموعد أو الملف الشخصي للمريض)
    object_repr TEXT,-- تمثيل نصي للكائن المتأثر (مثل "Appointment(id=1234, patient_id=5678)")
    changes JSONB,-- تفاصيل التغييرات التي حدثت في الإجراء (مثال: {"field_name": {"old": "old_value", "new": "new_value"}})
    ip_address INET,-- عنوان IP للجهاز الذي قام بالإجراء
    user_agent TEXT,-- معلومات عن المتصفح أو الجهاز المستخدم في الإجراء
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_log_user ON audit_log(user_id);-- index for user_id in audit_log
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp);-- index for timestamp in audit_log

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    appointment_id UUID UNIQUE NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,-- حذف الدفع عند حذف الموعد
    received_by UUID REFERENCES users(id) ON DELETE SET NULL,-- إذا تم حذف المستخدم الذي استلم الدفع، يتم تعيين received_by إلى NULL بدلاً من حذف سجل الدفع
    amount DECIMAL(10,2) NOT NULL,-- مبلغ الدفع يجب أن يكون غير سالب
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending','paid','refunded')),-- حالة الدفع (قيد الانتظار، مدفوع، مسترد)
    paid_at TIMESTAMP,-- وقت الدفع
    notes TEXT,-- ملاحظات إضافية حول الدفع (مثل طريقة الدفع أو تفاصيل المعاملة)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP-- وقت إنشاء سجل الدفع
);

CREATE INDEX idx_payments_appointment ON payments(appointment_id);-- index for appointment_id in payments

CREATE TABLE IF NOT EXISTS reviews (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patient_id UUID NOT NULL REFERENCES patient_profiles(id) ON DELETE CASCADE,-- حذف التقييم عند حذف الملف الشخصي للمريض   
    doctor_id UUID NOT NULL REFERENCES doctor_profiles(id) ON DELETE CASCADE,-- حذف التقييم عند حذف الملف الشخصي للطبيب
    appointment_id UUID UNIQUE REFERENCES appointments(id) ON DELETE SET NULL,-- إذا تم حذف الموعد، يتم تعيين appointment_id إلى NULL بدلاً من حذف التقييم
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),-- تقييم الطبيب من 1 إلى 5
    comment TEXT,-- تعليق نصي من المريض حول تجربته مع الطبيب
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,-- وقت إنشاء التقييم
    UNIQUE(patient_id, doctor_id, appointment_id)-- ضمان عدم وجود تقييم مكرر لنفس المريض والطبيب في نفس الموعد
);

CREATE INDEX idx_reviews_doctor ON reviews(doctor_id); -- index for doctor_id in reviews

CREATE TABLE IF NOT EXISTS policies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE, -- حذف السياسة عند حذف الدور  
    action VARCHAR(50) NOT NULL,-- نوع الإجراء الذي تغطيه السياسة (مثل "create_appointment" أو "view_patient_records")
    resource VARCHAR(50) NOT NULL,-- نوع المورد الذي تغطيه السياسة (مثل "Appointment" أو "PatientProfile")
    condition TEXT,-- شرط اختياري لتطبيق السياسة (مثل "user_id = patient_id" لتقييد الوصول إلى السجلات الخاصة بالمريض)
    effect VARCHAR(10) DEFAULT 'allow' CHECK (effect IN ('allow','deny')),-- تأثير السياسة (السماح أو الرفض)
    priority INTEGER DEFAULT 0,-- أولوية السياسة (كلما زادت القيمة، زادت الأولوية في تطبيق السياسات المتعارضة)
    is_active BOOLEAN DEFAULT true,-- حالة السياسة (نشطة أو غير نشطة)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,-- وقت إنشاء السياسة
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP-- وقت آخر تحديث للسياسة
);

CREATE INDEX idx_policies_role ON policies(role_id);-- index for role_id in policies
CREATE INDEX idx_policies_resource ON policies(resource);-- index for resource in policies

