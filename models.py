"""
QERP - User Model
Flask-Login authentication and role-based permission checks.

Roles and Permission Tiers:
------------------------------------------------------------
Tier 1 (Full Access):   owner, quality_manager, operations_manager
Tier 2 (Quality):       inspector
Tier 3 (Floor):         machinist, assembly
Tier 4 (Admin):         admin

Operation Sign-off Rules:
  Machining ops (Op-M*)     → machinist + Tier 1
  Assembly ops (Op-A*)      → assembly + Tier 1
  Finishing ops (Op-F*)     → inspector + Tier 1 (post-outside-service verification)
  Quality ops (Op-Q*)       → inspector + Tier 1
  Outside service (OS)      → Tier 1 only
  Receiving inspection      → assembly + inspector + Tier 1
  Quality inspection        → inspector + Tier 1 only
------------------------------------------------------------
"""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from database import execute_query


class User(UserMixin):
    """
    User model for authentication and authorization.
    Implements Flask-Login's UserMixin interface.
    """

    def __init__(self, user_id, username, full_name, initials, role, active=True):
        self.id = str(user_id)  # Flask-Login requires .id attribute
        self.user_id = user_id
        self.username = username
        self.full_name = full_name
        self.initials = initials
        self.role = role
        self.active = active

    @property
    def is_active(self):
        """Required by Flask-Login."""
        return self.active

    # -------------------------------------------------------------------------
    # Database lookups
    # -------------------------------------------------------------------------

    @staticmethod
    def get_by_id(user_id):
        """Load user by UUID."""
        query = """
            SELECT user_id, username, full_name, initials, role, active
            FROM users
            WHERE user_id = %s
        """
        result = execute_query(query, (user_id,), fetch_one=True)

        if result:
            return User(
                user_id=result['user_id'],
                username=result['username'],
                full_name=result['full_name'],
                initials=result['initials'],
                role=result['role'],
                active=result['active']
            )
        return None

    @staticmethod
    def get_by_username(username):
        """Load user by username."""
        query = """
            SELECT user_id, username, password_hash, full_name, initials, role, active
            FROM users
            WHERE username = %s
        """
        result = execute_query(query, (username,), fetch_one=True)

        if result:
            user = User(
                user_id=result['user_id'],
                username=result['username'],
                full_name=result['full_name'],
                initials=result['initials'],
                role=result['role'],
                active=result['active']
            )
            user.password_hash = result['password_hash']
            return user
        return None

    def verify_password(self, password):
        """Verify password against stored hash."""
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def create_user(username, password, full_name, initials, role):
        """Create a new user."""
        password_hash = generate_password_hash(password)

        query = """
            INSERT INTO users (username, password_hash, full_name, initials, role, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING user_id
        """
        result = execute_query(
            query,
            (username, password_hash, full_name, initials, role, True),
            fetch_one=True
        )
        return result['user_id'] if result else None

    # -------------------------------------------------------------------------
    # Tier checks
    # -------------------------------------------------------------------------

    def is_tier1(self):
        """Owner, Quality Manager, Operations Manager -- full system access."""
        return self.role in ('owner', 'quality_manager', 'operations_manager')

    def is_tier1_or_inspector(self):
        """Tier 1 plus Inspector -- quality-gated actions."""
        return self.role in ('owner', 'quality_manager', 'operations_manager', 'inspector')

    # -------------------------------------------------------------------------
    # System-level permissions
    # -------------------------------------------------------------------------

    def can_create_work_orders(self):
        """Tier 1 and admin can create and edit work orders."""
        return self.role in ('owner', 'quality_manager', 'operations_manager', 'admin')

    def can_release_to_ship(self):
        """Tier 1 only can release shipments."""
        return self.is_tier1()

    def can_manage_ncr(self):
        """Tier 1 only can set NCR disposition and close NCRs."""
        return self.is_tier1()

    def can_manage_users(self):
        """Tier 1 only can create, edit, and deactivate users."""
        return self.is_tier1()

    def can_approve_suppliers(self):
        """Tier 1 only can approve or change supplier status."""
        return self.is_tier1()

    def can_access_reports(self):
        """Tier 1 and admin can access reporting."""
        return self.role in ('owner', 'quality_manager', 'operations_manager', 'admin')

    # -------------------------------------------------------------------------
    # Operation sign-off permissions
    # -------------------------------------------------------------------------

    def can_sign_machining_ops(self):
        """
        Machining operations (Op-M*): setup, saw, unload, mill/lathe, deburr.
        Machinist and Tier 1 only.
        """
        return self.role in ('owner', 'quality_manager', 'operations_manager', 'machinist')

    def can_sign_assembly_ops(self):
        """
        Assembly operations (Op-A*): hardware install, dowel pins, helicoil,
        bag & tag, box & ship.
        Assembly and Tier 1 only.
        """
        return self.role in ('owner', 'quality_manager', 'operations_manager', 'assembly')

    def can_sign_finishing_ops(self):
        """
        Finishing operations (Op-F*): anodize, electropolish, teflon, zinc,
        electroless nickel. These are outside service ops -- sign-off occurs
        when parts return and are verified by quality.
        Inspector and Tier 1 only.
        """
        return self.is_tier1_or_inspector()

    def can_sign_quality_ops(self):
        """
        Quality operations (Op-Q*): in-process inspection, finishing inspection,
        final inspection.
        Inspector and Tier 1 only.
        """
        return self.is_tier1_or_inspector()

    def can_sign_outside_service_ops(self):
        """
        Outside service operations (OS): receiving and closing out OS POs.
        Tier 1 only.
        """
        return self.is_tier1()

    # -------------------------------------------------------------------------
    # Inspection permissions
    # -------------------------------------------------------------------------

    def can_perform_quality_inspection(self):
        """
        FAI, AQL, in-process, and final inspections.
        Inspector and Tier 1 only.
        """
        return self.is_tier1_or_inspector()

    def can_perform_receiving_inspection(self):
        """
        Receiving/triage inspection: parts intake, refurb assessment,
        checking parts before assembly begins.
        Assembly, Inspector, and Tier 1.
        """
        return self.role in ('owner', 'quality_manager', 'operations_manager',
                             'inspector', 'assembly')

    # -------------------------------------------------------------------------
    # NCR permissions
    # -------------------------------------------------------------------------

    def can_initiate_ncr(self):
        """
        Any floor user can initiate an NCR when they find a problem.
        All roles except admin.
        """
        return self.role in ('owner', 'quality_manager', 'operations_manager',
                             'inspector', 'machinist', 'assembly')

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
