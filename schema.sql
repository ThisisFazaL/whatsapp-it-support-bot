-- =========================================================
-- WhatsApp IT Support Chatbot - PostgreSQL DDL Schema & Seeds
-- =========================================================

-- Drop tables if re-initializing
DROP TABLE IF EXISTS ticket_assignments CASCADE;
DROP TABLE IF EXISTS tickets CASCADE;
DROP TABLE IF EXISTS conversation_state CASCADE;
DROP TABLE IF EXISTS issue_types CASCADE;
DROP TABLE IF EXISTS subcategories CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS priorities CASCADE;
DROP TABLE IF EXISTS ticket_status CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS support_admins CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
DROP TABLE IF EXISTS locations CASCADE;

-- Lookup Tables
CREATE TABLE locations (
    location_id SERIAL PRIMARY KEY,
    location_name VARCHAR(100) NOT NULL
);

CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    employee_id SERIAL PRIMARY KEY,
    employee_code VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL, -- Matched against incoming WhatsApp 'from' number
    email VARCHAR(100),
    department_id INT REFERENCES departments(department_id),
    location_id INT REFERENCES locations(location_id),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE support_admins (
    admin_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

-- Classification Tables
CREATE TABLE categories (
    category_id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE subcategories (
    subcategory_id SERIAL PRIMARY KEY,
    category_id INT REFERENCES categories(category_id),
    subcategory_name VARCHAR(100) NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE issue_types (
    issue_type_id SERIAL PRIMARY KEY,
    subcategory_id INT REFERENCES subcategories(subcategory_id),
    issue_name VARCHAR(150) NOT NULL,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE priorities (
    priority_id SERIAL PRIMARY KEY,
    priority_name VARCHAR(50) NOT NULL
);

CREATE TABLE ticket_status (
    status_id SERIAL PRIMARY KEY,
    status_name VARCHAR(50) NOT NULL
);

-- Core Workflow Tables
CREATE TABLE tickets (
    ticket_id SERIAL PRIMARY KEY,
    ticket_number VARCHAR(30) UNIQUE NOT NULL, -- Format: TKT-YYYYMMDD-XXXXX
    employee_id INT REFERENCES employees(employee_id),
    category_id INT REFERENCES categories(category_id),
    subcategory_id INT REFERENCES subcategories(subcategory_id),
    issue_type_id INT REFERENCES issue_types(issue_type_id),
    description TEXT NOT NULL,
    priority_id INT REFERENCES priorities(priority_id) DEFAULT 2,
    status_id INT REFERENCES ticket_status(status_id) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE TABLE ticket_assignments (
    assignment_id SERIAL PRIMARY KEY,
    ticket_id INT REFERENCES tickets(ticket_id),
    admin_id INT REFERENCES support_admins(admin_id),
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE conversation_state (
    phone VARCHAR(20) PRIMARY KEY,
    flow_name VARCHAR(50) DEFAULT 'raise_ticket',
    current_step VARCHAR(50) NOT NULL,
    current_data JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- SEED DATA
-- =========================================================

-- Priorities
INSERT INTO priorities (priority_id, priority_name) VALUES
(1, 'Low'),
(2, 'Medium'),
(3, 'High'),
(4, 'Urgent');

-- Ticket Status
INSERT INTO ticket_status (status_id, status_name) VALUES
(1, 'Open'),
(2, 'In Progress'),
(3, 'Resolved'),
(4, 'Closed');

-- Categories
INSERT INTO categories (category_id, category_name) VALUES
(1, 'Hardware & Devices'),
(2, 'Software & Applications'),
(3, 'Network & Connectivity'),
(4, 'Account & Access Management');

-- Subcategories
INSERT INTO subcategories (subcategory_id, category_id, subcategory_name) VALUES
-- Hardware (1)
(1, 1, 'Laptop / Desktop PC'),
(2, 1, 'Printers & Scanners'),
(3, 1, 'Peripherals (Monitor, Keyboard, Mouse)'),
-- Software (2)
(4, 2, 'Email & Outlook'),
(5, 2, 'Office Productivity Apps'),
(6, 2, 'VPN & Security Software'),
-- Network (3)
(7, 3, 'Wi-Fi & Wireless Network'),
(8, 3, 'LAN / Internet Connection'),
-- Account & Access (4)
(9, 4, 'Password Reset'),
(10, 4, 'Software Permission / Access');

-- Issue Types
INSERT INTO issue_types (subcategory_id, issue_name) VALUES
-- Sub 1: Laptop/Desktop
(1, 'Display / Screen damage or flickering'),
(1, 'Battery charging / Power failure'),
(1, 'System slow / BSOD crash'),
-- Sub 2: Printers
(2, 'Printer offline or unreachable'),
(2, 'Paper jam / Toner replacement'),
-- Sub 3: Peripherals
(3, 'External monitor not displaying'),
(3, 'Keyboard or Mouse non-responsive'),
-- Sub 4: Email & Outlook
(4, 'Outlook unable to sync emails'),
(4, 'Email send/receive error'),
-- Sub 5: Office Apps
(5, 'MS Office license activation issue'),
(5, 'Application freezing on launch'),
-- Sub 6: VPN & Security
(6, 'VPN connection drops constantly'),
(6, 'Antivirus alert / blocking file'),
-- Sub 7: Wi-Fi
(7, 'Cannot connect to Office Wi-Fi'),
(7, 'Wi-Fi password prompt looping'),
-- Sub 8: LAN / Internet
(8, 'Ethernet cable disconnected / No IP'),
(8, 'Extremely slow web browsing'),
-- Sub 9: Password Reset
(9, 'Active Directory Domain Password Reset'),
(9, 'Corporate Email Password Reset'),
-- Sub 10: Permissions
(10, 'Request access to Shared Folder / Drive'),
(10, 'Request access to ERP / CRM System');

-- Locations & Departments
INSERT INTO locations (location_id, location_name) VALUES (1, 'Headquarters - Floor 3'), (2, 'Branch Office');
INSERT INTO departments (department_id, department_name) VALUES (1, 'IT Support'), (2, 'Finance'), (3, 'Human Resources');

-- Support Admins
INSERT INTO support_admins (admin_id, full_name, phone, active) VALUES
(1, 'Alex Rivera (Lead Support)', '919876543210', TRUE),
(2, 'Sarah Jenkins (IT Admin)', '15556729057', TRUE);

-- Sample Employees
INSERT INTO employees (employee_id, employee_code, full_name, phone, email, department_id, location_id) VALUES
(1, 'EMP1001', 'John Doe', '919876543210', 'john.doe@company.com', 2, 1),
(2, 'EMP1002', 'Jane Smith', '15556729057', 'jane.smith@company.com', 3, 1),
(3, 'EMP1003', 'Robert Johnson', '919876543211', 'robert.j@company.com', 2, 2);
