ALTER TABLE patient_profiles ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL;
--- This migration adds a 'deleted_at' column to the 'patient_profiles' table to enable soft deletion of patient records.

-- إنشاء فهرس لتسريع الاستعلامات التي تستخدم deleted_at
CREATE INDEX idx_patient_profiles_deleted ON patient_profiles(deleted_at);