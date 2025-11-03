-- Smart Parking Management System Database
-- Drop database if exists and create fresh
DROP DATABASE IF EXISTS smart_parking;
CREATE DATABASE smart_parking;
USE smart_parking;

-- Table: users
-- Stores user and admin account information
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(15),
    role ENUM('admin', 'user') DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: parking_slots
-- Stores information about parking slots and their availability
CREATE TABLE parking_slots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slot_number VARCHAR(10) UNIQUE NOT NULL,
    status ENUM('empty', 'occupied') DEFAULT 'empty',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: vehicles
-- Stores vehicle entry, exit, and payment information
CREATE TABLE vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_number VARCHAR(20) NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    contact VARCHAR(15) NOT NULL,
    vehicle_type ENUM('Car', 'Bike', 'SUV', 'Van') DEFAULT 'Car',
    slot_id INT,
    user_id INT,
    entry_time DATETIME NOT NULL,
    exit_time DATETIME NULL,
    parking_fee DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (slot_id) REFERENCES parking_slots(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);
-- Table: system_settings
-- Stores global settings like parking fare
CREATE TABLE system_settings (
    setting_key VARCHAR(50) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL
);

-- Insert default parking fare
INSERT INTO system_settings (setting_key, setting_value) 
VALUES ('parking_fee_per_hour', '20');
-- Insert default admin account
-- Username: admin, Password: admin123
INSERT INTO users (username, email, password, phone, role) 
VALUES ('Admin User', 'admin@parking.com', 'admin123', '9876543210', 'admin');

-- Insert sample user accounts
INSERT INTO users (username, email, password, phone, role) 
VALUES 
('John Doe', 'john@example.com', 'user123', '9876543211', 'user'),
('Jane Smith', 'jane@example.com', 'user123', '9876543212', 'user');

-- Create parking slots (A1-A10 and B1-B10)
INSERT INTO parking_slots (slot_number, status) VALUES
('A1', 'empty'), ('A2', 'empty'), ('A3', 'empty'), ('A4', 'empty'), ('A5', 'empty'),
('A6', 'empty'), ('A7', 'empty'), ('A8', 'empty'), ('A9', 'empty'), ('A10', 'empty'),
('B1', 'empty'), ('B2', 'empty'), ('B3', 'empty'), ('B4', 'empty'), ('B5', 'empty'),
('B6', 'empty'), ('B7', 'empty'), ('B8', 'empty'), ('B9', 'empty'), ('B10', 'empty');

-- Sample vehicle entries for testing (optional)
-- INSERT INTO vehicles (vehicle_number, owner_name, contact, vehicle_type, slot_id, user_id, entry_time)
-- VALUES 
-- ('DL01AB1234', 'Rajesh Kumar', '9876543213', 'Car', 1, 2, NOW()),
-- ('UP32CD5678', 'Priya Singh', '9876543214', 'Bike', 2, 3, NOW());

-- Update slot status for sample vehicles
-- UPDATE parking_slots SET status = 'occupied' WHERE id IN (1, 2);

-- Display all tables
SHOW TABLES;

-- Success message
SELECT 'Database created successfully!' AS Message;