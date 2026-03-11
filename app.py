"""
ERP Lite - Main Flask Application
"""
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our modules
from database import init_db_pool, close_db_pool
from models import User

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Initialize database connection pool
init_db_pool()

@login_manager.user_loader
def load_user(user_id):
    """Load user for Flask-Login"""
    return User.get_by_id(user_id)

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.get_by_username(username)
        
        if user and user.verify_password(password):
            if not user.active:
                flash('Your account has been deactivated. Contact an administrator.', 'danger')
            else:
                login_user(user)
                flash(f'Welcome back, {user.full_name}!', 'success')
                
                # Redirect to next page or dashboard
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ============================================================================
# MAIN ROUTES
# ============================================================================

@app.route('/')
def index():
    """Redirect to dashboard or login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - work order overview"""
    from database import execute_query
    
    # Get work order counts by status
    wo_stats_query = """
        SELECT 
            status,
            COUNT(*) as count
        FROM work_orders
        GROUP BY status
        ORDER BY 
            CASE status
                WHEN 'released_to_floor' THEN 1
                WHEN 'in_production' THEN 2
                WHEN 'final_inspection' THEN 3
                WHEN 'pending_release' THEN 4
                WHEN 'draft' THEN 5
                WHEN 'pending_ship_release' THEN 6
                WHEN 'shipped' THEN 7
                ELSE 8
            END
    """
    wo_stats = execute_query(wo_stats_query, fetch_all=True)
    
    # Get open NCRs count
    ncr_count_query = "SELECT COUNT(*) as count FROM ncrs WHERE status != 'closed'"
    ncr_count = execute_query(ncr_count_query, fetch_one=True)['count']
    
    # Get overdue work orders
    overdue_query = """
        SELECT COUNT(*) as count
        FROM work_orders
        WHERE production_due_date < CURRENT_DATE
          AND status NOT IN ('shipped', 'closed', 'archived')
    """
    overdue_count = execute_query(overdue_query, fetch_one=True)['count']
    
    # Get recent work orders
    recent_wo_query = """
        SELECT wo.*, c.customer_code, p.customer_part_number
        FROM work_orders wo
        JOIN customers c ON wo.customer_id = c.customer_id
        JOIN parts p ON wo.part_id = p.part_id
        ORDER BY wo.created_at DESC
        LIMIT 10
    """
    recent_wos = execute_query(recent_wo_query, fetch_all=True)
    
    return render_template(
        'dashboard.html',
        wo_stats=wo_stats,
        ncr_count=ncr_count,
        overdue_count=overdue_count,
        recent_wos=recent_wos
    )

# ============================================================================
# IMPORT BLUEPRINTS (modules)
# ============================================================================

# Import and register blueprints
from routes.customers import customers_bp
from routes.parts import parts_bp
from routes.work_orders import work_orders_bp
from routes.shop_floor import shop_floor_bp
from routes.inspections import inspections_bp
from routes.suppliers import suppliers_bp
from routes.reports import reports_bp
from routes.users import users_bp

app.register_blueprint(customers_bp, url_prefix='/customers')
app.register_blueprint(parts_bp, url_prefix='/parts')
app.register_blueprint(work_orders_bp, url_prefix='/work-orders')
app.register_blueprint(shop_floor_bp, url_prefix='/shop-floor')
app.register_blueprint(inspections_bp, url_prefix='/inspections')
app.register_blueprint(suppliers_bp, url_prefix='/suppliers')
app.register_blueprint(reports_bp, url_prefix='/reports')
app.register_blueprint(users_bp, url_prefix='/users')

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """404 error handler"""
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """500 error handler"""
    return render_template('errors/500.html'), 500

# ============================================================================
# CLEANUP
# ============================================================================

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Clean up database connections on app shutdown"""
    pass  # Connection pool handles this

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    try:
        port = int(os.getenv('FLASK_PORT', 5000))
        debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
        company_name = os.getenv('COMPANY_NAME', 'ERPlite')
        
        print(f"""
╔════════════════════════════════════════════════════════╗
║        {company_name} Starting                
╚════════════════════════════════════════════════════════╝

Server running at: http://localhost:{port}
Debug mode: {debug}

Run setup.py if you haven't already.

Press CTRL+C to stop the server
        """)
        
        app.run(
            host='0.0.0.0',
            port=port,
            debug=debug
        )
    except KeyboardInterrupt:
        print("\n\nShutting down ERPlite...")
        close_db_pool()
    except Exception as e:
        print(f"Error starting application: {e}")
        close_db_pool()
