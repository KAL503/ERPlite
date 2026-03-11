"""
Shop Floor Operations Module - Operation Sign-Off
ISO 9001: 8.5.1 (Production control)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from database import execute_query
from datetime import datetime

shop_floor_bp = Blueprint('shop_floor', __name__)

# ============================================================================
# MY OPERATIONS VIEW - Role-filtered active operations
# ============================================================================

@shop_floor_bp.route('/')
@login_required
def my_operations():
    """Show work orders with available operations for current user"""
    
    # Determine which operation types this user can work on
    allowed_types = get_allowed_operation_types(current_user)
    
    if not allowed_types:
        flash('Your role does not have permission to sign off operations.', 'warning')
        return redirect(url_for('dashboard'))
    
    # Build query to get work orders that have operations for this user's role
    type_placeholders = ','.join(['%s'] * len(allowed_types))
    
    query = f"""
        SELECT DISTINCT
            wo.work_order_id,
            wo.work_order_number,
            wo.quantity_ordered,
            wo.quantity_completed,
            wo.production_due_date,
            wo.status as wo_status,
            c.customer_code,
            c.company_name,
            p.customer_part_number,
            pr.revision_level,
            (SELECT COUNT(*) FROM work_order_operations 
             WHERE work_order_id = wo.work_order_id 
               AND operation_type IN ({type_placeholders})
               AND status IN ('pending', 'in_progress')) as available_op_count,
            (SELECT COUNT(*) FROM work_order_operations 
             WHERE work_order_id = wo.work_order_id 
               AND operation_type IN ({type_placeholders})
               AND status = 'in_progress'
               AND start_by = %s) as my_in_progress_count,
            (SELECT COUNT(*) FROM ncrs WHERE work_order_id = wo.work_order_id AND status != 'closed') as open_ncr_count
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        WHERE EXISTS (
            SELECT 1 FROM work_order_operations wop
            WHERE wop.work_order_id = wo.work_order_id
              AND wop.operation_type IN ({type_placeholders})
              AND wop.status IN ('pending', 'in_progress')
        )
        AND wo.status IN ('released_to_floor', 'in_production', 'final_inspection')
        ORDER BY 
            wo.production_due_date ASC NULLS LAST,
            wo.work_order_number ASC
    """
    
    # Pass allowed_types three times: for first subquery, second subquery, and EXISTS clause
    work_orders = execute_query(
        query, 
        tuple(allowed_types) + tuple(allowed_types) + (current_user.user_id,) + tuple(allowed_types),
        fetch_all=True
    )
    
    return render_template(
        'shop_floor/my_work_orders.html',
        work_orders=work_orders,
        allowed_types=allowed_types,
        today=datetime.now().date()
    )

# ============================================================================
# WORK ORDER OPERATIONS LIST
# ============================================================================

@shop_floor_bp.route('/work-order/<work_order_id>')
@login_required
def work_order_operations(work_order_id):
    """Show all available operations for a specific work order"""
    
    allowed_types = get_allowed_operation_types(current_user)
    
    if not allowed_types:
        flash('Your role does not have permission to sign off operations.', 'warning')
        return redirect(url_for('dashboard'))
    
    # Get work order info
    wo_query = """
        SELECT wo.*, c.customer_code, c.company_name, 
               p.customer_part_number, pr.revision_level,
               (SELECT COUNT(*) FROM ncrs WHERE work_order_id = wo.work_order_id AND status != 'closed') as open_ncr_count
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        WHERE wo.work_order_id = %s
    """
    
    work_order = execute_query(wo_query, (work_order_id,), fetch_one=True)
    
    if not work_order:
        flash('Work order not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    # Get operations for this user's role
    type_placeholders = ','.join(['%s'] * len(allowed_types))
    
    ops_query = f"""
        SELECT 
            wop.*,
            u_start.initials as started_by_initials,
            u_start.full_name as started_by_name,
            u_end.initials as ended_by_initials,
            u_end.full_name as ended_by_name
        FROM work_order_operations wop
        LEFT JOIN users u_start ON wop.start_by = u_start.user_id
        LEFT JOIN users u_end ON wop.end_by = u_end.user_id
        WHERE wop.work_order_id = %s
          AND wop.operation_type IN ({type_placeholders})
          AND wop.status IN ('pending', 'in_progress')
        ORDER BY wop.sequence_number ASC
    """
    
    operations = execute_query(ops_query, (work_order_id,) + tuple(allowed_types), fetch_all=True)
    
    return render_template(
        'shop_floor/work_order_operations.html',
        work_order=work_order,
        operations=operations,
        allowed_types=allowed_types
    )

# ============================================================================
# OPERATION DETAIL VIEW
# ============================================================================

@shop_floor_bp.route('/operation/<operation_id>')
@login_required
def view_operation(operation_id):
    """View single operation detail with start/complete options"""
    
    query = """
        SELECT 
            wop.*,
            wo.work_order_number,
            wo.quantity_ordered,
            wo.production_due_date,
            wo.status as wo_status,
            wo.fai_required,
            wo.aql_required,
            c.customer_code,
            c.company_name,
            p.customer_part_number,
            p.description as part_description,
            pr.revision_level,
            pr.drawing_file_path,
            u_start.full_name as started_by_name,
            u_start.initials as started_by_initials,
            u_end.full_name as ended_by_name,
            u_end.initials as ended_by_initials,
            (SELECT COUNT(*) FROM ncrs WHERE work_order_id = wo.work_order_id AND status != 'closed') as open_ncr_count
        FROM work_order_operations wop
        JOIN work_orders wo ON wop.work_order_id = wo.work_order_id
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        LEFT JOIN users u_start ON wop.start_by = u_start.user_id
        LEFT JOIN users u_end ON wop.end_by = u_end.user_id
        WHERE wop.operation_id = %s
    """
    
    operation = execute_query(query, (operation_id,), fetch_one=True)
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    # Check if user has permission for this operation type
    allowed_types = get_allowed_operation_types(current_user)
    if operation['operation_type'] not in allowed_types:
        flash('You do not have permission to work on this operation type.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    # Get previous operations in sequence to show context
    prev_ops_query = """
        SELECT operation_code, operation_description, status
        FROM work_order_operations
        WHERE work_order_id = %s 
          AND stream_id = %s
          AND sequence_number < %s
        ORDER BY sequence_number DESC
        LIMIT 3
    """
    previous_operations = execute_query(
        prev_ops_query,
        (operation['work_order_id'], operation['stream_id'], operation['sequence_number']),
        fetch_all=True
    )
    
    # Get next operations
    next_ops_query = """
        SELECT operation_code, operation_description, status
        FROM work_order_operations
        WHERE work_order_id = %s 
          AND stream_id = %s
          AND sequence_number > %s
        ORDER BY sequence_number ASC
        LIMIT 3
    """
    next_operations = execute_query(
        next_ops_query,
        (operation['work_order_id'], operation['stream_id'], operation['sequence_number']),
        fetch_all=True
    )
    
    can_start = check_can_start_operation(operation, current_user)
    can_complete = check_can_complete_operation(operation, current_user)
    can_reopen = check_can_reopen_operation(operation, current_user)
    
    # Get active outside service suppliers for dropdown
    suppliers_query = """
        SELECT supplier_id, supplier_code, supplier_name
        FROM suppliers
        WHERE category = 'outside_service' AND active = TRUE
        ORDER BY supplier_code
    """
    os_suppliers = execute_query(suppliers_query, fetch_all=True)
    
    return render_template(
        'shop_floor/operation_detail.html',
        op=operation,
        previous_operations=previous_operations,
        next_operations=next_operations,
        can_start=can_start,
        can_complete=can_complete,
        can_reopen=can_reopen,
        os_suppliers=os_suppliers
    )

# ============================================================================
# START OPERATION
# ============================================================================

@shop_floor_bp.route('/operation/<operation_id>/start', methods=['POST'])
@login_required
def start_operation(operation_id):
    """Start an operation - capture timestamp, user, optional machine"""
    
    op_query = """
        SELECT wop.*, wo.status as wo_status
        FROM work_order_operations wop
        JOIN work_orders wo ON wop.work_order_id = wo.work_order_id
        WHERE wop.operation_id = %s
    """
    operation = execute_query(op_query, (operation_id,), fetch_one=True)
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    # Permission check
    allowed_types = get_allowed_operation_types(current_user)
    if operation['operation_type'] not in allowed_types:
        flash('You do not have permission to start this operation.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    can_start, errors = check_can_start_operation(operation, current_user)
    if not can_start:
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    # Get form data
    machine_actual = request.form.get('machine_actual', '').strip()
    quantity_started = request.form.get('quantity_started', '').strip()
    notes = request.form.get('notes', '').strip()
    
    if quantity_started:
        try:
            quantity_started = int(quantity_started)
            if quantity_started <= 0:
                raise ValueError()
        except ValueError:
            flash('Quantity started must be a positive number.', 'danger')
            return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    else:
        quantity_started = None
    
    update_query = """
        UPDATE work_order_operations
        SET status = 'in_progress',
            start_date = CURRENT_TIMESTAMP,
            start_by = %s,
            machine_number_actual = %s,
            quantity_started = %s,
            notes = CASE 
                WHEN %s IS NOT NULL AND LENGTH(%s) > 0 
                THEN COALESCE(notes || E'\\n\\n', '') || '[' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI') || ' - ' || %s || '] ' || %s
                ELSE notes
            END
        WHERE operation_id = %s
    """
    
    try:
        execute_query(
            update_query,
            (current_user.user_id, machine_actual or None, quantity_started,
             notes, notes, current_user.initials, notes, operation_id)
        )
        
        # Update work order status if this is the first operation started
        wo_update_query = """
            UPDATE work_orders
            SET status = 'in_production'
            WHERE work_order_id = %s
              AND status = 'released_to_floor'
        """
        execute_query(wo_update_query, (operation['work_order_id'],))
        
        flash(f'Operation {operation["operation_code"]} started successfully.', 'success')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
        
    except Exception as e:
        flash(f'Error starting operation: {str(e)}', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))

# ============================================================================
# COMPLETE OPERATION
# ============================================================================

@shop_floor_bp.route('/operation/<operation_id>/complete', methods=['POST'])
@login_required
def complete_operation(operation_id):
    """Complete an operation - capture timestamp, qty finished"""
    
    op_query = """
        SELECT wop.*, wo.quantity_ordered
        FROM work_order_operations wop
        JOIN work_orders wo ON wop.work_order_id = wo.work_order_id
        WHERE wop.operation_id = %s
    """
    operation = execute_query(op_query, (operation_id,), fetch_one=True)
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    allowed_types = get_allowed_operation_types(current_user)
    if operation['operation_type'] not in allowed_types:
        flash('You do not have permission to complete this operation.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    can_complete, errors = check_can_complete_operation(operation, current_user)
    if not can_complete:
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    quantity_finished = request.form.get('quantity_finished', '').strip()
    machine_actual = request.form.get('machine_actual', '').strip()
    notes = request.form.get('notes', '').strip()
    
    if not quantity_finished:
        flash('Quantity finished is required.', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    try:
        quantity_this_run = int(quantity_finished)
        if quantity_this_run < 0:
            raise ValueError()
    except ValueError:
        flash('Quantity finished must be a non-negative number.', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    current_qty_finished = operation['quantity_finished'] or 0
    new_total_qty = current_qty_finished + quantity_this_run
    
    should_complete = (new_total_qty >= operation['quantity_ordered']) or (quantity_this_run == 0 and new_total_qty == 0)
    new_status = 'complete' if should_complete else 'in_progress'
    
    update_query = """
        UPDATE work_order_operations
        SET status = %s,
            end_date = CASE WHEN %s = 'complete' THEN CURRENT_TIMESTAMP ELSE end_date END,
            end_by = CASE WHEN %s = 'complete' THEN %s ELSE end_by END,
            quantity_finished = %s,
            machine_number_actual = COALESCE(%s, machine_number_actual),
            notes = CASE 
                WHEN %s IS NOT NULL AND LENGTH(%s) > 0 
                THEN COALESCE(notes || E'\\n\\n', '') || '[' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI') || ' - ' || %s || '] Completed ' || %s || ' parts (Total: ' || %s || '/' || %s || ')' || CASE WHEN LENGTH(%s) > 0 THEN E'\\n' || %s ELSE '' END
                ELSE COALESCE(notes || E'\\n\\n', '') || '[' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI') || ' - ' || %s || '] Completed ' || %s || ' parts (Total: ' || %s || '/' || %s || ')'
            END
        WHERE operation_id = %s
    """
    
    try:
        execute_query(
            update_query,
            (new_status, new_status, new_status, current_user.user_id, 
             new_total_qty, machine_actual or None,
             notes, notes, current_user.initials, quantity_this_run, new_total_qty, operation['quantity_ordered'], notes, notes,
             current_user.initials, quantity_this_run, new_total_qty, operation['quantity_ordered'],
             operation_id)
        )
        
        if should_complete:
            flash(f'Operation {operation["operation_code"]} completed - {new_total_qty}/{operation["quantity_ordered"]} parts finished.', 'success')
        else:
            flash(f'Progress recorded - {new_total_qty}/{operation["quantity_ordered"]} parts finished. Operation still in progress.', 'info')
        
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
        
    except Exception as e:
        flash(f'Error completing operation: {str(e)}', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))

# ============================================================================
# REOPEN OPERATION
# ============================================================================

@shop_floor_bp.route('/operation/<operation_id>/reopen', methods=['POST'])
@login_required
def reopen_operation(operation_id):
    """Reopen a completed operation - with audit trail"""
    
    operation = execute_query(
        "SELECT * FROM work_order_operations WHERE operation_id = %s",
        (operation_id,),
        fetch_one=True
    )
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    can_reopen, errors = check_can_reopen_operation(operation, current_user)
    if not can_reopen:
        for error in errors:
            flash(error, 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('You must provide a reason for reopening this operation.', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    update_query = """
        UPDATE work_order_operations
        SET status = 'in_progress',
            notes = COALESCE(notes || E'\\n\\n', '') || 
                    '[' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI') || ' - REOPENED by ' || %s || '] ' || %s
        WHERE operation_id = %s
    """
    
    try:
        execute_query(update_query, (current_user.initials, reason, operation_id))
        flash(f'Operation {operation["operation_code"]} reopened.', 'success')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
        
    except Exception as e:
        flash(f'Error reopening operation: {str(e)}', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))

# ============================================================================
# MANAGER OVERRIDE - Force End Operation
# ============================================================================

@shop_floor_bp.route('/operation/<operation_id>/force-end', methods=['POST'])
@login_required
def force_end_operation(operation_id):
    """Manager override to force-end an in-progress operation (for reassignment)"""
    
    if not current_user.is_tier1():
        flash('You do not have permission to force-end operations.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    operation = execute_query(
        "SELECT * FROM work_order_operations WHERE operation_id = %s",
        (operation_id,),
        fetch_one=True
    )
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    if operation['status'] != 'in_progress':
        flash('Operation is not in progress.', 'warning')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    reason = request.form.get('reason', '').strip()
    if not reason:
        flash('You must provide a reason for force-ending this operation.', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    update_query = """
        UPDATE work_order_operations
        SET status = 'pending',
            notes = COALESCE(notes || E'\\n\\n', '') || 
                    '[' || TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI') || ' - FORCE-ENDED by ' || %s || '] ' || %s ||
                    E'\\n(Was started by ' || COALESCE((SELECT initials FROM users WHERE user_id = start_by), 'unknown') || 
                    ' on ' || TO_CHAR(start_date, 'YYYY-MM-DD HH24:MI') || ')'
        WHERE operation_id = %s
    """
    
    try:
        execute_query(update_query, (current_user.initials, reason, operation_id))
        flash(f'Operation force-ended successfully. It is now available for reassignment.', 'success')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
        
    except Exception as e:
        flash(f'Error force-ending operation: {str(e)}', 'danger')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_allowed_operation_types(user):
    """
    Return list of operation types this user can work on based on role.

    Tier 1 (owner, quality_manager, operations_manager): all types
    inspector:  quality and finishing only
    machinist:  machining only
    assembly:   assembly only
    admin:      outside_service only (sends/receives OS POs)
    """
    role = user.role

    if role in ('owner', 'quality_manager', 'operations_manager'):
        return ['machining', 'quality', 'finishing', 'assembly', 'outside_service']
    elif role == 'inspector':
        return ['quality', 'finishing']
    elif role == 'machinist':
        return ['machining']
    elif role == 'assembly':
        return ['assembly']
    elif role == 'admin':
        return ['outside_service']
    else:
        return []

def check_can_start_operation(operation, user):
    """Check if user can start this operation"""
    errors = []
    
    if operation['status'] != 'pending':
        errors.append(f'Operation is already {operation["status"]}.')
    
    if operation.get('wo_status') not in ('released_to_floor', 'in_production', 'final_inspection'):
        errors.append('Work order must be released to floor before starting operations.')
    
    if operation.get('open_ncr_count', 0) > 0:
        errors.append('Work order has open NCRs - cannot start new operations.')
    
    # Quality and finishing ops require inspector or Tier 1
    if operation['operation_type'] in ('quality', 'finishing'):
        if not user.can_perform_quality_inspection():
            errors.append('Only inspectors and quality managers can start quality and finishing operations.')
    
    return (len(errors) == 0, errors)

def check_can_complete_operation(operation, user):
    """Check if user can complete this operation"""
    errors = []
    
    if operation['status'] != 'in_progress':
        errors.append('Operation must be started before it can be completed.')
    
    # Quality and finishing ops require inspector or Tier 1
    if operation['operation_type'] in ('quality', 'finishing'):
        if not user.can_perform_quality_inspection():
            errors.append('Only inspectors and quality managers can complete quality and finishing operations.')
    
    # Outside service ops require Tier 1
    if operation['operation_type'] == 'outside_service':
        if not user.is_tier1():
            errors.append('Only managers can receive outside service operations.')
    
    return (len(errors) == 0, errors)

def check_can_reopen_operation(operation, user):
    """Check if user can reopen this operation"""
    errors = []
    
    if operation['status'] != 'complete':
        errors.append('Only completed operations can be reopened.')
    
    allowed_types = get_allowed_operation_types(user)
    if operation['operation_type'] not in allowed_types:
        errors.append('You do not have permission to reopen this operation type.')
    
    return (len(errors) == 0, errors)
