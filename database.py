import sqlite3
import os
import pandas as pd
from datetime import datetime
from werkzeug.security import generate_password_hash

DB_NAME = "ndis_recon.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Users table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, -- 'admin', 'finance', 'readonly'
        provider_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Price rules table (NDIS Price Guide)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS price_rules (
        rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
        support_item_code TEXT UNIQUE NOT NULL,
        service_description TEXT,
        registration_group TEXT,
        unit TEXT,
        price_limit_national REAL,
        effective_from TEXT,
        effective_to TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 3. Shifts table (ShiftCare shifts)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS shifts (
        shift_id TEXT PRIMARY KEY,
        participant_id TEXT NOT NULL,
        support_item_code TEXT NOT NULL,
        service_date TEXT NOT NULL,
        start_time TEXT,
        end_time TEXT,
        duration_hours REAL,
        staff_id TEXT,
        location TEXT,
        claim_status TEXT, -- 'claimed', 'unclaimed', 'cancelled', etc.
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 4. Invoices table (Xero invoices)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        invoice_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT NOT NULL,
        line_date TEXT NOT NULL,
        participant_reference TEXT NOT NULL,
        support_item_code TEXT NOT NULL,
        description TEXT,
        quantity REAL,
        unit_amount REAL,
        line_total REAL,
        payment_status TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 5. Reconciliation results table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reconciliation_results (
        result_id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        shift_id TEXT,
        invoice_id INTEGER,
        invoice_number TEXT,
        match_status TEXT, -- 'matched', 'unmatched', 'partial'
        discrepancy_type TEXT, -- 'none', 'unbilled_shift', 'missing_shift', 'duration_mismatch', 'rate_mismatch', 'multiple_shifts'
        discrepancy_amount REAL DEFAULT 0.0,
        flag_severity TEXT, -- 'none', 'low', 'medium', 'high'
        notes TEXT,
        FOREIGN KEY(shift_id) REFERENCES shifts(shift_id),
        FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id)
    )
    """)
    
    # 6. Compliance flags table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compliance_flags (
        flag_id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER,
        invoice_number TEXT,
        rule_violated TEXT, -- 'rate_limit', 'duration_reasonableness', 'time_of_day', 'cancellation'
        severity TEXT, -- 'low', 'medium', 'high'
        recommended_action TEXT,
        details TEXT,
        reviewed INTEGER DEFAULT 0, -- 0 or 1
        resolved INTEGER DEFAULT 0, -- 0 or 1
        FOREIGN KEY(invoice_id) REFERENCES invoices(invoice_id)
    )
    """)
    
    # Seed default users if they don't exist
    users_to_seed = [
        ("admin@splana.com.au", "admin123", "admin"),
        ("finance@splana.com.au", "finance123", "finance"),
        ("read@splana.com.au", "read123", "readonly")
    ]
    
    for email, password, role in users_to_seed:
        cursor.execute("SELECT 1 FROM users WHERE email = ?", (email,))
        if not cursor.fetchone():
            hashed = generate_password_hash(password)
            cursor.execute("INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)", (email, hashed, role))
            
    conn.commit()
    conn.close()
    print("Database initialized and seeded.")

def parse_date(date_str):
    if not date_str or pd.isna(date_str):
        return None
    date_str = str(date_str).strip()
    # Try different formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Try dateutil parser if formats fail
    try:
        import dateutil.parser
        return dateutil.parser.parse(date_str).strftime("%Y-%m-%d")
    except:
        return date_str

def clean_amount(val):
    if val is None or pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace('$', '').replace(',', '')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def load_file_as_df(file_path):
    """
    Load a data file as a Pandas DataFrame. Supports XML and CSV.
    """
    file_lower = file_path.lower()
    if file_lower.endswith('.xml'):
        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            rows = []
            
            # Helper to check if an element is a leaf (only has text, no sub-elements)
            def is_leaf(elem):
                return len(elem) == 0
                
            # Approach 1: Directly inspect root children
            for child in root:
                row_data = {}
                for field in child:
                    if is_leaf(field):
                        row_data[field.tag.lower()] = field.text.strip() if field.text else ""
                if row_data:
                    rows.append(row_data)
                    
            # Approach 2: If root was a flat list and we didn't find structure, look deeper
            if not rows:
                for elem in root.iter():
                    if len(elem) > 0 and elem != root:
                        row_data = {}
                        has_grandchildren = False
                        for field in elem:
                            if len(field) > 0:
                                has_grandchildren = True
                                break
                            row_data[field.tag.lower()] = field.text.strip() if field.text else ""
                        if row_data and not has_grandchildren:
                            rows.append(row_data)
            
            if not rows:
                raise ValueError("Could not find list of rows in the XML structure.")
                
            return pd.DataFrame(rows)
        except Exception as e:
            raise ValueError(f"XML Parsing Error: {e}")
    else:
        # Standard CSV load
        encodings = ['utf-8', 'utf-8-sig', 'cp1252']
        df = None
        for enc in encodings:
            try:
                df = pd.read_csv(file_path, encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            raise ValueError("Could not read CSV file.")
        return df

def load_ndis_price_guide(file_path):
    df = load_file_as_df(file_path)
    
    # Standardize column names (strip spaces, lowercase)
    df.columns = [c.strip().lower() for c in df.columns]
    
    # Required columns check
    required_cols = ["support_item_code", "service_description", "registration_group", "unit", "price_limit_national", "effective_from", "effective_to"]
    for col in required_cols:
        if col not in df.columns:
            matches = [c for c in df.columns if col in c]
            if matches:
                df.rename(columns={matches[0]: col}, inplace=True)
            else:
                raise ValueError(f"Missing required column in Price Guide: {col}. Available: {list(df.columns)}")
                
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear and reload
    cursor.execute("DELETE FROM price_rules")
    
    success_count = 0
    for idx, row in df.iterrows():
        try:
            code = str(row["support_item_code"]).strip()
            desc = str(row["service_description"]).strip() if not pd.isna(row["service_description"]) else ""
            reg_group = str(row["registration_group"]).strip() if not pd.isna(row["registration_group"]) else ""
            unit = str(row["unit"]).strip() if not pd.isna(row["unit"]) else ""
            limit = clean_amount(row["price_limit_national"])
            eff_from = parse_date(row["effective_from"])
            eff_to = parse_date(row["effective_to"])
            
            cursor.execute("""
            INSERT OR REPLACE INTO price_rules 
            (support_item_code, service_description, registration_group, unit, price_limit_national, effective_from, effective_to)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, desc, reg_group, unit, limit, eff_from, eff_to))
            success_count += 1
        except Exception as e:
            print(f"Error loading price rule at row {idx}: {e}")
            
    conn.commit()
    conn.close()
    return success_count

def load_shiftcare_shifts(file_path):
    df = load_file_as_df(file_path)
    
    df.columns = [c.strip().lower() for c in df.columns]
    
    required_cols = ["shift_id", "participant_id", "support_item_code", "service_date", "start_time", "end_time", "duration_hours", "staff_id", "location", "claim_status"]
    for col in required_cols:
        if col not in df.columns:
            matches = [c for c in df.columns if col in c]
            if matches:
                df.rename(columns={matches[0]: col}, inplace=True)
            else:
                raise ValueError(f"Missing required column in Shiftcare file: {col}. Available: {list(df.columns)}")
                
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear old shifts and recon results that depend on shifts
    cursor.execute("DELETE FROM reconciliation_results")
    cursor.execute("DELETE FROM shifts")
    
    success_count = 0
    for idx, row in df.iterrows():
        try:
            shift_id = str(row["shift_id"]).strip()
            participant_id = str(row["participant_id"]).strip()
            code = str(row["support_item_code"]).strip()
            date = parse_date(row["service_date"])
            start_t = str(row["start_time"]).strip() if not pd.isna(row["start_time"]) else ""
            end_t = str(row["end_time"]).strip() if not pd.isna(row["end_time"]) else ""
            duration = float(row["duration_hours"]) if not pd.isna(row["duration_hours"]) else 0.0
            staff = str(row["staff_id"]).strip() if not pd.isna(row["staff_id"]) else ""
            loc = str(row["location"]).strip() if not pd.isna(row["location"]) else ""
            status = str(row["claim_status"]).strip() if not pd.isna(row["claim_status"]) else ""
            
            cursor.execute("""
            INSERT OR REPLACE INTO shifts 
            (shift_id, participant_id, support_item_code, service_date, start_time, end_time, duration_hours, staff_id, location, claim_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (shift_id, participant_id, code, date, start_t, end_t, duration, staff, loc, status))
            success_count += 1
        except Exception as e:
            print(f"Error loading shift at row {idx}: {e}")
            
    conn.commit()
    conn.close()
    return success_count

def load_xero_invoices(file_path):
    df = load_file_as_df(file_path)
    
    df.columns = [c.strip().lower() for c in df.columns]
    
    required_cols = ["invoice_number", "line_date", "participant_reference", "support_item_code", "description", "quantity", "unit_amount", "line_total", "payment_status"]
    for col in required_cols:
        if col not in df.columns:
            matches = [c for c in df.columns if col in c]
            if matches:
                df.rename(columns={matches[0]: col}, inplace=True)
            else:
                raise ValueError(f"Missing required column in Xero file: {col}. Available: {list(df.columns)}")
                
    conn = get_db()
    cursor = conn.cursor()
    
    # Clear old invoices, invoice compliance flags, and recon results
    cursor.execute("DELETE FROM reconciliation_results")
    cursor.execute("DELETE FROM compliance_flags")
    cursor.execute("DELETE FROM invoices")
    
    success_count = 0
    for idx, row in df.iterrows():
        try:
            inv_num = str(row["invoice_number"]).strip()
            date = parse_date(row["line_date"])
            ref = str(row["participant_reference"]).strip()
            code = str(row["support_item_code"]).strip()
            desc = str(row["description"]).strip() if not pd.isna(row["description"]) else ""
            qty = float(row["quantity"]) if not pd.isna(row["quantity"]) else 0.0
            unit_amt = clean_amount(row["unit_amount"])
            total_amt = clean_amount(row["line_total"])
            status = str(row["payment_status"]).strip() if not pd.isna(row["payment_status"]) else ""
            
            cursor.execute("""
            INSERT INTO invoices 
            (invoice_number, line_date, participant_reference, support_item_code, description, quantity, unit_amount, line_total, payment_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (inv_num, date, ref, code, desc, qty, unit_amt, total_amt, status))
            success_count += 1
        except Exception as e:
            print(f"Error loading invoice line at row {idx}: {e}")
            
    conn.commit()
    conn.close()
    return success_count

if __name__ == "__main__":
    init_db()
