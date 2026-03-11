"""
Suppliers Module - Approved Supplier List Management
ISO 9001: 8.4 (Control of externally provided processes, products and services)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import execute_query
import uuid

suppliers_bp = Blueprint('suppliers', __name__)

# ============================================================================
# LIST SUPPLIERS
# ============================================================================

@suppliers_bp.route('/')
@login_required
def list_suppliers():
    """List all suppliers with search and filters"""
    
    # Permission check - office and above
    if not current_user.is_office():
        flash('You do not have permission to access supplier management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    # Build query
    where_clauses = []
    params = []
    
    if search:
        where_clauses.append("""
            (supplier_code ILIKE %s OR 
             supplier_name ILIKE %s OR 
             approved_processes ILIKE %s OR
             primary_contact ILIKE %s)
        """)
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
    
    if category:
        where_clauses.append("category = %s")
        params.append(category)
    
    if active_only:
        where_clauses.append("active = TRUE")
    
    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    
    query = f"""
        SELECT *
        FROM suppliers
        WHERE {where_sql}
        ORDER BY supplier_code ASC
    """
    
    suppliers = execute_query(query, tuple(params), fetch_all=True)
    
    return render_template(
        'suppliers/list.html',
        suppliers=suppliers,
        search=search,
        category=category,
        active_only=active_only
    )

# ============================================================================
# VIEW SUPPLIER
# ============================================================================

@suppliers_bp.route('/<supplier_id>')
@login_required
def view_supplier(supplier_id):
    """View supplier details and history"""
    
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access supplier management.', 'danger')
        return redirect(url_for('dashboard'))
    
    query = """
        SELECT *
        FROM suppliers
        WHERE supplier_id = %s
    """
    supplier = execute_query(query, (supplier_id,), fetch_one=True)
    
    if not supplier:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    # Get recent OS POs for this supplier
    po_query = """
        SELECT os.*, wo.work_order_number,
               u.full_name as created_by_name
        FROM outside_service_pos os
        LEFT JOIN work_orders wo ON os.work_order_id = wo.work_order_id
        LEFT JOIN users u ON os.created_by = u.user_id
        WHERE os.supplier_id = %s
        ORDER BY os.created_at DESC
        LIMIT 10
    """
    recent_pos = execute_query(po_query, (supplier_id,), fetch_all=True)
    
    return render_template(
        'suppliers/view.html',
        supplier=supplier,
        recent_pos=recent_pos
    )

# ============================================================================
# CREATE SUPPLIER
# ============================================================================

@suppliers_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create_supplier():
    """Create a new supplier"""
    
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to create suppliers.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    if request.method == 'POST':
        # Get form data
        supplier_code = request.form.get('supplier_code', '').strip().upper()
        supplier_name = request.form.get('supplier_name', '').strip()
        category = request.form.get('category')
        approved_status = request.form.get('approved_status', 'approved')
        approved_processes = request.form.get('approved_processes', '').strip()
        
        # Contact info
        primary_contact = request.form.get('primary_contact', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        
        # Address
        address_line1 = request.form.get('address_line1', '').strip()
        address_line2 = request.form.get('address_line2', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        country = request.form.get('country', '').strip()
        
        notes = request.form.get('notes', '').strip()
        
        # Validation
        errors = []
        
        if not supplier_code:
            errors.append('Supplier code is required.')
        elif not supplier_code.replace('_', '').replace('-', '').isalnum():
            errors.append('Supplier code must contain only letters, numbers, underscore, and hyphen.')
        
        if not supplier_name:
            errors.append('Supplier name is required.')
        
        if not category:
            errors.append('Category is required.')
        
        # Check for duplicate supplier code
        if supplier_code:
            dup_check = execute_query(
                "SELECT supplier_id FROM suppliers WHERE supplier_code = %s",
                (supplier_code,),
                fetch_one=True
            )
            if dup_check:
                errors.append(f'Supplier code {supplier_code} already exists.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('suppliers.create_supplier'))
        
        # Insert supplier
        insert_query = """
            INSERT INTO suppliers (
                supplier_code, supplier_name, category, approved_status,
                approved_processes, primary_contact, email, phone,
                address_line1, address_line2, city, state, postal_code, country,
                notes, approval_date, active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE, TRUE)
            RETURNING supplier_id
        """
        
        try:
            result = execute_query(
                insert_query,
                (supplier_code, supplier_name, category, approved_status, approved_processes,
                 primary_contact, email, phone, address_line1, address_line2,
                 city, state, postal_code, country, notes),
                fetch_one=True
            )
            
            flash(f'Supplier {supplier_code} created successfully.', 'success')
            return redirect(url_for('suppliers.view_supplier', supplier_id=result['supplier_id']))
            
        except Exception as e:
            flash(f'Error creating supplier: {str(e)}', 'danger')
            return redirect(url_for('suppliers.create_supplier'))
    
    return render_template('suppliers/form.html', supplier=None)

# ============================================================================
# EDIT SUPPLIER
# ============================================================================

@suppliers_bp.route('/<supplier_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_supplier(supplier_id):
    """Edit existing supplier"""
    
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to edit suppliers.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    # Get existing supplier
    supplier = execute_query(
        "SELECT * FROM suppliers WHERE supplier_id = %s",
        (supplier_id,),
        fetch_one=True
    )
    
    if not supplier:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    if request.method == 'POST':
        # Get form data (same as create)
        supplier_code = request.form.get('supplier_code', '').strip().upper()
        supplier_name = request.form.get('supplier_name', '').strip()
        category = request.form.get('category')
        approved_status = request.form.get('approved_status')
        approved_processes = request.form.get('approved_processes', '').strip()
        
        primary_contact = request.form.get('primary_contact', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        
        address_line1 = request.form.get('address_line1', '').strip()
        address_line2 = request.form.get('address_line2', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        country = request.form.get('country', '').strip()
        
        notes = request.form.get('notes', '').strip()
        
        # Validation
        errors = []
        
        if not supplier_code:
            errors.append('Supplier code is required.')
        
        if not supplier_name:
            errors.append('Supplier name is required.')
        
        # Check for duplicate code (excluding current supplier)
        if supplier_code != supplier['supplier_code']:
            dup_check = execute_query(
                "SELECT supplier_id FROM suppliers WHERE supplier_code = %s AND supplier_id != %s",
                (supplier_code, supplier_id),
                fetch_one=True
            )
            if dup_check:
                errors.append(f'Supplier code {supplier_code} already exists.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('suppliers.edit_supplier', supplier_id=supplier_id))
        
        # Update supplier
        update_query = """
            UPDATE suppliers
            SET supplier_code = %s, supplier_name = %s, category = %s,
                approved_status = %s, approved_processes = %s,
                primary_contact = %s, email = %s, phone = %s,
                address_line1 = %s, address_line2 = %s, city = %s,
                state = %s, postal_code = %s, country = %s, notes = %s
            WHERE supplier_id = %s
        """
        
        try:
            execute_query(
                update_query,
                (supplier_code, supplier_name, category, approved_status, approved_processes,
                 primary_contact, email, phone, address_line1, address_line2,
                 city, state, postal_code, country, notes, supplier_id)
            )
            
            flash(f'Supplier {supplier_code} updated successfully.', 'success')
            return redirect(url_for('suppliers.view_supplier', supplier_id=supplier_id))
            
        except Exception as e:
            flash(f'Error updating supplier: {str(e)}', 'danger')
            return redirect(url_for('suppliers.edit_supplier', supplier_id=supplier_id))
    
    return render_template('suppliers/form.html', supplier=supplier)

# ============================================================================
# DEACTIVATE SUPPLIER
# ============================================================================

@suppliers_bp.route('/<supplier_id>/deactivate', methods=['POST'])
@login_required
def deactivate_supplier(supplier_id):
    """Deactivate a supplier"""
    
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to deactivate suppliers.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    supplier = execute_query(
        "SELECT supplier_code FROM suppliers WHERE supplier_id = %s",
        (supplier_id,),
        fetch_one=True
    )
    
    if not supplier:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    # Check for active OS POs
    active_pos = execute_query(
        "SELECT COUNT(*) as count FROM outside_service_pos WHERE supplier_id = %s AND status IN ('draft', 'sent', 'in_process')",
        (supplier_id,),
        fetch_one=True
    )
    
    if active_pos['count'] > 0:
        flash(f'Cannot deactivate supplier with {active_pos["count"]} active outside service PO(s).', 'warning')
        return redirect(url_for('suppliers.view_supplier', supplier_id=supplier_id))
    
    # Deactivate
    execute_query(
        "UPDATE suppliers SET active = FALSE WHERE supplier_id = %s",
        (supplier_id,)
    )
    
    flash(f'Supplier {supplier["supplier_code"]} deactivated.', 'success')
    return redirect(url_for('suppliers.list_suppliers'))

# ============================================================================
# REACTIVATE SUPPLIER
# ============================================================================

@suppliers_bp.route('/<supplier_id>/reactivate', methods=['POST'])
@login_required
def reactivate_supplier(supplier_id):
    """Reactivate a supplier"""
    
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to reactivate suppliers.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    supplier = execute_query(
        "SELECT supplier_code FROM suppliers WHERE supplier_id = %s",
        (supplier_id,),
        fetch_one=True
    )
    
    if not supplier:
        flash('Supplier not found.', 'danger')
        return redirect(url_for('suppliers.list_suppliers'))
    
    execute_query(
        "UPDATE suppliers SET active = TRUE WHERE supplier_id = %s",
        (supplier_id,)
    )
    
    flash(f'Supplier {supplier["supplier_code"]} reactivated.', 'success')
    return redirect(url_for('suppliers.view_supplier', supplier_id=supplier_id))

# ============================================================================
# EXPORT SUPPLIERS TO CSV
# ============================================================================

@suppliers_bp.route('/export')
@login_required
def export_suppliers():
    """Export all suppliers to CSV file"""
    
    # Permission check - office and above
    if not current_user.is_office():
        flash('You do not have permission to export suppliers.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get all suppliers with all fields
    query = """
        SELECT 
            supplier_code,
            supplier_name,
            primary_contact,
            phone,
            email,
            address_line1,
            address_line2,
            city,
            state,
            postal_code,
            country,
            category,
            approved_status,
            approved_processes,
            notes,
            active
        FROM suppliers
        ORDER BY supplier_code
    """
    
    suppliers = execute_query(query, fetch_all=True)
    
    # Create CSV content
    import csv
    import io
    from flask import make_response
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'supplier_code', 'supplier_name', 'primary_contact', 'phone', 'email',
        'address_line1', 'address_line2', 'city', 'state',
        'postal_code', 'country', 'category', 'approved_status', 
        'approved_processes', 'notes', 'active'
    ])
    
    # Write data rows
    for supplier in suppliers:
        writer.writerow([
            supplier['supplier_code'],
            supplier['supplier_name'],
            supplier['primary_contact'] or '',
            supplier['phone'] or '',
            supplier['email'] or '',
            supplier['address_line1'] or '',
            supplier['address_line2'] or '',
            supplier['city'] or '',
            supplier['state'] or '',
            supplier['postal_code'] or '',
            supplier['country'] or '',
            supplier['category'] or '',
            supplier['approved_status'] or '',
            supplier['approved_processes'] or '',
            supplier['notes'] or '',
            'TRUE' if supplier['active'] else 'FALSE'
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = 'attachment; filename=suppliers_export.csv'
    response.headers['Content-Type'] = 'text/csv'
    
    return response
