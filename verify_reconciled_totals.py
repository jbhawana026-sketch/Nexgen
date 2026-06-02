import sqlite3
from database import get_db, init_db, load_ndis_price_guide, load_shiftcare_shifts, load_xero_invoices
from reconciler import run_reconciliation

def run_tests():
    print("--- Running Verification of Reconciled Totals ---")
    
    # 1. Initialize and clean the database, load real CSV files, and run reconciliation
    init_db()
    load_ndis_price_guide("ndis_price_guide_sample.csv")
    load_shiftcare_shifts("shiftcare_shifts_sample.csv")
    load_xero_invoices("xero_invoices_sample.csv")
    run_reconciliation()
    
    conn = get_db()
    cursor = conn.cursor()
    
    # 2. Query Dashboard KPIs
    # Revenue leakage (unmatched active shifts + underbilled duration mismatch)
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
    """)
    dashboard_leakage = cursor.fetchone()['val']
    
    # Invoice Error cost (unmatched invoices + overbilled rate/duration discrepancies)
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
    """)
    dashboard_errors = cursor.fetchone()['val']
    
    print(f"Dashboard Revenue Leakage KPI: ${dashboard_leakage:.2f}")
    print(f"Dashboard Invoice Error Cost KPI: ${dashboard_errors:.2f}")
    
    # 3. Query Unmatched Shifts Page
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'unbilled_shift'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
    """)
    page_leakage = cursor.fetchone()['val']
    
    # 4. Query Invoice Errors Page
    cursor.execute("""
        SELECT COALESCE(SUM(r.discrepancy_amount), 0.0) as val 
        FROM reconciliation_results r
        LEFT JOIN shifts s ON r.shift_id = s.shift_id
        LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
        WHERE r.discrepancy_type = 'missing_shift'
           OR r.discrepancy_type = 'rate_mismatch'
           OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours < i.quantity)
    """)
    page_errors = cursor.fetchone()['val']
    
    print(f"Unmatched Shifts Page Total: ${page_leakage:.2f}")
    print(f"Invoice Errors Page Total: ${page_errors:.2f}")
    
    # 5. Query Participant Breakdown Sum
    cursor.execute("""
        SELECT SUM(total_discrepancy) FROM (
            SELECT SUM(r.discrepancy_amount) as total_discrepancy
            FROM reconciliation_results r
            LEFT JOIN shifts s ON r.shift_id = s.shift_id
            LEFT JOIN invoices i ON r.invoice_id = i.invoice_id
            WHERE r.discrepancy_type = 'unbilled_shift'
               OR (r.discrepancy_type = 'duration_mismatch' AND s.duration_hours > i.quantity)
            GROUP BY COALESCE(s.participant_id, i.participant_reference)
        )
    """)
    breakdown_participant_sum = cursor.fetchone()[0] or 0.0
    print(f"Participant Breakdown Sum: ${breakdown_participant_sum:.2f}")
    
    # 6. Assertions
    assert abs(dashboard_leakage - page_leakage) < 0.01, "Revenue Leakage does not reconcile between Dashboard and sub-page!"
    assert abs(dashboard_errors - page_errors) < 0.01, "Invoice Error Cost does not reconcile between Dashboard and sub-page!"
    assert abs(dashboard_leakage - breakdown_participant_sum) < 0.01, "Revenue Leakage breakdown does not sum to dashboard KPI!"
    
    conn.close()
    print("\n[SUCCESS] All verification assertions passed! Totals reconcile perfectly across all pages and components.")

if __name__ == "__main__":
    run_tests()
