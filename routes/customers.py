"""
Customers Module - CRUD operations for customer master data
ISO 9001: 8.2
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import execute_query, get_db_cursor
import uuid

customers_bp = Blueprint('customers', __name__)

# ============================================================================
# LIST / VIEW ALL CUSTOMERS
# ============================================================================

@customers_bp.route('/')
@login_required
def list_customers():
    """List all customers"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access customer management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    # Build query
    query = """
        SELECT 
            customer_id,
            customer_code,
            company_name,
            city,
            state,
            primary_contact_name,
            primary_contact_email,
            primary_contact_phone,
            active
        FROM customers
        WHERE 1=1
    """
    params = []
    
    if active_only:
        query += " AND active = TRUE"
    
    if search:
        query += """ AND (
            LOWER(customer_code) LIKE LOWER(%s) OR
            LOWER(company_name) LIKE LOWER(%s) OR
            LOWER(city) LIKE LOWER(%s)
        )"""
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])
    
    query += " ORDER BY company_name"
    
    customers = execute_query(query, tuple(params) if params else None, fetch_all=True)
    
    return render_template(
        'customers/list.html',
        customers=customers,
        search=search,
        active_only=active_only
    )

# ============================================================================
# VIEW SINGLE CUSTOMER
# ============================================================================

@customers_bp.route('/<customer_id>')
@login_required
def view_customer(customer_id):
    """View detailed customer information"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access customer management.', 'danger')
        return redirect(url_for('dashboard'))
    
    query = """
        SELECT *
        FROM customers
        WHERE customer_id = %s
    """
    customer = execute_query(query, (customer_id,), fetch_one=True)
    
    if not customer:
        flash('Customer not found.', 'danger')
        return redirect(url_for('customers.list_customers'))
    
    # Get associated parts count
    parts_query = """
        SELECT COUNT(*) as part_count
        FROM parts
        WHERE customer_id = %s AND active = TRUE
    """
    parts_count = execute_query(parts_query, (customer_id,), fetch_one=True)
    
    # Get recent work orders
    wo_query = """
        SELECT 
            wo.work_order_number,
            wo.status,
            wo.production_due_date,
            p.customer_part_number,
            p.description
        FROM work_orders wo
        JOIN parts p ON wo.part_id = p.part_id
        WHERE wo.customer_id = %s
        ORDER BY wo.created_at DESC
        LIMIT 10
    """
    recent_work_orders = execute_query(wo_query, (customer_id,), fetch_all=True)
    
    return render_template(
        'customers/view.html',
        customer=customer,
        parts_count=parts_count['part_count'] if parts_count else 0,
        recent_work_orders=recent_work_orders
    )

# ============================================================================
# CREATE NEW CUSTOMER
# ============================================================================

@customers_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create_customer():
    """Create a new customer"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access customer management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only office and above can create customers
    if not current_user.can_create_work_orders():
        flash('You do not have permission to create customers.', 'danger')
        return redirect(url_for('customers.list_customers'))
    
    if request.method == 'POST':
        # Get form data
        customer_code = request.form.get('customer_code', '').strip().upper()
        company_name = request.form.get('company_name', '').strip()
        address_line1 = request.form.get('address_line1', '').strip()
        address_line2 = request.form.get('address_line2', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        country = request.form.get('country', 'USA').strip()
        primary_contact_name = request.form.get('primary_contact_name', '').strip()
        primary_contact_email = request.form.get('primary_contact_email', '').strip()
        primary_contact_phone = request.form.get('primary_contact_phone', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # Validate required fields
        if not customer_code or not company_name:
            flash('Customer code and company name are required.', 'danger')
            return render_template('customers/form.html', form_data=request.form)
        
        # Check for duplicate customer code
        check_query = "SELECT customer_id FROM customers WHERE customer_code = %s"
        existing = execute_query(check_query, (customer_code,), fetch_one=True)
        
        if existing:
            flash(f'Customer code "{customer_code}" already exists.', 'danger')
            return render_template('customers/form.html', form_data=request.form)
        
        # Insert new customer
        insert_query = """
            INSERT INTO customers (
                customer_code, company_name, address_line1, address_line2,
                city, state, postal_code, country,
                primary_contact_name, primary_contact_email, primary_contact_phone,
                notes, active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE
            )
            RETURNING customer_id
        """
        
        try:
            result = execute_query(
                insert_query,
                (customer_code, company_name, address_line1, address_line2,
                 city, state, postal_code, country,
                 primary_contact_name, primary_contact_email, primary_contact_phone,
                 notes),
                fetch_one=True
            )
            
            flash(f'Customer "{company_name}" created successfully.', 'success')
            return redirect(url_for('customers.view_customer', customer_id=result['customer_id']))
            
        except Exception as e:
            flash(f'Error creating customer: {str(e)}', 'danger')
            return render_template('customers/form.html', form_data=request.form)
    
    # GET request - show empty form
    return render_template('customers/form.html', form_data=None)

# ============================================================================
# EDIT CUSTOMER
# ============================================================================

@customers_bp.route('/<customer_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_customer(customer_id):
    """Edit existing customer"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access customer management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only office and above can edit customers
    if not current_user.can_create_work_orders():
        flash('You do not have permission to edit customers.', 'danger')
        return redirect(url_for('customers.view_customer', customer_id=customer_id))
    
    # Get existing customer
    query = "SELECT * FROM customers WHERE customer_id = %s"
    customer = execute_query(query, (customer_id,), fetch_one=True)
    
    if not customer:
        flash('Customer not found.', 'danger')
        return redirect(url_for('customers.list_customers'))
    
    if request.method == 'POST':
        # Get form data
        customer_code = request.form.get('customer_code', '').strip().upper()
        company_name = request.form.get('company_name', '').strip()
        address_line1 = request.form.get('address_line1', '').strip()
        address_line2 = request.form.get('address_line2', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        postal_code = request.form.get('postal_code', '').strip()
        country = request.form.get('country', 'USA').strip()
        primary_contact_name = request.form.get('primary_contact_name', '').strip()
        primary_contact_email = request.form.get('primary_contact_email', '').strip()
        primary_contact_phone = request.form.get('primary_contact_phone', '').strip()
        notes = request.form.get('notes', '').strip()
        active = request.form.get('active') == 'on'
        
        # Validate required fields
        if not customer_code or not company_name:
            flash('Customer code and company name are required.', 'danger')
            return render_template('customers/form.html', form_data=request.form, customer=customer)
        
        # Check for duplicate customer code (excluding current customer)
        check_query = """
            SELECT customer_id FROM customers 
            WHERE customer_code = %s AND customer_id != %s
        """
        existing = execute_query(check_query, (customer_code, customer_id), fetch_one=True)
        
        if existing:
            flash(f'Customer code "{customer_code}" already exists.', 'danger')
            return render_template('customers/form.html', form_data=request.form, customer=customer)
        
        # Update customer
        update_query = """
            UPDATE customers SET
                customer_code = %s,
                company_name = %s,
                address_line1 = %s,
                address_line2 = %s,
                city = %s,
                state = %s,
                postal_code = %s,
                country = %s,
                primary_contact_name = %s,
                primary_contact_email = %s,
                primary_contact_phone = %s,
                notes = %s,
                active = %s
            WHERE customer_id = %s
        """
        
        try:
            execute_query(
                update_query,
                (customer_code, company_name, address_line1, address_line2,
                 city, state, postal_code, country,
                 primary_contact_name, primary_contact_email, primary_contact_phone,
                 notes, active, customer_id)
            )
            
            flash(f'Customer "{company_name}" updated successfully.', 'success')
            return redirect(url_for('customers.view_customer', customer_id=customer_id))
            
        except Exception as e:
            flash(f'Error updating customer: {str(e)}', 'danger')
            return render_template('customers/form.html', form_data=request.form, customer=customer)
    
    # GET request - show form with existing data
    return render_template('customers/form.html', form_data=customer, customer=customer)

# ============================================================================
# DELETE / DEACTIVATE CUSTOMER
# ============================================================================

@customers_bp.route('/<customer_id>/deactivate', methods=['POST'])
@login_required
def deactivate_customer(customer_id):
    """Deactivate a customer (soft delete)"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access customer management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only owner can deactivate customers
    if not current_user.is_owner():
        flash('Only owners can deactivate customers.', 'danger')
        return redirect(url_for('customers.view_customer', customer_id=customer_id))
    
    query = "UPDATE customers SET active = FALSE WHERE customer_id = %s"
    
    try:
        execute_query(query, (customer_id,))
        flash('Customer deactivated successfully.', 'success')
    except Exception as e:
        flash(f'Error deactivating customer: {str(e)}', 'danger')
    
    return redirect(url_for('customers.list_customers'))
