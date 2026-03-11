"""
Reports Module - Production and Quality Reports
ISO 9001: 9.1 (Monitoring, measurement, analysis and evaluation)
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from database import execute_query
from datetime import datetime, date, timedelta
import io
import csv

reports_bp = Blueprint('reports', __name__)

# ============================================================================
# REPORTS DASHBOARD
# ============================================================================

@reports_bp.route('/')
@login_required
def reports_dashboard():
    """Main reports dashboard with links to all reports"""
    
    # Permission check - office and above can view reports
    if not current_user.is_office():
        flash('You do not have permission to access reports.', 'danger')
        return redirect(url_for('dashboard'))
    
    return render_template('reports/dashboard.html')

# ============================================================================
# PRODUCTION SUMMARY REPORT
# ============================================================================

@reports_bp.route('/production-summary')
@login_required
def production_summary():
    """Work orders completed in date range"""
    
    if not current_user.is_office():
        flash('You do not have permission to access reports.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get date range from query params (default to last 30 days)
    end_date = request.args.get('end_date', date.today().isoformat())
    start_date = request.args.get('start_date', (date.today() - timedelta(days=30)).isoformat())
    
    query = """
        SELECT 
            wo.work_order_number,
            wo.quantity_ordered,
            wo.production_due_date,
            wo.released_at,
            wo.status,
            c.customer_code,
            c.company_name,
            p.customer_part_number,
            pr.revision_level,
            (SELECT MAX(end_date) FROM work_order_operations WHERE work_order_id = wo.work_order_id) as completion_date,
            (wo.production_due_date < (SELECT MAX(end_date) FROM work_order_operations WHERE work_order_id = wo.work_order_id)::date) as was_late
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        JOIN part_revisions pr ON wo.revision_id = pr.revision_id
        WHERE wo.status IN ('in_production', 'final_inspection', 'pending_ship_release', 'shipped')
          AND EXISTS (
              SELECT 1 FROM work_order_operations 
              WHERE work_order_id = wo.work_order_id 
                AND end_date BETWEEN %s AND %s
          )
        ORDER BY wo.work_order_number DESC
    """
    
    work_orders = execute_query(query, (start_date, end_date), fetch_all=True)
    
    # Calculate summary stats
    total_wos = len(work_orders)
    on_time = sum(1 for wo in work_orders if not wo.get('was_late'))
    late = total_wos - on_time
    on_time_pct = (on_time / total_wos * 100) if total_wos > 0 else 0
    
    summary = {
        'total_wos': total_wos,
        'on_time': on_time,
        'late': late,
        'on_time_pct': round(on_time_pct, 1)
    }
    
    return render_template(
        'reports/production_summary.html',
        work_orders=work_orders,
        summary=summary,
        start_date=start_date,
        end_date=end_date
    )

# ============================================================================
# ON-TIME DELIVERY REPORT
# ============================================================================

@reports_bp.route('/on-time-delivery')
@login_required
def on_time_delivery():
    """On-time delivery performance by customer and month"""
    
    if not current_user.is_office():
        flash('You do not have permission to access reports.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get date range
    end_date = request.args.get('end_date', date.today().isoformat())
    start_date = request.args.get('start_date', (date.today() - timedelta(days=90)).isoformat())
    
    # By customer
    customer_query = """
        SELECT 
            c.customer_code,
            c.company_name,
            COUNT(*) as total_wos,
            SUM(CASE WHEN wo.production_due_date >= (
                SELECT MAX(end_date)::date FROM work_order_operations WHERE work_order_id = wo.work_order_id
            ) THEN 1 ELSE 0 END) as on_time_wos,
            ROUND(
                SUM(CASE WHEN wo.production_due_date >= (
                    SELECT MAX(end_date)::date FROM work_order_operations WHERE work_order_id = wo.work_order_id
                ) THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1
            ) as on_time_pct
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        WHERE wo.status IN ('in_production', 'final_inspection', 'pending_ship_release', 'shipped')
          AND EXISTS (
              SELECT 1 FROM work_order_operations 
              WHERE work_order_id = wo.work_order_id 
                AND end_date BETWEEN %s AND %s
          )
        GROUP BY c.customer_id, c.customer_code, c.company_name
        ORDER BY total_wos DESC
    """
    
    by_customer = execute_query(customer_query, (start_date, end_date), fetch_all=True)
    
    # Overall stats
    total_query = """
        SELECT 
            COUNT(*) as total_wos,
            SUM(CASE WHEN wo.production_due_date >= (
                SELECT MAX(end_date)::date FROM work_order_operations WHERE work_order_id = wo.work_order_id
            ) THEN 1 ELSE 0 END) as on_time_wos
        FROM work_orders wo
        WHERE wo.status IN ('in_production', 'final_inspection', 'pending_ship_release', 'shipped')
          AND EXISTS (
              SELECT 1 FROM work_order_operations 
              WHERE work_order_id = wo.work_order_id 
                AND end_date BETWEEN %s AND %s
          )
    """
    
    totals = execute_query(total_query, (start_date, end_date), fetch_one=True)
    overall_pct = (totals['on_time_wos'] / totals['total_wos'] * 100) if totals['total_wos'] > 0 else 0
    
    return render_template(
        'reports/on_time_delivery.html',
        by_customer=by_customer,
        totals=totals,
        overall_pct=round(overall_pct, 1),
        start_date=start_date,
        end_date=end_date
    )

# ============================================================================
# NCR TRENDING REPORT
# ============================================================================

@reports_bp.route('/ncr-trending')
@login_required
def ncr_trending():
    """NCR trending by month and source"""
    
    if not current_user.role in ('quality_manager', 'operations_manager', 'owner'):
        flash('You do not have permission to access this report.', 'danger')
        return redirect(url_for('reports.reports_dashboard'))
    
    # Get date range
    end_date = request.args.get('end_date', date.today().isoformat())
    start_date = request.args.get('start_date', (date.today() - timedelta(days=180)).isoformat())
    
    # NCRs by source
    source_query = """
        SELECT 
            source,
            COUNT(*) as ncr_count,
            SUM(quantity_nonconforming) as total_qty_nc
        FROM ncrs
        WHERE initiated_at BETWEEN %s AND %s
        GROUP BY source
        ORDER BY ncr_count DESC
    """
    
    by_source = execute_query(source_query, (start_date, end_date), fetch_all=True)
    
    # NCRs by month
    month_query = """
        SELECT 
            TO_CHAR(initiated_at, 'YYYY-MM') as month,
            COUNT(*) as ncr_count,
            SUM(quantity_nonconforming) as total_qty_nc
        FROM ncrs
        WHERE initiated_at BETWEEN %s AND %s
        GROUP BY TO_CHAR(initiated_at, 'YYYY-MM')
        ORDER BY month DESC
    """
    
    by_month = execute_query(month_query, (start_date, end_date), fetch_all=True)
    
    # NCRs by disposition
    disposition_query = """
        SELECT 
            disposition,
            COUNT(*) as ncr_count
        FROM ncrs
        WHERE initiated_at BETWEEN %s AND %s
          AND disposition IS NOT NULL
        GROUP BY disposition
        ORDER BY ncr_count DESC
    """
    
    by_disposition = execute_query(disposition_query, (start_date, end_date), fetch_all=True)
    
    # Recent NCRs
    recent_query = """
        SELECT 
            ncr.ncr_number,
            ncr.initiated_at,
            ncr.quantity_nonconforming,
            ncr.source,
            ncr.disposition,
            ncr.status,
            wo.work_order_number
        FROM ncrs ncr
        LEFT JOIN work_orders wo ON ncr.work_order_id = wo.work_order_id
        WHERE ncr.initiated_at BETWEEN %s AND %s
        ORDER BY ncr.initiated_at DESC
        LIMIT 20
    """
    
    recent_ncrs = execute_query(recent_query, (start_date, end_date), fetch_all=True)
    
    return render_template(
        'reports/ncr_trending.html',
        by_source=by_source,
        by_month=by_month,
        by_disposition=by_disposition,
        recent_ncrs=recent_ncrs,
        start_date=start_date,
        end_date=end_date
    )

# ============================================================================
# WORK IN PROGRESS REPORT
# ============================================================================

@reports_bp.route('/work-in-progress')
@login_required
def work_in_progress():
    """Current WIP - all active work orders on floor"""
    
    if not current_user.is_office():
        flash('You do not have permission to access reports.', 'danger')
        return redirect(url_for('dashboard'))
    
    query = """
        SELECT 
            wo.work_order_number,
            wo.quantity_ordered,
            wo.production_due_date,
            wo.released_at,
            wo.status,
            c.customer_code,
            p.customer_part_number,
            (SELECT COUNT(*) FROM work_order_operations WHERE work_order_id = wo.work_order_id) as total_ops,
            (SELECT COUNT(*) FROM work_order_operations WHERE work_order_id = wo.work_order_id AND status = 'complete') as completed_ops,
            (SELECT COUNT(*) FROM work_order_operations WHERE work_order_id = wo.work_order_id AND status = 'in_progress') as in_progress_ops,
            (SELECT operation_code FROM work_order_operations WHERE work_order_id = wo.work_order_id AND status = 'in_progress' LIMIT 1) as current_op,
            (wo.production_due_date < CURRENT_DATE) as is_overdue
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        WHERE wo.status IN ('released_to_floor', 'in_production', 'final_inspection')
        ORDER BY wo.production_due_date ASC
    """
    
    wip = execute_query(query, fetch_all=True)
    
    # Summary stats
    total_wip = len(wip)
    overdue = sum(1 for wo in wip if wo.get('is_overdue'))
    
    return render_template(
        'reports/work_in_progress.html',
        wip=wip,
        total_wip=total_wip,
        overdue=overdue
    )

# ============================================================================
# EXPORT TO CSV
# ============================================================================

@reports_bp.route('/export/<report_type>')
@login_required
def export_csv(report_type):
    """Export report data to CSV"""
    
    if not current_user.is_office():
        flash('You do not have permission to export reports.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get date range
    end_date = request.args.get('end_date', date.today().isoformat())
    start_date = request.args.get('start_date', (date.today() - timedelta(days=30)).isoformat())
    
    if report_type == 'production':
        # Reuse production summary query
        query = """
            SELECT 
                wo.work_order_number,
                c.customer_code,
                p.customer_part_number,
                wo.quantity_ordered,
                wo.production_due_date,
                (SELECT MAX(end_date) FROM work_order_operations WHERE work_order_id = wo.work_order_id) as completion_date,
                CASE WHEN wo.production_due_date < (SELECT MAX(end_date) FROM work_order_operations WHERE work_order_id = wo.work_order_id)::date 
                     THEN 'Late' ELSE 'On Time' END as delivery_status
            FROM work_orders wo
            JOIN customers c ON wo.customer_id = c.customer_id
            JOIN parts p ON wo.part_id = p.part_id
            WHERE wo.status IN ('in_production', 'final_inspection', 'pending_ship_release', 'shipped')
              AND EXISTS (
                  SELECT 1 FROM work_order_operations 
                  WHERE work_order_id = wo.work_order_id 
                    AND end_date BETWEEN %s AND %s
              )
            ORDER BY wo.work_order_number DESC
        """
        
        data = execute_query(query, (start_date, end_date), fetch_all=True)
        filename = f'production_summary_{start_date}_to_{end_date}.csv'
        
    else:
        flash('Unknown report type.', 'danger')
        return redirect(url_for('reports.reports_dashboard'))
    
    # Generate CSV
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    
    # Send file
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )
