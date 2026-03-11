-- ============================================================================
-- QERP - PostgreSQL Database Schema
-- Version 1.0
-- ============================================================================
-- Complete data model for a Flask + PostgreSQL web ERP system designed
-- for small precision manufacturing operations, with full ISO 9001:2015
-- traceability and quality management integration.
-- ============================================================================

-- ============================================================================
-- SECTION 1: EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- SECTION 2: ENUM TYPES
-- ============================================================================

-- User roles with hierarchical permissions
CREATE TYPE user_role AS ENUM (
    'owner',
    'quality_manager',
    'operations_manager',
    'office',
    'machinist',
    'inspector'
);

-- Work order status progression
CREATE TYPE work_order_status AS ENUM (
    'draft',
    'pending_release',
    'released_to_floor',
    'in_production',
    'outside_service',
    'final_inspection',
    'pending_ship_release',
    'shipped',
    'closed',
    'archived'
);

-- Operation types
CREATE TYPE operation_type AS ENUM (
    'machining',
    'assembly',
    'finishing',
    'quality',
    'outside_service'
);

-- Operation status
CREATE TYPE operation_status AS ENUM (
    'pending',
    'in_progress',
    'complete',
    'on_hold',
    'skipped'
);

-- Inspection types
CREATE TYPE inspection_type AS ENUM (
    'in_process',
    'first_article',
    'aql',
    'final',
    'receiving'
);

-- Inspection results
CREATE TYPE inspection_result AS ENUM (
    'pass',
    'fail',
    'conditional'
);

-- NCR source
CREATE TYPE ncr_source AS ENUM (
    'in_process',
    'receiving',
    'final_inspection',
    'customer_return',
    'supplier'
);

-- NCR status
CREATE TYPE ncr_status AS ENUM (
    'open',
    'under_review',
    'disposition_pending',
    'capa_required',
    'closed'
);

-- NCR disposition
CREATE TYPE ncr_disposition AS ENUM (
    'rework',
    'use_as_is',
    'npf',
    'customer_waiver',
    'scrap',
    'rtv'
);

-- CAPA types
CREATE TYPE capa_type AS ENUM (
    'corrective',
    'preventive'
);

-- CAPA status
CREATE TYPE capa_status AS ENUM (
    'open',
    'in_progress',
    'verification_pending',
    'closed',
    'overdue'
);

-- Supplier category
CREATE TYPE supplier_category AS ENUM (
    'raw_material',
    'outside_service',
    'tooling',
    'other'
);

-- Supplier approval status
CREATE TYPE supplier_approval_status AS ENUM (
    'approved',
    'conditional',
    'probation',
    'disapproved'
);

-- Outside service PO status
CREATE TYPE os_po_status AS ENUM (
    'draft',
    'sent',
    'in_process',
    'received',
    'closed'
);

-- Receiving inspection result
CREATE TYPE receiving_result AS ENUM (
    'accepted',
    'rejected',
    'conditionally_accepted'
);

-- Equipment calibration status
CREATE TYPE equipment_status AS ENUM (
    'current',
    'due_soon',
    'overdue',
    'out_of_service'
);

-- Calibration result
CREATE TYPE calibration_result AS ENUM (
    'pass',
    'fail',
    'adjusted'
);

-- Equipment owner type
CREATE TYPE equipment_owner_type AS ENUM (
    'company',
    'employee_assigned'
);

-- ============================================================================
-- SECTION 3: BASE TABLES (No Foreign Keys)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1 Users and Authentication (ISO 9001: 5.3, 7.2)
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    initials VARCHAR(10) NOT NULL,
    role user_role NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_username_format CHECK (username ~ '^[a-zA-Z0-9_]+$'),
    CONSTRAINT chk_initials_length CHECK (LENGTH(initials) >= 2)
);

COMMENT ON TABLE users IS 'User accounts with role-based access control';
COMMENT ON COLUMN users.role IS 'Permission hierarchy: owner > quality_manager > operations_manager > office > machinist/inspector';
COMMENT ON COLUMN users.initials IS 'Used for traveler sign-offs and quality records';

-- ----------------------------------------------------------------------------
-- 3.2 Customers (ISO 9001: 8.2)
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_code VARCHAR(50) UNIQUE NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'USA',
    primary_contact_name VARCHAR(100),
    primary_contact_email VARCHAR(100),
    primary_contact_phone VARCHAR(50),
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_customer_code_format CHECK (customer_code ~ '^[A-Z0-9_-]+$')
);

COMMENT ON TABLE customers IS 'Customer master record - ISO 9001:2015 clause 8.2';
COMMENT ON COLUMN customers.customer_code IS 'Short identifier used in reports and work orders (e.g., ACME)';

-- ----------------------------------------------------------------------------
-- 3.3 Suppliers (ISO 9001: 8.4 - Approved Supplier List)
-- ----------------------------------------------------------------------------
CREATE TABLE suppliers (
    supplier_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    supplier_name VARCHAR(200) NOT NULL,
    supplier_code VARCHAR(50) UNIQUE NOT NULL,
    category supplier_category NOT NULL,
    address_line1 VARCHAR(200),
    address_line2 VARCHAR(200),
    city VARCHAR(100),
    state VARCHAR(50),
    postal_code VARCHAR(20),
    country VARCHAR(100),
    primary_contact VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(50),
    approved_status supplier_approval_status NOT NULL DEFAULT 'approved',
    approval_date DATE,
    last_evaluation_date DATE,
    next_evaluation_due DATE,
    approved_processes TEXT,
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_supplier_code_format CHECK (supplier_code ~ '^[A-Z0-9_-]+$')
);

COMMENT ON TABLE suppliers IS 'Approved supplier list with evaluation tracking - ISO 9001:2015 clause 8.4';
COMMENT ON COLUMN suppliers.approved_processes IS 'Comma-separated list of approved processes (e.g., "Anodize Type II, Electropolish")';

-- ----------------------------------------------------------------------------
-- 3.4 Equipment Register (ISO 9001: 7.1.5)
-- ----------------------------------------------------------------------------
CREATE TABLE equipment (
    equipment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_name VARCHAR(200) NOT NULL,
    serial_number VARCHAR(100),
    asset_number VARCHAR(100) UNIQUE,
    location VARCHAR(100),
    calibration_interval_days INTEGER,
    last_calibration_date DATE,
    next_calibration_due DATE,
    calibration_standard VARCHAR(200),
    status equipment_status DEFAULT 'current',
    assigned_to VARCHAR(100),
    owner_type equipment_owner_type DEFAULT 'company',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_calibration_interval CHECK (calibration_interval_days > 0)
);

COMMENT ON TABLE equipment IS 'Calibration register for measuring and test equipment - ISO 9001:2015 clause 7.1.5';
COMMENT ON COLUMN equipment.next_calibration_due IS 'Auto-calculated: last_calibration_date + calibration_interval_days';
COMMENT ON COLUMN equipment.assigned_to IS 'Employee name if owner_type is employee_assigned';

-- ============================================================================
-- SECTION 4: PARTS AND REVISIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 4.1 Parts Master (ISO 9001: 7.5, 8.5.2)
-- ----------------------------------------------------------------------------
CREATE TABLE parts (
    part_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    customer_part_number VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    material VARCHAR(200),
    finish VARCHAR(200),
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_customer_part UNIQUE (customer_id, customer_part_number)
);

COMMENT ON TABLE parts IS 'Part master record - links to customer and tracks current configuration';
COMMENT ON COLUMN parts.customer_part_number IS 'Part number as assigned by the customer';

-- ----------------------------------------------------------------------------
-- 4.2 Part Revisions (ISO 9001: 7.5 - Document Control)
-- ----------------------------------------------------------------------------
CREATE TABLE part_revisions (
    revision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    part_id UUID NOT NULL REFERENCES parts(part_id) ON DELETE CASCADE,
    revision_level VARCHAR(20) NOT NULL,
    drawing_file_path VARCHAR(500),
    effective_date DATE NOT NULL,
    superseded_date DATE,
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_part_revision UNIQUE (part_id, revision_level),
    CONSTRAINT chk_revision_dates CHECK (superseded_date IS NULL OR superseded_date >= effective_date)
);

COMMENT ON TABLE part_revisions IS 'Tracks drawing revisions with file paths and effectivity dates';
COMMENT ON COLUMN part_revisions.drawing_file_path IS 'Path to controlled drawing file in /qerp-files/drawings/';
COMMENT ON COLUMN part_revisions.superseded_date IS 'NULL for current revision; populated when a newer revision becomes effective';

-- ============================================================================
-- SECTION 5: WORK ORDERS AND OPERATIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 5.1 Work Orders - Digital Traveler (ISO 9001: 8.1, 8.5.1, 8.5.2)
-- ----------------------------------------------------------------------------
CREATE TABLE work_orders (
    work_order_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    part_id UUID NOT NULL REFERENCES parts(part_id),
    revision_id UUID NOT NULL REFERENCES part_revisions(revision_id),
    customer_po_number VARCHAR(100),
    customer_po_line VARCHAR(50),
    customer_po_date DATE,
    quantity_ordered INTEGER NOT NULL,
    quantity_completed INTEGER DEFAULT 0,
    production_due_date DATE NOT NULL,
    mfg_date_shipped DATE,
    status work_order_status DEFAULT 'draft',
    sub_wo_parent_id UUID REFERENCES work_orders(work_order_id),
    fai_required BOOLEAN DEFAULT FALSE,
    aql_required BOOLEAN DEFAULT FALSE,
    special_fa_required BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(user_id),
    released_at TIMESTAMP,
    released_by UUID REFERENCES users(user_id),
    closed_at TIMESTAMP,
    closed_by UUID REFERENCES users(user_id),

    CONSTRAINT chk_quantity_ordered CHECK (quantity_ordered > 0),
    CONSTRAINT chk_quantity_completed CHECK (quantity_completed >= 0 AND quantity_completed <= quantity_ordered),
    CONSTRAINT chk_production_due CHECK (status = 'draft' OR production_due_date >= CURRENT_DATE)
);

COMMENT ON TABLE work_orders IS 'Digital traveler - core production tracking entity linking customer order to shop floor execution';
COMMENT ON COLUMN work_orders.work_order_number IS 'Auto-generated format: MMDDYYYY-SEQ';
COMMENT ON COLUMN work_orders.revision_id IS 'Frozen at order time - links to specific drawing revision in effect when order was placed';
COMMENT ON COLUMN work_orders.production_due_date IS 'Required before floor release - drives scheduling';
COMMENT ON COLUMN work_orders.sub_wo_parent_id IS 'NULL for primary WO; references parent if this is a split or sub work order';

-- ----------------------------------------------------------------------------
-- 5.2 Work Order Operations - Routing (ISO 9001: 8.5.1, 8.6)
-- ----------------------------------------------------------------------------
CREATE TABLE work_order_operations (
    operation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_id UUID NOT NULL REFERENCES work_orders(work_order_id) ON DELETE CASCADE,
    stream_id INTEGER DEFAULT 1,
    sequence_number INTEGER NOT NULL,
    operation_code VARCHAR(20) NOT NULL,
    operation_description VARCHAR(200) NOT NULL,
    operation_type operation_type NOT NULL,
    work_center VARCHAR(100),
    machine_number_planned VARCHAR(50),
    machine_number_actual VARCHAR(50),
    quantity_started INTEGER,
    quantity_finished INTEGER,
    start_date TIMESTAMP,
    start_by UUID REFERENCES users(user_id),
    end_date TIMESTAMP,
    end_by UUID REFERENCES users(user_id),
    status operation_status DEFAULT 'pending',
    notes TEXT,
    outside_service_po_id UUID,

    CONSTRAINT uq_wo_stream_sequence UNIQUE (work_order_id, stream_id, sequence_number),
    CONSTRAINT chk_operation_code_format CHECK (operation_code ~ '^(Op-(M[0-8]|F[2-6]|Q[1-3]|A[67])|OS)$'),
    CONSTRAINT chk_quantities CHECK (
        (quantity_started IS NULL OR quantity_started > 0) AND
        (quantity_finished IS NULL OR quantity_finished >= 0) AND
        (quantity_finished IS NULL OR quantity_started IS NULL OR quantity_finished <= quantity_started)
    ),
    CONSTRAINT chk_operation_dates CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)
);

COMMENT ON TABLE work_order_operations IS 'Routing sequence for each work order using controlled operation codes';
COMMENT ON COLUMN work_order_operations.stream_id IS 'Supports parallel routing sequences (default 1 for linear routing)';
COMMENT ON COLUMN work_order_operations.operation_code IS 'Controlled codes: Op-M0 through Op-M8, Op-F2 through Op-F6, Op-Q1 through Op-Q3, Op-A6/A7, OS';
COMMENT ON COLUMN work_order_operations.outside_service_po_id IS 'FK to outside_service_pos - added via ALTER TABLE after that table is created';

-- ============================================================================
-- SECTION 6: MATERIAL AND OUTSIDE SERVICE
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 6.1 Material Certifications (ISO 9001: 8.5.2, 8.4)
-- ----------------------------------------------------------------------------
CREATE TABLE material_certs (
    cert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_id UUID NOT NULL REFERENCES work_orders(work_order_id) ON DELETE CASCADE,
    part_number_on_cert VARCHAR(100),
    description VARCHAR(200),
    lot_number VARCHAR(100),
    heat_number VARCHAR(100),
    certification_number VARCHAR(100),
    cert_date DATE,
    manufacturer VARCHAR(200),
    supplier_po_number VARCHAR(100),
    cert_file_path VARCHAR(500) NOT NULL,
    special_instructions TEXT,
    entered_by UUID REFERENCES users(user_id),
    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_cert_file_required CHECK (cert_file_path IS NOT NULL AND LENGTH(cert_file_path) > 0)
);

COMMENT ON TABLE material_certs IS 'Material certifications linked to work orders - at least one with attached file required before floor release';
COMMENT ON COLUMN material_certs.cert_file_path IS 'Path to cert file in /qerp-files/certs/material/ - REQUIRED';

-- ----------------------------------------------------------------------------
-- 6.2 Outside Service Purchase Orders (ISO 9001: 8.4)
-- ----------------------------------------------------------------------------
CREATE TABLE outside_service_pos (
    os_po_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_id UUID NOT NULL REFERENCES work_orders(work_order_id),
    operation_id UUID REFERENCES work_order_operations(operation_id),
    supplier_id UUID NOT NULL REFERENCES suppliers(supplier_id),
    po_number VARCHAR(50) UNIQUE NOT NULL,
    process_description VARCHAR(200) NOT NULL,
    process_spec VARCHAR(200),
    quantity_sent INTEGER,
    date_sent DATE,
    date_expected_return DATE,
    date_received DATE,
    quantity_received INTEGER,
    vendor_invoice_number VARCHAR(100),
    vendor_so_number VARCHAR(100),
    invoice_amount DECIMAL(10,2),
    invoice_file_path VARCHAR(500),
    cert_file_path VARCHAR(500),
    status os_po_status DEFAULT 'draft',
    receiving_notes TEXT,
    received_by UUID REFERENCES users(user_id),
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_os_quantities CHECK (
        (quantity_sent IS NULL OR quantity_sent > 0) AND
        (quantity_received IS NULL OR quantity_received > 0)
    ),
    CONSTRAINT chk_os_dates CHECK (
        (date_expected_return IS NULL OR date_sent IS NULL OR date_expected_return >= date_sent) AND
        (date_received IS NULL OR date_sent IS NULL OR date_received >= date_sent)
    )
);

COMMENT ON TABLE outside_service_pos IS 'Outside service purchase orders - linked operation cannot complete until status=received with invoice attached';
COMMENT ON COLUMN outside_service_pos.invoice_file_path IS 'Path to vendor invoice in /qerp-files/certs/outside/';
COMMENT ON COLUMN outside_service_pos.cert_file_path IS 'Optional separate cert file if vendor provides one in addition to invoice';

-- Add FK constraint to work_order_operations now that outside_service_pos exists
ALTER TABLE work_order_operations
    ADD CONSTRAINT fk_outside_service_po
    FOREIGN KEY (outside_service_po_id)
    REFERENCES outside_service_pos(os_po_id);

-- ============================================================================
-- SECTION 7: QUALITY AND INSPECTION
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 7.1 Inspection Records (ISO 9001: 8.6, 8.5.1)
-- ----------------------------------------------------------------------------
CREATE TABLE inspection_records (
    inspection_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    work_order_id UUID NOT NULL REFERENCES work_orders(work_order_id),
    operation_id UUID REFERENCES work_order_operations(operation_id),
    inspection_type inspection_type NOT NULL,
    quantity_started INTEGER,
    quantity_finished INTEGER,
    quantity_inspected INTEGER NOT NULL,
    quantity_passed INTEGER DEFAULT 0,
    quantity_failed INTEGER DEFAULT 0,
    result inspection_result NOT NULL,
    inspection_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    inspector_id UUID NOT NULL REFERENCES users(user_id),
    equipment_used VARCHAR(200),
    notes TEXT,
    ncr_id UUID,

    CONSTRAINT chk_inspection_quantities CHECK (
        quantity_inspected > 0 AND
        quantity_passed >= 0 AND
        quantity_failed >= 0 AND
        quantity_passed + quantity_failed = quantity_inspected
    )
);

COMMENT ON TABLE inspection_records IS 'All inspection records: in-process, FAI, AQL, final, and receiving';
COMMENT ON COLUMN inspection_records.inspector_id IS 'Must be user with inspector or quality_manager role (enforced by application)';
COMMENT ON COLUMN inspection_records.equipment_used IS 'Equipment IDs or names used for dimensional inspection';
COMMENT ON COLUMN inspection_records.ncr_id IS 'FK to ncrs - added via ALTER TABLE after NCR table is created';

-- ----------------------------------------------------------------------------
-- 7.2 Inspection Characteristics (for FAI/Dimensional)
-- ----------------------------------------------------------------------------
CREATE TABLE inspection_characteristics (
    characteristic_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    inspection_id UUID NOT NULL REFERENCES inspection_records(inspection_id) ON DELETE CASCADE,
    characteristic_name VARCHAR(200) NOT NULL,
    nominal DECIMAL(12,6),
    tolerance_plus DECIMAL(12,6),
    tolerance_minus DECIMAL(12,6),
    actual_measured DECIMAL(12,6) NOT NULL,
    result inspection_result NOT NULL,
    notes TEXT
);

COMMENT ON TABLE inspection_characteristics IS 'Detailed dimensional measurements for FAI and critical inspection operations';
COMMENT ON COLUMN inspection_characteristics.characteristic_name IS 'Description of the characteristic being measured (e.g., "Diameter at Station A")';

-- ----------------------------------------------------------------------------
-- 7.3 NCRs - Nonconforming Material (ISO 9001: 8.7, 10.2)
-- ----------------------------------------------------------------------------
CREATE TABLE ncrs (
    ncr_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ncr_number VARCHAR(50) UNIQUE NOT NULL,
    work_order_id UUID REFERENCES work_orders(work_order_id),
    operation_id UUID REFERENCES work_order_operations(operation_id),
    inspection_id UUID REFERENCES inspection_records(inspection_id),
    initiated_by UUID NOT NULL REFERENCES users(user_id),
    initiated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT NOT NULL,
    quantity_nonconforming INTEGER NOT NULL,
    part_number VARCHAR(100),
    source ncr_source NOT NULL,
    status ncr_status DEFAULT 'open',
    disposition ncr_disposition,
    disposition_by UUID REFERENCES users(user_id),
    disposition_at TIMESTAMP,
    disposition_notes TEXT,
    customer_notified BOOLEAN DEFAULT FALSE,
    customer_response_file_path VARCHAR(500),
    reinspection_required BOOLEAN DEFAULT FALSE,
    reinspection_result inspection_result,
    reinspection_by UUID REFERENCES users(user_id),
    reinspection_at TIMESTAMP,
    capa_required BOOLEAN DEFAULT FALSE,
    capa_id UUID,
    root_cause TEXT,
    supplier_id UUID REFERENCES suppliers(supplier_id),
    scar_required BOOLEAN DEFAULT FALSE,
    closed_by UUID REFERENCES users(user_id),
    closed_at TIMESTAMP,
    evidence_file_paths JSONB,

    CONSTRAINT chk_ncr_quantity CHECK (quantity_nonconforming > 0),
    CONSTRAINT chk_ncr_number_format CHECK (ncr_number ~ '^NCR-[0-9]{4}-[0-9]{4}$'),
    CONSTRAINT chk_customer_waiver_requirements CHECK (
        disposition != 'customer_waiver' OR customer_response_file_path IS NOT NULL
    ),
    CONSTRAINT chk_rework_reinspection CHECK (
        disposition != 'rework' OR reinspection_required = TRUE
    )
);

COMMENT ON TABLE ncrs IS 'Nonconforming material records with full disposition and CAPA workflow';
COMMENT ON COLUMN ncrs.ncr_number IS 'Auto-generated format: NCR-YYYY-NNNN';
COMMENT ON COLUMN ncrs.disposition IS 'Only quality_manager or owner role can set disposition (enforced by application)';
COMMENT ON COLUMN ncrs.evidence_file_paths IS 'JSON array of file paths in /qerp-files/ncr/';
COMMENT ON COLUMN ncrs.capa_id IS 'FK to capas - added via ALTER TABLE after CAPA table is created';

-- Add FK constraint back to inspection_records now that ncrs exists
ALTER TABLE inspection_records
    ADD CONSTRAINT fk_ncr
    FOREIGN KEY (ncr_id)
    REFERENCES ncrs(ncr_id);

-- ----------------------------------------------------------------------------
-- 7.4 CAPAs - Corrective and Preventive Actions (ISO 9001: 10.2)
-- ----------------------------------------------------------------------------
CREATE TABLE capas (
    capa_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    capa_number VARCHAR(50) UNIQUE NOT NULL,
    ncr_id UUID REFERENCES ncrs(ncr_id),
    initiated_by UUID NOT NULL REFERENCES users(user_id),
    initiated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    type capa_type NOT NULL,
    description TEXT NOT NULL,
    root_cause TEXT,
    action_plan TEXT,
    assigned_to UUID REFERENCES users(user_id),
    due_date DATE,
    status capa_status DEFAULT 'open',
    effectiveness_verified BOOLEAN DEFAULT FALSE,
    effectiveness_notes TEXT,
    verified_by UUID REFERENCES users(user_id),
    verified_at TIMESTAMP,
    closed_by UUID REFERENCES users(user_id),
    closed_at TIMESTAMP,

    CONSTRAINT chk_capa_number_format CHECK (capa_number ~ '^CAPA-[0-9]{4}-[0-9]{4}$')
);

COMMENT ON TABLE capas IS 'Corrective and Preventive Actions - linked NCRs cannot close until CAPA closes';
COMMENT ON COLUMN capas.capa_number IS 'Auto-generated format: CAPA-YYYY-NNNN';

-- Add FK constraint back to ncrs now that capas exists
ALTER TABLE ncrs
    ADD CONSTRAINT fk_capa
    FOREIGN KEY (capa_id)
    REFERENCES capas(capa_id);

-- ============================================================================
-- SECTION 8: RECEIVING AND SHIPPING
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 8.1 Receiving Inspection Records (ISO 9001: 8.4)
-- ----------------------------------------------------------------------------
CREATE TABLE receiving_records (
    receiving_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    receiving_number VARCHAR(50) UNIQUE NOT NULL,
    supplier_id UUID NOT NULL REFERENCES suppliers(supplier_id),
    po_number VARCHAR(50) NOT NULL,
    date_received DATE NOT NULL,
    received_by UUID NOT NULL REFERENCES users(user_id),
    description VARCHAR(500),
    quantity_received INTEGER NOT NULL,
    quantity_accepted INTEGER DEFAULT 0,
    quantity_rejected INTEGER DEFAULT 0,
    inspection_result receiving_result NOT NULL,
    cert_verified BOOLEAN DEFAULT FALSE,
    cert_file_path VARCHAR(500),
    work_order_id UUID REFERENCES work_orders(work_order_id),
    os_po_id UUID REFERENCES outside_service_pos(os_po_id),
    ncr_id UUID REFERENCES ncrs(ncr_id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_receiving_number_format CHECK (receiving_number ~ '^REC-[0-9]{4}-[0-9]{4}$'),
    CONSTRAINT chk_receiving_quantities CHECK (
        quantity_received > 0 AND
        quantity_accepted >= 0 AND
        quantity_rejected >= 0 AND
        quantity_accepted + quantity_rejected = quantity_received
    )
);

COMMENT ON TABLE receiving_records IS 'Receiving inspection records for all incoming material and outside services';
COMMENT ON COLUMN receiving_records.receiving_number IS 'Auto-generated format: REC-YYYY-NNNN';
COMMENT ON COLUMN receiving_records.cert_verified IS 'TRUE if material cert or outside service cert has been reviewed and approved';

-- ----------------------------------------------------------------------------
-- 8.2 Shipments and Release Gate (ISO 9001: 8.6)
-- ----------------------------------------------------------------------------
CREATE TABLE shipments (
    shipment_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    shipment_number VARCHAR(50) UNIQUE NOT NULL,
    work_order_id UUID NOT NULL REFERENCES work_orders(work_order_id),
    ship_date DATE NOT NULL,
    quantity_shipped INTEGER NOT NULL,
    carrier VARCHAR(100),
    tracking_number VARCHAR(100),
    customer_id UUID NOT NULL REFERENCES customers(customer_id),
    ship_to_name VARCHAR(200),
    ship_to_address_line1 VARCHAR(200),
    ship_to_address_line2 VARCHAR(200),
    ship_to_city VARCHAR(100),
    ship_to_state VARCHAR(50),
    ship_to_postal_code VARCHAR(20),
    ship_to_country VARCHAR(100),
    customer_po_number VARCHAR(100),
    released_by UUID NOT NULL REFERENCES users(user_id),
    released_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    coc_generated BOOLEAN DEFAULT FALSE,
    coc_file_path VARCHAR(500),
    packing_slip_file_path VARCHAR(500),
    notes TEXT,

    CONSTRAINT chk_shipment_number_format CHECK (shipment_number ~ '^SHIP-[0-9]{4}-[0-9]{4}$'),
    CONSTRAINT chk_quantity_shipped CHECK (quantity_shipped > 0)
);

COMMENT ON TABLE shipments IS '7-condition release gate must pass before Release to Ship activates:
  1. All routing operations status = complete
  2. Final inspection exists with result = pass
  3. If fai_required = TRUE, FAI inspection record exists and passes
  4. Zero open NCRs on this work order
  5. At least one material cert with attached file exists
  6. All outside service operations status = received with invoice attached
  7. quantity_shipped <= quantity_ordered';
COMMENT ON COLUMN shipments.shipment_number IS 'Auto-generated format: SHIP-YYYY-NNNN';
COMMENT ON COLUMN shipments.released_by IS 'Only quality_manager or owner role can release to ship (enforced by application)';
COMMENT ON COLUMN shipments.coc_file_path IS 'Path to generated Certificate of Conformance PDF in /qerp-files/coc/';

-- ============================================================================
-- SECTION 9: CALIBRATION RECORDS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 9.1 Calibration Records (ISO 9001: 7.1.5)
-- ----------------------------------------------------------------------------
CREATE TABLE calibration_records (
    calibration_record_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    equipment_id UUID NOT NULL REFERENCES equipment(equipment_id) ON DELETE CASCADE,
    calibration_date DATE NOT NULL,
    performed_by VARCHAR(200) NOT NULL,
    result calibration_result NOT NULL,
    certificate_file_path VARCHAR(500),
    next_due_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_cal_dates CHECK (next_due_date > calibration_date)
);

COMMENT ON TABLE calibration_records IS 'Calibration history for all measuring and test equipment - ISO 9001:2015 clause 7.1.5';
COMMENT ON COLUMN calibration_records.performed_by IS 'Calibration vendor or internal technician name';
COMMENT ON COLUMN calibration_records.certificate_file_path IS 'Path to calibration certificate in /qerp-files/certs/calibration/';

-- ============================================================================
-- SECTION 10: INDEXES FOR PERFORMANCE
-- ============================================================================

-- Users
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_active ON users(active);

-- Customers
CREATE INDEX idx_customers_code ON customers(customer_code);
CREATE INDEX idx_customers_active ON customers(active);

-- Suppliers
CREATE INDEX idx_suppliers_code ON suppliers(supplier_code);
CREATE INDEX idx_suppliers_category ON suppliers(category);
CREATE INDEX idx_suppliers_status ON suppliers(approved_status);

-- Parts
CREATE INDEX idx_parts_customer ON parts(customer_id);
CREATE INDEX idx_parts_active ON parts(active);

-- Part Revisions
CREATE INDEX idx_part_revisions_part ON part_revisions(part_id);
CREATE INDEX idx_part_revisions_effective ON part_revisions(effective_date);
CREATE INDEX idx_part_revisions_current ON part_revisions(part_id, superseded_date) WHERE superseded_date IS NULL;

-- Work Orders
CREATE INDEX idx_wo_number ON work_orders(work_order_number);
CREATE INDEX idx_wo_customer ON work_orders(customer_id);
CREATE INDEX idx_wo_part ON work_orders(part_id);
CREATE INDEX idx_wo_revision ON work_orders(revision_id);
CREATE INDEX idx_wo_status ON work_orders(status);
CREATE INDEX idx_wo_due_date ON work_orders(production_due_date);
CREATE INDEX idx_wo_po_number ON work_orders(customer_po_number);
CREATE INDEX idx_wo_parent ON work_orders(sub_wo_parent_id);

-- Work Order Operations
CREATE INDEX idx_woop_wo ON work_order_operations(work_order_id);
CREATE INDEX idx_woop_sequence ON work_order_operations(work_order_id, stream_id, sequence_number);
CREATE INDEX idx_woop_status ON work_order_operations(status);
CREATE INDEX idx_woop_type ON work_order_operations(operation_type);
CREATE INDEX idx_woop_os_po ON work_order_operations(outside_service_po_id);

-- Material Certs
CREATE INDEX idx_matcert_wo ON material_certs(work_order_id);

-- Outside Service POs
CREATE INDEX idx_ospo_wo ON outside_service_pos(work_order_id);
CREATE INDEX idx_ospo_supplier ON outside_service_pos(supplier_id);
CREATE INDEX idx_ospo_status ON outside_service_pos(status);
CREATE INDEX idx_ospo_po_number ON outside_service_pos(po_number);

-- Inspections
CREATE INDEX idx_insp_wo ON inspection_records(work_order_id);
CREATE INDEX idx_insp_operation ON inspection_records(operation_id);
CREATE INDEX idx_insp_type ON inspection_records(inspection_type);
CREATE INDEX idx_insp_result ON inspection_records(result);
CREATE INDEX idx_insp_inspector ON inspection_records(inspector_id);
CREATE INDEX idx_insp_date ON inspection_records(inspection_date);

-- Inspection Characteristics
CREATE INDEX idx_inspchar_inspection ON inspection_characteristics(inspection_id);

-- NCRs
CREATE INDEX idx_ncr_number ON ncrs(ncr_number);
CREATE INDEX idx_ncr_wo ON ncrs(work_order_id);
CREATE INDEX idx_ncr_status ON ncrs(status);
CREATE INDEX idx_ncr_source ON ncrs(source);
CREATE INDEX idx_ncr_disposition ON ncrs(disposition);
CREATE INDEX idx_ncr_capa ON ncrs(capa_id);
CREATE INDEX idx_ncr_open ON ncrs(status) WHERE status != 'closed';

-- CAPAs
CREATE INDEX idx_capa_number ON capas(capa_number);
CREATE INDEX idx_capa_ncr ON capas(ncr_id);
CREATE INDEX idx_capa_status ON capas(status);
CREATE INDEX idx_capa_assigned ON capas(assigned_to);
CREATE INDEX idx_capa_due_date ON capas(due_date);
CREATE INDEX idx_capa_open ON capas(status) WHERE status != 'closed';

-- Receiving
CREATE INDEX idx_recv_number ON receiving_records(receiving_number);
CREATE INDEX idx_recv_supplier ON receiving_records(supplier_id);
CREATE INDEX idx_recv_wo ON receiving_records(work_order_id);
CREATE INDEX idx_recv_ospo ON receiving_records(os_po_id);
CREATE INDEX idx_recv_date ON receiving_records(date_received);

-- Shipments
CREATE INDEX idx_ship_number ON shipments(shipment_number);
CREATE INDEX idx_ship_wo ON shipments(work_order_id);
CREATE INDEX idx_ship_customer ON shipments(customer_id);
CREATE INDEX idx_ship_date ON shipments(ship_date);
CREATE INDEX idx_ship_po ON shipments(customer_po_number);

-- Equipment
CREATE INDEX idx_equip_asset ON equipment(asset_number);
CREATE INDEX idx_equip_status ON equipment(status);
CREATE INDEX idx_equip_cal_due ON equipment(next_calibration_due);

-- Calibration Records
CREATE INDEX idx_calrec_equipment ON calibration_records(equipment_id);
CREATE INDEX idx_calrec_date ON calibration_records(calibration_date);
CREATE INDEX idx_calrec_next_due ON calibration_records(next_due_date);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
-- Tables: 19 core tables
-- ISO 9001:2015 clauses covered: 5.3, 7.1.5, 7.2, 7.5, 8.1, 8.2, 8.4,
--                                 8.5.1, 8.5.2, 8.6, 8.7, 10.2
-- Run setup.py before first use to initialize admin credentials.
-- ============================================================================
