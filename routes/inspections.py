"""
Inspection Records and NCR Module
ISO 9001: 8.6 (Release of products/services), 8.7 (Nonconforming outputs), 10.2 (CAPA)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from database import execute_query
from datetime import datetime

inspections_bp = Blueprint('inspections', __name__)

# ============================================================================
# RECORD INSPECTION (from quality operation)
# ============================================================================

@inspections_bp.route('/record/<operation_id>', methods=['GET', 'POST'])
@login_required
def record_inspection(operation_id):
    """Record inspection results for a quality operation"""
    
    # Permission check - inspector and Tier 1 only
    if not current_user.can_perform_quality_inspection():
        flash('Only inspectors and quality managers can record inspections.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    # Get operation details
    op_query = """
        SELECT wop.*, wo.*, c.customer_code, c.company_name,
               p.customer_part_number, pr.revision_level
        FROM work_order_operations wop
        JOIN work_orders wo ON wop.work_order_id = wo.work_order_id
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        WHERE wop.operation_id = %s
    """
    operation = execute_query(op_query, (operation_id,), fetch_one=True)
    
    if not operation:
        flash('Operation not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    if operation['operation_type'] != 'quality':
        flash('This is not a quality operation.', 'warning')
        return redirect(url_for('shop_floor.view_operation', operation_id=operation_id))
    
    if request.method == 'POST':
        # Get form data
        inspection_type = request.form.get('inspection_type')
        quantity_inspected = request.form.get('quantity_inspected', '').strip()
        quantity_passed = request.form.get('quantity_passed', '').strip()
        result = request.form.get('result')
        equipment_used = request.form.get('equipment_used', '').strip()
        cmm_report_path = request.form.get('cmm_report_path', '').strip()
        notes = request.form.get('notes', '').strip()
        
        # Validation
        errors = []
        
        if not inspection_type:
            errors.append('Inspection type is required.')
        
        try:
            quantity_inspected = int(quantity_inspected)
            if quantity_inspected <= 0:
                raise ValueError()
        except:
            errors.append('Quantity inspected must be a positive number.')
        
        try:
            quantity_passed = int(quantity_passed)
            if quantity_passed < 0 or quantity_passed > quantity_inspected:
                raise ValueError()
        except:
            errors.append('Quantity passed must be between 0 and quantity inspected.')
        
        quantity_failed = quantity_inspected - quantity_passed
        
        if not result:
            errors.append('Inspection result is required.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('inspections.record_inspection', operation_id=operation_id))
        
        # Insert inspection record
        insert_query = """
            INSERT INTO inspection_records (
                work_order_id, operation_id, inspection_type,
                quantity_inspected, quantity_passed, quantity_failed,
                result, inspector_id, equipment_used, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING inspection_id
        """
        
        try:
            result_row = execute_query(
                insert_query,
                (operation['work_order_id'], operation_id, inspection_type,
                 quantity_inspected, quantity_passed, quantity_failed,
                 result, current_user.user_id, equipment_used, notes),
                fetch_one=True
            )
            
            inspection_id = result_row['inspection_id']
            
            # If CMM report provided, store as note (file attachment feature coming later)
            if cmm_report_path:
                update_query = """
                    UPDATE inspection_records
                    SET notes = COALESCE(notes || E'\\n\\n', '') || 'CMM Report: ' || %s
                    WHERE inspection_id = %s
                """
                execute_query(update_query, (cmm_report_path, inspection_id))
            
            flash(f'Inspection recorded successfully.', 'success')
            
            # If failed, redirect to NCR creation
            if result == 'fail':
                return redirect(url_for('inspections.create_ncr_from_inspection', inspection_id=inspection_id))
            else:
                # Mark operation as complete
                complete_op_query = """
                    UPDATE work_order_operations
                    SET status = 'complete',
                        end_date = CURRENT_TIMESTAMP,
                        end_by = %s,
                        quantity_finished = %s
                    WHERE operation_id = %s
                """
                execute_query(complete_op_query, (current_user.user_id, quantity_passed, operation_id))
                
                return redirect(url_for('shop_floor.my_operations'))
                
        except Exception as e:
            flash(f'Error recording inspection: {str(e)}', 'danger')
            return redirect(url_for('inspections.record_inspection', operation_id=operation_id))
    
    return render_template(
        'inspections/record_inspection.html',
        operation=operation
    )

# ============================================================================
# CREATE NCR FROM FAILED INSPECTION
# ============================================================================

@inspections_bp.route('/create-ncr/<inspection_id>', methods=['GET', 'POST'])
@login_required
def create_ncr_from_inspection(inspection_id):
    """Create NCR from a failed inspection"""
    
    # Inspector and Tier 1 only
    if not current_user.can_perform_quality_inspection():
        flash('You do not have permission to create NCRs.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get inspection details
    insp_query = """
        SELECT ir.*, wo.work_order_number, wo.quantity_ordered,
               c.customer_code, p.customer_part_number, pr.revision_level,
               wop.operation_code, wop.operation_description
        FROM inspection_records ir
        JOIN work_orders wo ON ir.work_order_id = wo.work_order_id
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        LEFT JOIN work_order_operations wop ON ir.operation_id = wop.operation_id
        WHERE ir.inspection_id = %s
    """
    inspection = execute_query(insp_query, (inspection_id,), fetch_one=True)
    
    if not inspection:
        flash('Inspection not found.', 'danger')
        return redirect(url_for('shop_floor.my_operations'))
    
    if request.method == 'POST':
        description = request.form.get('description', '').strip()
        quantity_nonconforming = request.form.get('quantity_nonconforming', '').strip()
        source = request.form.get('source', 'in_process')
        
        # Validation
        errors = []
        
        if not description:
            errors.append('Description of nonconformance is required.')
        
        try:
            quantity_nonconforming = int(quantity_nonconforming)
            if quantity_nonconforming <= 0:
                raise ValueError()
        except:
            errors.append('Quantity nonconforming must be a positive number.')
        
        if errors:
            for error in errors:
                flash(error, 'danger')
            return redirect(url_for('inspections.create_ncr_from_inspection', inspection_id=inspection_id))
        
        # Generate NCR number (NCR-YYYY-NNNN)
        year = datetime.now().year
        seq_query = """
            SELECT COALESCE(MAX(CAST(SUBSTRING(ncr_number FROM 10) AS INTEGER)), 0) + 1 as next_seq
            FROM ncrs
            WHERE ncr_number LIKE %s
        """
        seq_result = execute_query(seq_query, (f'NCR-{year}-%',), fetch_one=True)
        ncr_number = f"NCR-{year}-{seq_result['next_seq']:04d}"
        
        # Create NCR
        insert_query = """
            INSERT INTO ncrs (
                ncr_number, work_order_id, operation_id, inspection_id,
                initiated_by, description, quantity_nonconforming,
                part_number, source, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'open')
            RETURNING ncr_id
        """
        
        part_number = f"{inspection['customer_part_number']} Rev {inspection['revision_level']}"
        
        try:
            result = execute_query(
                insert_query,
                (ncr_number, inspection['work_order_id'], inspection['operation_id'],
                 inspection_id, current_user.user_id, description,
                 quantity_nonconforming, part_number, source),
                fetch_one=True
            )
            
            ncr_id = result['ncr_id']
            
            # Link NCR back to inspection
            update_insp_query = "UPDATE inspection_records SET ncr_id = %s WHERE inspection_id = %s"
            execute_query(update_insp_query, (ncr_id, inspection_id))
            
            # Put work order on hold
            hold_wo_query = """
                UPDATE work_order_operations
                SET status = 'on_hold'
                WHERE work_order_id = %s AND status IN ('pending', 'in_progress')
            """
            execute_query(hold_wo_query, (inspection['work_order_id'],))
            
            flash(f'NCR {ncr_number} created successfully. Work order placed on hold.', 'success')
            return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
            
        except Exception as e:
            flash(f'Error creating NCR: {str(e)}', 'danger')
            return redirect(url_for('inspections.create_ncr_from_inspection', inspection_id=inspection_id))
    
    return render_template(
        'inspections/create_ncr.html',
        inspection=inspection
    )

# ============================================================================
# VIEW NCR
# ============================================================================

@inspections_bp.route('/ncr/<ncr_id>')
@login_required
def view_ncr(ncr_id):
    """View NCR details"""
    
    query = """
        SELECT ncr.*, 
               wo.work_order_number,
               u_init.full_name as initiated_by_name,
               u_init.initials as initiated_by_initials,
               u_disp.full_name as disposition_by_name,
               u_disp.initials as disposition_by_initials,
               u_closed.full_name as closed_by_name
        FROM ncrs ncr
        LEFT JOIN work_orders wo ON ncr.work_order_id = wo.work_order_id
        LEFT JOIN users u_init ON ncr.initiated_by = u_init.user_id
        LEFT JOIN users u_disp ON ncr.disposition_by = u_disp.user_id
        LEFT JOIN users u_closed ON ncr.closed_by = u_closed.user_id
        WHERE ncr.ncr_id = %s
    """
    
    ncr = execute_query(query, (ncr_id,), fetch_one=True)
    
    if not ncr:
        flash('NCR not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    can_set_disposition = current_user.can_manage_ncr()
    
    return render_template(
        'inspections/view_ncr.html',
        ncr=ncr,
        can_set_disposition=can_set_disposition
    )

# ============================================================================
# SET NCR DISPOSITION (Quality Manager / Owner only)
# ============================================================================

@inspections_bp.route('/ncr/<ncr_id>/disposition', methods=['POST'])
@login_required
def set_ncr_disposition(ncr_id):
    """Set disposition for NCR (Quality Manager / Owner only)"""
    
    if not current_user.can_manage_ncr():
        flash('Only Quality Managers and Owners can set NCR disposition.', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
    
    disposition = request.form.get('disposition')
    disposition_notes = request.form.get('disposition_notes', '').strip()
    
    if not disposition:
        flash('Disposition is required.', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
    
    update_query = """
        UPDATE ncrs
        SET disposition = %s,
            disposition_notes = %s,
            disposition_by = %s,
            disposition_at = CURRENT_TIMESTAMP,
            status = 'disposition_pending'
        WHERE ncr_id = %s
    """
    
    try:
        execute_query(update_query, (disposition, disposition_notes, current_user.user_id, ncr_id))
        flash(f'Disposition set to: {disposition.replace("_", " ").title()}', 'success')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
        
    except Exception as e:
        flash(f'Error setting disposition: {str(e)}', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))

# ============================================================================
# CLOSE NCR
# ============================================================================

@inspections_bp.route('/ncr/<ncr_id>/close', methods=['POST'])
@login_required
def close_ncr(ncr_id):
    """Close NCR (Quality Manager / Owner only)"""
    
    if not current_user.can_manage_ncr():
        flash('Only Quality Managers and Owners can close NCRs.', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
    
    ncr = execute_query("SELECT * FROM ncrs WHERE ncr_id = %s", (ncr_id,), fetch_one=True)
    
    if not ncr:
        flash('NCR not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    if not ncr['disposition']:
        flash('Cannot close NCR without disposition.', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
    
    update_query = """
        UPDATE ncrs
        SET status = 'closed',
            closed_by = %s,
            closed_at = CURRENT_TIMESTAMP
        WHERE ncr_id = %s
    """
    
    try:
        execute_query(update_query, (current_user.user_id, ncr_id))
        
        # Release work order operations from hold
        if ncr['work_order_id']:
            release_query = """
                UPDATE work_order_operations
                SET status = 'pending'
                WHERE work_order_id = %s AND status = 'on_hold'
            """
            execute_query(release_query, (ncr['work_order_id'],))
        
        flash('NCR closed successfully. Work order released from hold.', 'success')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))
        
    except Exception as e:
        flash(f'Error closing NCR: {str(e)}', 'danger')
        return redirect(url_for('inspections.view_ncr', ncr_id=ncr_id))

# ============================================================================
# LIST ALL NCRs
# ============================================================================

@inspections_bp.route('/ncrs')
@login_required
def list_ncrs():
    """List all NCRs"""
    
    status_filter = request.args.get('status', 'open')
    
    if status_filter == 'all':
        where_clause = "TRUE"
    else:
        where_clause = f"ncr.status = '{status_filter}'"
    
    query = f"""
        SELECT ncr.*, 
               wo.work_order_number,
               u_init.full_name as initiated_by_name,
               u_init.initials as initiated_by_initials
        FROM ncrs ncr
        LEFT JOIN work_orders wo ON ncr.work_order_id = wo.work_order_id
        LEFT JOIN users u_init ON ncr.initiated_by = u_init.user_id
        WHERE {where_clause}
        ORDER BY ncr.initiated_at DESC
    """
    
    ncrs = execute_query(query, fetch_all=True)
    
    return render_template(
        'inspections/list_ncrs.html',
        ncrs=ncrs,
        status_filter=status_filter
    )
