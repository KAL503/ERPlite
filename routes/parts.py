"""
Parts Module - CRUD operations for parts and part revisions
ISO 9001: 7.5, 8.5.2
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import execute_query, get_db_cursor
import uuid
import os
from datetime import date

parts_bp = Blueprint('parts', __name__)

# ============================================================================
# LIST / VIEW ALL PARTS
# ============================================================================

@parts_bp.route('/')
@login_required
def list_parts():
    """List all parts"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access parts management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get filter parameters
    search = request.args.get('search', '').strip()
    customer_id = request.args.get('customer_id', '').strip()
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    # Build query - use DISTINCT ON to pick one revision per part (most recent if multiple current)
    query = """
        SELECT DISTINCT ON (p.part_id)
            p.part_id,
            p.customer_part_number,
            p.description,
            p.material,
            p.finish,
            p.active,
            c.customer_code,
            c.company_name,
            COUNT(*) OVER (PARTITION BY p.part_id) as revision_count,
            pr.revision_level as current_revision
        FROM parts p
        JOIN customers c ON p.customer_id = c.customer_id
        LEFT JOIN part_revisions pr ON p.part_id = pr.part_id 
            AND pr.superseded_date IS NULL
        WHERE 1=1
    """
    params = []
    
    if active_only:
        query += " AND p.active = TRUE"
    
    if customer_id:
        query += " AND p.customer_id = %s"
        params.append(customer_id)
    
    if search:
        query += """ AND (
            LOWER(p.customer_part_number) LIKE LOWER(%s) OR
            LOWER(p.description) LIKE LOWER(%s) OR
            LOWER(p.material) LIKE LOWER(%s)
        )"""
        search_pattern = f'%{search}%'
        params.extend([search_pattern, search_pattern, search_pattern])
    
    query += """
        ORDER BY p.part_id, pr.effective_date DESC NULLS LAST, pr.revision_level DESC
    """
    
    parts = execute_query(query, tuple(params) if params else None, fetch_all=True)
    
    # Get all customers for filter dropdown
    customers_query = """
        SELECT customer_id, customer_code, company_name
        FROM customers
        WHERE active = TRUE
        ORDER BY company_name
    """
    customers = execute_query(customers_query, fetch_all=True)
    
    return render_template(
        'parts/list.html',
        parts=parts,
        customers=customers,
        search=search,
        selected_customer_id=customer_id,
        active_only=active_only
    )

# ============================================================================
# VIEW SINGLE PART WITH REVISIONS
# ============================================================================

@parts_bp.route('/<part_id>')
@login_required
def view_part(part_id):
    """View detailed part information with revisions"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access parts management.', 'danger')
        return redirect(url_for('dashboard'))
    
    query = """
        SELECT 
            p.*,
            c.customer_code,
            c.company_name,
            u.full_name as created_by_name
        FROM parts p
        JOIN customers c ON p.customer_id = c.customer_id
        LEFT JOIN users u ON p.created_by = u.user_id
        WHERE p.part_id = %s
    """
    part = execute_query(query, (part_id,), fetch_one=True)
    
    if not part:
        flash('Part not found.', 'danger')
        return redirect(url_for('parts.list_parts'))
    
    # Get all revisions for this part
    revisions_query = """
        SELECT 
            pr.*,
            u.full_name as created_by_name,
            CASE WHEN pr.superseded_date IS NULL THEN TRUE ELSE FALSE END as is_current
        FROM part_revisions pr
        LEFT JOIN users u ON pr.created_by = u.user_id
        WHERE pr.part_id = %s
        ORDER BY pr.effective_date DESC
    """
    revisions = execute_query(revisions_query, (part_id,), fetch_all=True)
    
    # Get recent work orders for this part
    wo_query = """
        SELECT 
            wo.work_order_number,
            wo.status,
            wo.production_due_date,
            wo.quantity_ordered,
            pr.revision_level
        FROM work_orders wo
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        WHERE wo.part_id = %s
        ORDER BY wo.created_at DESC
        LIMIT 10
    """
    recent_work_orders = execute_query(wo_query, (part_id,), fetch_all=True)
    
    return render_template(
        'parts/view.html',
        part=part,
        revisions=revisions,
        recent_work_orders=recent_work_orders
    )

# ============================================================================
# CREATE NEW PART
# ============================================================================

@parts_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create_part():
    """Create a new part"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access parts management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only office and above can create parts
    if not current_user.can_create_work_orders():
        flash('You do not have permission to create parts.', 'danger')
        return redirect(url_for('parts.list_parts'))
    
    if request.method == 'POST':
        # Get form data
        customer_id = request.form.get('customer_id', '').strip()
        customer_part_number = request.form.get('customer_part_number', '').strip()
        description = request.form.get('description', '').strip()
        material = request.form.get('material', '').strip()
        finish = request.form.get('finish', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # Initial revision data
        revision_level = request.form.get('revision_level', '').strip()
        drawing_file_path = request.form.get('drawing_file_path', '').strip()
        effective_date = request.form.get('effective_date', '').strip()
        
        # Validate required fields
        if not customer_id or not customer_part_number:
            flash('Customer and part number are required.', 'danger')
            return render_template('parts/form.html', form_data=request.form, customers=get_customers())
        
        if not revision_level:
            flash('Initial revision level is required (e.g., A, 01, Rev A).', 'danger')
            return render_template('parts/form.html', form_data=request.form, customers=get_customers())
        
        if not effective_date:
            flash('Effective date is required for initial revision.', 'danger')
            return render_template('parts/form.html', form_data=request.form, customers=get_customers())
        
        # Check for duplicate part number for this customer
        check_query = """
            SELECT part_id FROM parts 
            WHERE customer_id = %s AND customer_part_number = %s
        """
        existing = execute_query(check_query, (customer_id, customer_part_number), fetch_one=True)
        
        if existing:
            flash(f'Part number "{customer_part_number}" already exists for this customer.', 'danger')
            return render_template('parts/form.html', form_data=request.form, customers=get_customers())
        
        # Insert new part with initial revision in transaction
        try:
            # Insert part
            insert_part_query = """
                INSERT INTO parts (
                    customer_id, customer_part_number, description,
                    material, finish, notes, active, created_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                RETURNING part_id
            """
            
            part_result = execute_query(
                insert_part_query,
                (customer_id, customer_part_number, description,
                 material, finish, notes, True, current_user.user_id),
                fetch_one=True
            )
            
            part_id = part_result['part_id']
            
            # Insert additional customers if provided
            additional_customers = request.form.getlist('additional_customers')
            if additional_customers:
                for add_customer_id in additional_customers:
                    if add_customer_id and add_customer_id != customer_id:  # Don't duplicate primary
                        execute_query(
                            "INSERT INTO part_customers (part_id, customer_id, is_primary) VALUES (%s, %s, FALSE)",
                            (part_id, add_customer_id)
                        )
            
            # Insert initial revision
            insert_revision_query = """
                INSERT INTO part_revisions (
                    part_id, revision_level, drawing_file_path, 
                    effective_date, superseded_date, created_by
                ) VALUES (
                    %s, %s, %s, %s, NULL, %s
                )
            """
            
            execute_query(
                insert_revision_query,
                (part_id, revision_level, drawing_file_path or None,
                 effective_date, current_user.user_id)
            )
            
            flash(f'Part "{customer_part_number}" created successfully with revision {revision_level}.', 'success')
            return redirect(url_for('parts.view_part', part_id=part_id))
            
        except Exception as e:
            flash(f'Error creating part: {str(e)}', 'danger')
            return render_template('parts/form.html', form_data=request.form, customers=get_customers())
    
    # GET request - show empty form
    return render_template('parts/form.html', 
                         form_data=None, 
                         customers=get_customers(),
                         today=date.today().isoformat())

# ============================================================================
# EDIT PART
# ============================================================================

@parts_bp.route('/<part_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_part(part_id):
    """Edit existing part"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access parts management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only office and above can edit parts
    if not current_user.can_create_work_orders():
        flash('You do not have permission to edit parts.', 'danger')
        return redirect(url_for('parts.view_part', part_id=part_id))
    
    # Get existing part
    query = "SELECT * FROM parts WHERE part_id = %s"
    part = execute_query(query, (part_id,), fetch_one=True)
    
    if not part:
        flash('Part not found.', 'danger')
        return redirect(url_for('parts.list_parts'))
    
    if request.method == 'POST':
        # Get form data
        customer_id = request.form.get('customer_id', '').strip()
        customer_part_number = request.form.get('customer_part_number', '').strip()
        description = request.form.get('description', '').strip()
        material = request.form.get('material', '').strip()
        finish = request.form.get('finish', '').strip()
        notes = request.form.get('notes', '').strip()
        active = request.form.get('active') == 'on'
        
        # Validate required fields
        if not customer_id or not customer_part_number:
            flash('Customer and part number are required.', 'danger')
            return render_template('parts/form.html', form_data=request.form, part=part, customers=get_customers())
        
        # Check for duplicate part number (excluding current part)
        check_query = """
            SELECT part_id FROM parts 
            WHERE customer_id = %s AND customer_part_number = %s AND part_id != %s
        """
        existing = execute_query(check_query, (customer_id, customer_part_number, part_id), fetch_one=True)
        
        if existing:
            flash(f'Part number "{customer_part_number}" already exists for this customer.', 'danger')
            return render_template('parts/form.html', form_data=request.form, part=part, customers=get_customers())
        
        # Update part
        update_query = """
            UPDATE parts SET
                customer_id = %s,
                customer_part_number = %s,
                description = %s,
                material = %s,
                finish = %s,
                notes = %s,
                active = %s
            WHERE part_id = %s
        """
        
        try:
            execute_query(
                update_query,
                (customer_id, customer_part_number, description,
                 material, finish, notes, active, part_id)
            )
            
            # Handle additional customers
            # First, remove existing additional customers
            execute_query(
                "DELETE FROM part_customers WHERE part_id = %s",
                (part_id,)
            )
            
            # Then add new ones
            additional_customers = request.form.getlist('additional_customers')
            if additional_customers:
                for add_customer_id in additional_customers:
                    if add_customer_id and add_customer_id != customer_id:  # Don't duplicate primary
                        execute_query(
                            "INSERT INTO part_customers (part_id, customer_id, is_primary) VALUES (%s, %s, FALSE)",
                            (part_id, add_customer_id)
                        )
            
            flash(f'Part "{customer_part_number}" updated successfully.', 'success')
            return redirect(url_for('parts.view_part', part_id=part_id))
            
        except Exception as e:
            flash(f'Error updating part: {str(e)}', 'danger')
            return render_template('parts/form.html', form_data=request.form, part=part, customers=get_customers())
    
    # GET request - show form with existing data
    # Get existing additional customers
    existing_additional = execute_query(
        "SELECT customer_id FROM part_customers WHERE part_id = %s",
        (part_id,),
        fetch_all=True
    )
    additional_customer_ids = [str(row['customer_id']) for row in existing_additional] if existing_additional else []
    
    return render_template('parts/form.html', 
                         form_data=part, 
                         part=part, 
                         customers=get_customers(),
                         additional_customer_ids=additional_customer_ids)

# ============================================================================
# ADD PART REVISION
# ============================================================================

@parts_bp.route('/<part_id>/revisions/new', methods=['GET', 'POST'])
@login_required
def add_revision(part_id):
    """Add a new revision to a part"""
    # Permission check
    if not current_user.is_office():
        flash('You do not have permission to access parts management.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Only office and above can add revisions
    if not current_user.can_create_work_orders():
        flash('You do not have permission to add revisions.', 'danger')
        return redirect(url_for('parts.view_part', part_id=part_id))
    
    # Get part info
    part_query = """
        SELECT p.*, c.company_name
        FROM parts p
        JOIN customers c ON p.customer_id = c.customer_id
        WHERE p.part_id = %s
    """
    part = execute_query(part_query, (part_id,), fetch_one=True)
    
    if not part:
        flash('Part not found.', 'danger')
        return redirect(url_for('parts.list_parts'))
    
    if request.method == 'POST':
        revision_level = request.form.get('revision_level', '').strip()
        effective_date = request.form.get('effective_date', '').strip()
        supersede_previous = request.form.get('supersede_previous') == 'on'
        
        # Validate required fields
        if not revision_level or not effective_date:
            flash('Revision level and effective date are required.', 'danger')
            return render_template('parts/revision_form.html', part=part, form_data=request.form)
        
        # Check for duplicate revision level
        check_query = """
            SELECT revision_id FROM part_revisions 
            WHERE part_id = %s AND revision_level = %s
        """
        existing = execute_query(check_query, (part_id, revision_level), fetch_one=True)
        
        if existing:
            flash(f'Revision "{revision_level}" already exists for this part.', 'danger')
            return render_template('parts/revision_form.html', part=part, form_data=request.form)
        
        try:
            with get_db_cursor() as cur:
                # If superseding previous revisions, mark them as superseded
                if supersede_previous:
                    supersede_query = """
                        UPDATE part_revisions
                        SET superseded_date = %s
                        WHERE part_id = %s AND superseded_date IS NULL
                    """
                    cur.execute(supersede_query, (effective_date, part_id))
                
                # Insert new revision
                insert_query = """
                    INSERT INTO part_revisions (
                        part_id, revision_level, effective_date, created_by
                    ) VALUES (
                        %s, %s, %s, %s
                    )
                    RETURNING revision_id
                """
                cur.execute(
                    insert_query,
                    (part_id, revision_level, effective_date, current_user.user_id)
                )
                result = cur.fetchone()
            
            flash(f'Revision "{revision_level}" added successfully.', 'success')
            return redirect(url_for('parts.view_part', part_id=part_id))
            
        except Exception as e:
            flash(f'Error adding revision: {str(e)}', 'danger')
            return render_template('parts/revision_form.html', part=part, form_data=request.form)
    
    # GET request - show form
    return render_template('parts/revision_form.html', part=part, form_data=None)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_customers():
    """Get all active customers for dropdown"""
    query = """
        SELECT customer_id, customer_code, company_name
        FROM customers
        WHERE active = TRUE
        ORDER BY company_name
    """
    return execute_query(query, fetch_all=True)
