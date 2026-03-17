CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP   
);

-- ENTER PRIMARY ROLES
INSERT INTO roles (name, description) VALUES
('patient', 'Role for patients who can book appointments and view their medical records.'),
('doctor', 'Role for doctors who can write prescriptions and view patient records.'),
('reception', 'Role for receptionists who can manage appointments and patient check-ins.'),
('admin', 'Role for administrators who can manage users and system settings.');

-- Create users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20),
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT, -- يمنع حدف الدور إذا كان مستخدم مرتبط به
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP        
    );

    -- index for email
    CREATE UNIQUE INDEX idx_users_email ON users(email);

    -- index for role_id
    CREATE INDEX idx_users_role_id ON users(role_id);
