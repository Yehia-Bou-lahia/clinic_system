# Clinic Management System

A professional clinic management system designed for medical clinics, built with a focus on clean architecture, security, and scalability.

## About
This system digitizes and streamlines clinic operations including patient management, doctor scheduling, appointment booking, medical records, and billing — all in one integrated platform. It is built as a **modular, secure, and production-ready backend** that can be tailored to the needs of real clinics.

## Goals
- **Production-ready** – designed to be sold to clinics with confidence.
- **Modular architecture** – clients can purchase only the features they need.
- **Security-first** – built to resist common attack vectors (SQL injection, XSS, timing attacks, etc.).
- **Clean, maintainable code** – separates data, business logic, and presentation layers for long-term scalability.

## Core Focus Areas
- **Clean Architecture** – clear separation between data (repository), business logic (service), and presentation (API) layers.
- **Security** – parameterized queries, bcrypt password hashing, policy-based access control, audit logging, and protection against timing attacks.
- **Modularity** – independent features (e.g., appointments, patients, doctors) can be enabled or disabled per client using feature flags.
- **Data Integrity** – soft delete to preserve medical records, full audit trail via event-driven architecture.

## What’s Implemented

###  Core Infrastructure
- **PostgreSQL database** with full schema (`users`, `roles`, `policies`, `patient_profiles`, `doctor_profiles`, `appointments`, `visit_reports`, etc.)
- **Connection pool** for efficient database access
- **Parameterized queries** in all repositories – prevents SQL injection

###  Security & Access Control
- **PolicyEngine** – rule-based access control (ABAC) with pre-defined condition handlers (e.g., `is_own_patient`, `is_assigned_doctor`). Policies are stored in the database and evaluated in memory with TTL cache.
- **bcrypt password hashing** with salt (12 rounds) for user passwords.
- **Timing attack protection** in authentication (constant-time check with dummy hash).
- **Soft delete** (`deleted_at` column) for all critical tables – data is never permanently removed through the application.

###  Business Logic (Service Layer)
- **UserService** – registration, login, profile management, password change with strong validation (email format, password strength, phone number validation using `phonenumbers`, restricted to Gulf countries).
- **BookingService** – create, confirm, cancel, reschedule appointments; checks doctor availability (including schedule and breaks) and patient booking limits.
- **EventBus** – asynchronous event publishing/subscribing (in-memory) to decouple services (e.g., `BookingService` publishes `appointment.created`, `NotificationService` listens to it).
- **Repository pattern** – all data access is encapsulated in repository classes (e.g., `UserRepository`, `DoctorRepository`, `AppointmentRepository`).

###  Testing & Quality
- **Pytest test suite** covering all repositories and core logic.
- **Isolated test database** (`clinic_test`) with a dedicated user (`clinic_test_user`) that has full privileges – never touches production data.
- **Logging** for debugging and monitoring.


- **Repository Layer**: raw SQL, connection pooling, parameterized queries.
- **Service Layer**: business rules, policy enforcement, event publishing.
- **Core**: `PolicyEngine`, `EventBus`, custom exceptions, utilities.
- **Database**: tables, indexes, constraints, soft delete.

## Security Measures
- **SQL injection**: all queries use `%s` placeholders with `cursor.execute`.
- **Password storage**: bcrypt hashing with unique salts.
- **Authentication**: bcrypt check with dummy hash to prevent timing leaks.
- **Access control**: policy engine with pre‑defined conditions (no `eval` of user input).
- **Audit logging**: events (e.g., `appointment.created`) can be captured by `AuditService` (planned).
- **Least privilege**: application database user (`clinic_app_user`) has only `SELECT`, `INSERT`, `UPDATE` – no `DELETE`.

## Modularity & Customization
- **Feature flags** (planned) – enable/disable modules (e.g., payments, telemedicine) per client.
- **Policies** stored in the database – can be adjusted without redeploying the application.
- **Event‑driven architecture** – services communicate via events, allowing optional features to be plugged in (e.g., notifications).

## Current Status
**🚧 Actively under development**

- ✅ Database schema
- ✅ Repository layer (all core tables)
- ✅ `PolicyEngine` & `EventBus`
- ✅ `UserService` (complete)
- ✅ `BookingService` (core appointment logic)
- ✅ Doctor availability check (with schedule & conflicts)
- ⏳ `PatientService`, `DoctorService`, `VisitReportService`
- ⏳ API layer (Django REST Framework, JWT)
- ⏳ Frontend (planned – React or Vue)
# License
## Proprietary – not open source.
## Contact
## For inquiries, please contact the development team.

