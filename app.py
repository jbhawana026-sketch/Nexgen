import os
import csv
from io import StringIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from database import get_db, init_db, load_ndis_price_guide, load_shiftcare_shifts, load_xero_invoices
from reconciler import run_reconciliation

import platform

app = Flask(__name__)
app.secret_key = "splana_reconciliation_prototype_secret_key"

if platform.system() == "Linux" and os.environ.get("AWS_EXECUTION_ENV"):
    UPLOAD_FOLDER = '/tmp/uploads'
else:
    UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure database exists
init_db()

# --- Auth Helpers ---
def is_logged_in():
    return 'user_id' in session

def get_current_user():
    if not is_logged_in():
        return None
    return {
        "user_id": session.get("user_id"),
        "email": session.get("email"),
        "role": session.get("role")
    }

# Decorators for role access
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not is_logged_in():
                return redirect(url_for('login'))
            if session.get("role") not in roles:
                flash("You do not have permission to perform this action.", "error")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Routes ---

@app.route('/')
def index():
    if is_logged_in():
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if is_logged_in():
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['email'] = user['email']
            session['role'] = user['role']
            flash(f"Welcome back, {user['email']}!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "error")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Fetch KPI metrics
    # Revenue leakage (unmatched active shifts + underbilled duration mismatch)
    cursor.execute("""
        SELECT 
            COALESCE(SUM(r.discrepancy_amount), 0.0) as val,
            COUNT(r.result_id) as count
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
    """)
    leakage_row = cursor.fetchone()
    leakage = leakage_row['val']
    leakage_count = leakage_row['count']
    
    # Invoice Error cost (unmatched invoices + overbilled rate/duration discrepancies)
    cursor.execute("""
        SELECT 
            COALESCE(SUM(r.discrepancy_amount), 0.0) as val,
            COUNT(r.result_id) as count
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
    """)
    invoice_errors_row = cursor.fetchone()
    invoice_errors = invoice_errors_row['val']
    invoice_errors_count = invoice_errors_row['count']
    
    # Compliance Risk (Flags count)
    cursor.execute("SELECT COUNT(*) as count FROM compliance_flags")
    compliance_flags_count = cursor.fetchone()['count']
    
    # Coverage Calculation
    cursor.execute("SELECT COUNT(*) as count FROM shifts")
    total_shifts = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM shifts WHERE shift_id IN (SELECT DISTINCT shift_id FROM reconciliation_results WHERE match_status = 'matched')")
    matched_shifts = cursor.fetchone()['count']
    
    coverage = (matched_shifts / total_shifts * 100) if total_shifts > 0 else 0.0
    
    # Last Upload Date
    cursor.execute("""
        SELECT MAX(uploaded_at) as last_upload FROM (
            SELECT MAX(uploaded_at) as uploaded_at FROM shifts
            UNION
            SELECT MAX(uploaded_at) as uploaded_at FROM invoices
            UNION
            SELECT MAX(uploaded_at) as uploaded_at FROM price_rules
        )
    """)
    last_upload_row = cursor.fetchone()
    last_upload = last_upload_row['last_upload'] if last_upload_row and last_upload_row['last_upload'] else "Never"
    
    # 2. Get breakdown lists for visual dashboard
    # Discrepancy breakdown by participant (summing only revenue leakage)
    cursor.execute("""
        SELECT 
            COALESCE(s.participant_id, i.participant_reference) as participant_id,
            COUNT(r.result_id) as flag_count,
            SUM(r.discrepancy_amount) as total_discrepancy
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
        GROUP BY participant_id
        ORDER BY total_discrepancy DESC
        LIMIT 5
    """)
    participant_breakdown = cursor.fetchall()
    
    # Discrepancy breakdown by staff member (summing only revenue leakage)
    cursor.execute("""
        SELECT 
            s.staff_id,
            COUNT(r.result_id) as flag_count,
            SUM(r.discrepancy_amount) as total_discrepancy
        FROM reconciliation_results r
        JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
        GROUP BY s.staff_id
        ORDER BY total_discrepancy DESC
        LIMIT 5
    """)
    staff_breakdown = cursor.fetchall()
    
    # 3. Overall match status counts for chart representation (shifts only)
    cursor.execute("""
        SELECT match_status, COUNT(*) as count 
        FROM reconciliation_results 
        WHERE shift_id IS NOT NULL 
        GROUP BY match_status
    """)
    status_counts = {row['match_status']: row['count'] for row in cursor.fetchall()}
    
    conn.close()
    
    return render_template('dashboard.html', 
                           user=get_current_user(),
                           leakage=leakage,
                           leakage_count=leakage_count,
                           invoice_errors=invoice_errors,
                           invoice_errors_count=invoice_errors_count,
                           compliance_flags_count=compliance_flags_count,
                           coverage=round(coverage, 1),
                           last_upload=last_upload,
                           participant_breakdown=participant_breakdown,
                           staff_breakdown=staff_breakdown,
                           status_counts=status_counts,
                           total_shifts=total_shifts)

@app.route('/unmatched-shifts')
@login_required
def unmatched_shifts():
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch unmatched shifts representing revenue leakage
    cursor.execute("""
        SELECT 
            r.result_id,
            r.match_status,
            r.discrepancy_type,
            r.discrepancy_amount,
            r.flag_severity,
            r.notes,
            s.shift_id,
            s.participant_id,
            s.support_item_code,
            s.service_date,
            s.start_time,
            s.end_time,
            s.duration_hours,
            s.staff_id,
            s.location,
            s.claim_status
        FROM reconciliation_results r
        JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
        ORDER BY r.discrepancy_amount DESC
    """)
    results = cursor.fetchall()
    
    # Calculate total revenue leakage for page header summary card
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
    """)
    total_leakage = cursor.fetchone()['val']
    
    conn.close()
    return render_template('unmatched_shifts.html', user=get_current_user(), results=results, total_leakage=total_leakage)

@app.route('/invoice-errors')
@login_required
def invoice_errors():
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch invoice errors representing invoice error costs
    cursor.execute("""
        SELECT 
            r.result_id,
            r.match_status,
            r.discrepancy_type,
            r.discrepancy_amount,
            r.flag_severity,
            r.notes,
            i.invoice_number,
            i.line_date,
            i.participant_reference,
            i.support_item_code,
            i.description,
            i.quantity,
            i.unit_amount,
            i.line_total,
            i.payment_status,
            s.shift_id
        FROM reconciliation_results r
        JOIN invoices i ON r.invoice_id = i.invoice_id
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
        ORDER BY r.discrepancy_amount DESC
    """)
    results = cursor.fetchall()
    
    # Calculate total invoice error cost for page header summary card
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
    """)
    total_error_cost = cursor.fetchone()['val']
    
    conn.close()
    return render_template('invoice_errors.html', user=get_current_user(), results=results, total_error_cost=total_error_cost)

@app.route('/compliance-flags')
@login_required
def compliance_flags():
    conn = get_db()
    cursor = conn.cursor()
    
    # Fetch compliance flags
    cursor.execute("""
        SELECT 
            f.flag_id,
            f.invoice_number,
            f.rule_violated,
            f.severity,
            f.recommended_action,
            f.details,
            f.reviewed,
            f.resolved,
            i.participant_reference,
            i.support_item_code,
            i.line_date,
            i.quantity,
            i.unit_amount
        FROM compliance_flags f
        JOIN invoices i ON f.invoice_id = i.invoice_id
        ORDER BY f.severity DESC, f.flag_id DESC
    """)
    results = cursor.fetchall()
    conn.close()
    
    return render_template('compliance_flags.html', user=get_current_user(), results=results)

@app.route('/price-rules')
@login_required
def price_rules():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM price_rules ORDER BY support_item_code ASC")
    rules = cursor.fetchall()
    conn.close()
    
    return render_template('price_rules.html', user=get_current_user(), rules=rules)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'finance')
def upload():
    if request.method == 'POST':
        file_type = request.form.get('file_type')
        if 'file' not in request.files:
            flash("No file part in the request.", "error")
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash("No file selected.", "error")
            return redirect(request.url)
            
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            try:
                if file_type == 'price_guide':
                    count = load_ndis_price_guide(file_path)
                    flash(f"NDIS Price Guide imported successfully. Loaded {count} price rules.", "success")
                elif file_type == 'shiftcare':
                    count = load_shiftcare_shifts(file_path)
                    flash(f"ShiftCare shifts imported successfully. Loaded {count} shifts.", "success")
                elif file_type == 'xero':
                    count = load_xero_invoices(file_path)
                    flash(f"Xero Invoices imported successfully. Loaded {count} invoice line items.", "success")
                else:
                    flash("Unknown file type selected.", "error")
                    return redirect(request.url)
                
                # Check if we can run reconciliation (need at least some shifts and invoices)
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as count FROM shifts")
                shifts_count = cursor.fetchone()['count']
                cursor.execute("SELECT COUNT(*) as count FROM invoices")
                invoices_count = cursor.fetchone()['count']
                conn.close()
                
                if shifts_count > 0 and invoices_count > 0:
                    run_reconciliation()
                    flash("Automated reconciliation & compliance checks executed successfully.", "success")
                    
            except Exception as e:
                flash(f"Error importing file: {e}", "error")
                
            finally:
                # Cleanup file
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            return redirect(url_for('dashboard'))
            
    return render_template('upload.html', user=get_current_user())

@app.route('/toggle-compliance/<int:flag_id>', methods=['POST'])
@login_required
@role_required('admin', 'finance')
def toggle_compliance(flag_id):
    action = request.form.get('action') # 'reviewed' or 'resolved'
    value = int(request.form.get('value', 0))
    
    conn = get_db()
    cursor = conn.cursor()
    if action == 'reviewed':
        cursor.execute("UPDATE compliance_flags SET reviewed = ? WHERE flag_id = ?", (value, flag_id))
    elif action == 'resolved':
        cursor.execute("UPDATE compliance_flags SET resolved = ? WHERE flag_id = ?", (value, flag_id))
        
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.route('/download-sample/<filename>')
@login_required
def download_sample(filename):
    # Ensure it's safe to serve
    if filename in [
        'ndis_price_guide_2025_26.csv', 'ndis_price_guide_2025_26.xml',
        'xero_invoices_sample.csv', 'xero_invoices_sample.xml',
        'shiftcare_shifts_sample.csv', 'shiftcare_shifts_sample.xml'
    ]:
        return send_from_directory('sample_data', filename, as_attachment=True)
    else:
        return "File not found", 404

@app.route('/export/reconciliation')
@login_required
def export_reconciliation():
    conn = get_db()
    cursor = conn.cursor()
    
    # Export a list of flagged items (unmatched shifts, invoice errors, and rate mismatches)
    # in a nice formatted CSV.
    cursor.execute("""
        SELECT 
            'Shift Care' as source,
            s.shift_id as record_id,
            s.participant_id as participant,
            s.support_item_code,
            s.service_date as date,
            s.duration_hours as qty_or_duration,
            '' as invoice_number,
            r.discrepancy_type,
            r.discrepancy_amount,
            r.flag_severity,
            r.notes
        FROM reconciliation_results r
        JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
        
        UNION ALL
        
        SELECT 
            'Xero Invoice' as source,
            CAST(i.invoice_id AS TEXT) as record_id,
            i.participant_reference as participant,
            i.support_item_code,
            i.line_date as date,
            i.quantity as qty_or_duration,
            i.invoice_number,
            r.discrepancy_type,
            r.discrepancy_amount,
            r.flag_severity,
            r.notes
        FROM reconciliation_results r
        JOIN invoices i ON r.invoice_id = i.invoice_id
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
        
        ORDER BY discrepancy_amount DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["Source", "Record ID / Invoice ID", "Participant ID / Ref", "Support Item Code", "Date", "Qty / Duration", "Invoice Number", "Discrepancy Type", "Discrepancy Amount ($)", "Severity", "Notes"])
    
    for r in rows:
        cw.writerow([
            r['source'],
            r['record_id'],
            r['participant'],
            r['support_item_code'],
            r['date'],
            r['qty_or_duration'],
            r['invoice_number'],
            r['discrepancy_type'],
            f"{r['discrepancy_amount']:.2f}",
            r['flag_severity'],
            r['notes']
        ])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=NDIS_Billing_Reconciliation_Report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    # Running prototype locally
    app.run(debug=True, port=5000)
