import sqlite3
from datetime import datetime, timedelta
from database import get_db

def run_reconciliation():
    conn = get_db()
    cursor = conn.cursor()
    
    # 1. Clear old results
    cursor.execute("DELETE FROM reconciliation_results")
    cursor.execute("DELETE FROM compliance_flags")
    conn.commit()
    
    # 2. Fetch all shifts
    cursor.execute("SELECT * FROM shifts")
    shifts = [dict(row) for row in cursor.fetchall()]
    
    # 3. Fetch all invoices
    cursor.execute("SELECT * FROM invoices")
    invoices = [dict(row) for row in cursor.fetchall()]
    
    # 4. Fetch NDIS price limits
    cursor.execute("SELECT * FROM price_rules")
    price_rules = {row["support_item_code"]: dict(row) for row in cursor.fetchall()}
    
    # Keep track of matched invoice line IDs to prevent double-matching
    matched_invoice_ids = set()
    matched_shift_ids = set()
    
    # Helper to check if dates are within ±1 day
    def dates_within_range(d1_str, d2_str, days_limit=1):
        try:
            d1 = datetime.strptime(d1_str, "%Y-%m-%d")
            d2 = datetime.strptime(d2_str, "%Y-%m-%d")
            return abs((d1 - d2).days) <= days_limit
        except Exception:
            return False
            
    # Helper to check if dates are in same month and year
    def dates_in_same_month(d1_str, d2_str):
        try:
            d1 = datetime.strptime(d1_str, "%Y-%m-%d")
            d2 = datetime.strptime(d2_str, "%Y-%m-%d")
            return d1.year == d2.year and d1.month == d2.month
        except Exception:
            return False

    # Perform Multi-Tier Matching
    
    # --- TIER 1: Primary Match ---
    # Exact participant, date, and support item code
    for shift in shifts:
        for inv in invoices:
            if inv["invoice_id"] in matched_invoice_ids:
                continue
            
            if (shift["participant_id"] == inv["participant_reference"] and
                shift["support_item_code"] == inv["support_item_code"] and
                shift["service_date"] == inv["line_date"]):
                
                # We have a match!
                matched_invoice_ids.add(inv["invoice_id"])
                matched_shift_ids.add(shift["shift_id"])
                
                process_match(cursor, shift, inv, "matched", "primary", price_rules)
                break
                
    # --- TIER 2: Secondary Match ---
    # Same participant, same code, but date is ±1 day
    for shift in shifts:
        if shift["shift_id"] in matched_shift_ids:
            continue
            
        for inv in invoices:
            if inv["invoice_id"] in matched_invoice_ids:
                continue
            
            if (shift["participant_id"] == inv["participant_reference"] and
                shift["support_item_code"] == inv["support_item_code"] and
                dates_within_range(shift["service_date"], inv["line_date"], 1)):
                
                matched_invoice_ids.add(inv["invoice_id"])
                matched_shift_ids.add(shift["shift_id"])
                
                process_match(cursor, shift, inv, "matched", "secondary (±1 day)", price_rules)
                break
                
    # --- TIER 3: Tertiary Match ---
    # Same participant, same code, but date is in the same month (loose match)
    for shift in shifts:
        if shift["shift_id"] in matched_shift_ids:
            continue
            
        for inv in invoices:
            if inv["invoice_id"] in matched_invoice_ids:
                continue
            
            if (shift["participant_id"] == inv["participant_reference"] and
                shift["support_item_code"] == inv["support_item_code"] and
                dates_in_same_month(shift["service_date"], inv["line_date"])):
                
                matched_invoice_ids.add(inv["invoice_id"])
                matched_shift_ids.add(shift["shift_id"])
                
                process_match(cursor, shift, inv, "partial", "tertiary (loose month match)", price_rules)
                break

    # --- UNMATCHED SHIFTS (Revenue Leakage) ---
    for shift in shifts:
        if shift["shift_id"] in matched_shift_ids:
            continue
            
        # Get rate limit if available
        rule = price_rules.get(shift["support_item_code"])
        rate = rule["price_limit_national"] if rule else 67.56 # default backup rate
        leakage_amt = shift["duration_hours"] * rate
        
        # If the shift was cancelled, leakage might be 0, but if it is active, it is leakage
        if shift["claim_status"] == "cancelled":
            leakage_amt = 0.0
            notes = "Cancelled shift. Not billed, which is correct."
            status = "matched"
            discrepancy = "none"
            severity = "none"
        else:
            notes = "Shift Care shift has no matching Xero invoice. Potential revenue leakage."
            status = "unmatched"
            discrepancy = "unbilled_shift"
            severity = "high"
            
        cursor.execute("""
        INSERT INTO reconciliation_results 
        (shift_id, match_status, discrepancy_type, discrepancy_amount, flag_severity, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (shift["shift_id"], status, discrepancy, leakage_amt, severity, notes))

    # --- UNMATCHED INVOICES (Potential Invoice Errors) ---
    for inv in invoices:
        if inv["invoice_id"] in matched_invoice_ids:
            continue
            
        cursor.execute("""
        INSERT INTO reconciliation_results 
        (invoice_id, invoice_number, match_status, discrepancy_type, discrepancy_amount, flag_severity, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (inv["invoice_id"], inv["invoice_number"], "unmatched", "missing_shift", inv["line_total"], "high", 
              "Xero invoice line has no corresponding Shift Care shift recorded.")
        )
        
    # --- COMPLIANCE ENGINE RUN ---
    for inv in invoices:
        run_compliance_checks(cursor, inv, price_rules, shifts, matched_invoice_ids, matched_shift_ids)

    conn.commit()
    conn.close()
    print("Reconciliation and Compliance check complete.")

def process_match(cursor, shift, inv, base_status, tier_name, price_rules):
    """
    Compare shift duration and invoice details, logging discrepancies.
    """
    discrepancy_type = "none"
    discrepancy_amount = 0.0
    severity = "none"
    notes = f"Matched via {tier_name} rules."
    
    # Get NDIS price limit if available, otherwise use the invoiced unit amount
    rule = price_rules.get(inv["support_item_code"])
    limit = rule["price_limit_national"] if rule else inv["unit_amount"]
    
    # 1. Check Duration Mismatch
    duration_diff = shift["duration_hours"] - inv["quantity"]
    has_duration_mismatch = abs(duration_diff) > 0.05
    duration_mismatch_amount = 0.0
    if has_duration_mismatch:
        base_status = "partial"
        severity = "medium"
        # Store the FULL shift value (duration * rate) as the discrepancy amount
        duration_mismatch_amount = shift["duration_hours"] * limit
        if duration_diff > 0:
            diff_amount = duration_diff * limit
            notes += f" Underbilled by {duration_diff:.2f} hours (${diff_amount:.2f} difference). Full shift value: ${duration_mismatch_amount:.2f}."
        else:
            diff_amount = abs(duration_diff) * limit
            notes += f" Overbilled client by {abs(duration_diff):.2f} hours (${diff_amount:.2f} difference). Full shift value: ${duration_mismatch_amount:.2f}."
            
    # 2. Check Rate Mismatch (invoiced unit rate vs price guide)
    has_rate_mismatch = False
    rate_mismatch_amount = 0.0
    if rule:
        if inv["unit_amount"] > limit + 0.01:
            has_rate_mismatch = True
            base_status = "partial"
            rate_diff = inv["unit_amount"] - limit
            rate_mismatch_amount = rate_diff * inv["quantity"]
            severity = "high"
            notes += f" Invoiced rate ${inv['unit_amount']:.2f} exceeds NDIS guide max ${limit:.2f} (overbill of ${rate_mismatch_amount:.2f})."

    # Determine discrepancy type and amount
    if has_rate_mismatch:
        discrepancy_type = "rate_mismatch"
        discrepancy_amount = rate_mismatch_amount
    elif has_duration_mismatch:
        discrepancy_type = "duration_mismatch"
        discrepancy_amount = duration_mismatch_amount
        
    cursor.execute("""
    INSERT INTO reconciliation_results 
    (shift_id, invoice_id, invoice_number, match_status, discrepancy_type, discrepancy_amount, flag_severity, notes)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (shift["shift_id"], inv["invoice_id"], inv["invoice_number"], base_status, discrepancy_type, discrepancy_amount, severity, notes))

def run_compliance_checks(cursor, inv, price_rules, shifts, matched_invoice_ids, matched_shift_ids):
    """
    Apply NDIS-specific compliance checks on each invoice line.
    """
    rule = price_rules.get(inv["support_item_code"])
    
    # 1. Rate Limit Compliance Check
    if rule:
        limit = rule["price_limit_national"]
        if inv["unit_amount"] > limit + 0.01:
            cursor.execute("""
            INSERT INTO compliance_flags 
            (invoice_id, invoice_number, rule_violated, severity, recommended_action, details)
            VALUES (?, ?, 'rate_limit', 'high', 
                    'Issue credit note and rebill at NDIS limit. Ensure billing rates in Xero are updated.', 
                    ?)
            """, (inv["invoice_id"], inv["invoice_number"], 
                  f"Billed unit rate ${inv['unit_amount']:.2f} exceeds NDIS Price Guide limit of ${limit:.2f} for code {inv['support_item_code']}."))

    # 2. Duration Reasonableness Check (>24 hours or <=0 hours)
    if inv["quantity"] >= 24.0 or inv["quantity"] <= 0.0:
        cursor.execute("""
        INSERT INTO compliance_flags 
        (invoice_id, invoice_number, rule_violated, severity, recommended_action, details)
        VALUES (?, ?, 'duration_reasonableness', 'medium', 
                'Verify timesheet logs. Invoiced quantity is out of standard range (0-24 hours).', 
                ?)
        """, (inv["invoice_id"], inv["invoice_number"], 
              f"Invoiced hours quantity is {inv['quantity']:.2f} hours, which is audit-risky."))

    # Find matching shift if any
    matched_shift = None
    for s in shifts:
        # Check if this invoice is linked to this shift
        # We find shift matching participant and code on same month (covers all 3 tiers)
        # Note: In SQLite, we can query or scan. We do a scan here.
        if (s["participant_id"] == inv["participant_reference"] and
            s["support_item_code"] == inv["support_item_code"]):
            # Check date matching
            try:
                s_dt = datetime.strptime(s["service_date"], "%Y-%m-%d")
                i_dt = datetime.strptime(inv["line_date"], "%Y-%m-%d")
                if s_dt.year == i_dt.year and s_dt.month == i_dt.month:
                    matched_shift = s
                    break
            except Exception:
                pass

    # 3. Time-of-Day and Day-of-Week Pricing Compliance
    try:
        inv_date = datetime.strptime(inv["line_date"], "%Y-%m-%d")
        day_name = inv_date.strftime("%A")
        is_weekend = inv_date.weekday() in [5, 6]
        
        # Check weekend support billing code
        if is_weekend:
            # Weekday standard support item code billed on weekend
            if inv["support_item_code"] == "01_011_0107_1_1":
                cursor.execute("""
                INSERT INTO compliance_flags 
                (invoice_id, invoice_number, rule_violated, severity, recommended_action, details)
                VALUES (?, ?, 'time_of_day', 'medium', 
                        'Underclaiming risk. Weekday code billed for weekend service. Check if weekend loading applies.', 
                        ?)
                """, (inv["invoice_id"], inv["invoice_number"], 
                      f"Billed weekday code {inv['support_item_code']} on {day_name}."))
        
        # If standard code was used but start time was in evening
        if matched_shift and inv["support_item_code"] == "01_011_0107_1_1":
            start_t = matched_shift["start_time"]
            if start_t:
                # If start_time is >= 20:00 (8:00 PM), evening rates should apply
                try:
                    start_hour = int(start_t.split(':')[0])
                    if start_hour >= 20:
                        cursor.execute("""
                        INSERT INTO compliance_flags 
                        (invoice_id, invoice_number, rule_violated, severity, recommended_action, details)
                        VALUES (?, ?, 'time_of_day', 'medium', 
                                'Underclaiming risk. Evening shift billed using standard weekday code. Rebill with evening code.', 
                                ?)
                        """, (inv["invoice_id"], inv["invoice_number"], 
                              f"Shift started at {start_t} (evening) but billed weekday standard code."))
                except Exception:
                    pass
    except Exception:
        pass

    # 4. Cancellation Compliance Check
    if matched_shift and matched_shift["claim_status"] == "cancelled":
        if inv["line_total"] > 0:
            cursor.execute("""
            INSERT INTO compliance_flags 
            (invoice_id, invoice_number, rule_violated, severity, recommended_action, details)
            VALUES (?, ?, 'cancellation', 'medium', 
                    'Check NDIS cancellation rules. Billed full rate on a cancelled shift. Ensure client gave consent.', 
                    ?)
            """, (inv["invoice_id"], inv["invoice_number"], 
                  f"Billed full rate for cancelled shift (ID: {matched_shift['shift_id']})."))

if __name__ == "__main__":
    run_reconciliation()
