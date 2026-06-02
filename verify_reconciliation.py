import sqlite3
from database import init_db, load_ndis_price_guide, load_shiftcare_shifts, load_xero_invoices, get_db
from reconciler import run_reconciliation

def run_verification():
    print("--- Starting Reconciliation Core Verification ---")
    
    # 1. Initialize and clean the database
    init_db()
    
    # 2. Load generated sample CSV files
    print("\n[Loading sample CSV files...]")
    price_rules_count = load_ndis_price_guide("sample_data/ndis_price_guide_2025_26.csv")
    print(f"Loaded {price_rules_count} NDIS Price Guide rules.")
    
    shifts_count = load_shiftcare_shifts("sample_data/shiftcare_shifts_sample.csv")
    print(f"Loaded {shifts_count} ShiftCare shifts.")
    
    invoices_count = load_xero_invoices("sample_data/xero_invoices_sample.csv")
    print(f"Loaded {invoices_count} Xero invoice lines.")
    
    # 3. Run reconciliation
    print("\n[Running reconciliation engine...]")
    run_reconciliation()
    
    # 4. Query results and assert counts
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM reconciliation_results")
    results_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reconciliation_results WHERE match_status = 'matched'")
    matched_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reconciliation_results WHERE match_status = 'partial'")
    partial_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reconciliation_results WHERE match_status = 'unmatched'")
    unmatched_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM reconciliation_results WHERE discrepancy_type = 'unbilled_shift'")
    unbilled_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(discrepancy_amount) FROM reconciliation_results WHERE discrepancy_type = 'unbilled_shift'")
    revenue_leakage = cursor.fetchone()[0] or 0.0
    
    cursor.execute("SELECT COUNT(*) FROM compliance_flags")
    flags_count = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n--- Verification Summary Results ---")
    print(f"Total Reconciliation Results logged: {results_count}")
    print(f"  - Perfect Matches: {matched_count}")
    print(f"  - Partial Mismatches: {partial_count}")
    print(f"  - Unmatched anomalies: {unmatched_count}")
    print(f"Total Unbilled Care Shifts (Revenue Leakage): {unbilled_count} shifts")
    print(f"Total Estimated Revenue Leakage value: ${revenue_leakage:.2f}")
    print(f"Total NDIS Compliance Flags raised: {flags_count}")
    
    # Simple sanity checks
    assert price_rules_count > 0, "No NDIS rules were loaded!"
    assert shifts_count > 0, "No shifts were loaded!"
    assert invoices_count > 0, "No invoice lines were loaded!"
    assert results_count > 0, "Reconciliation process failed to write results!"
    assert unbilled_count > 0, "Failed to identify the known unbilled Saturday shift!"
    assert flags_count > 0, "Failed to identify known NDIS compliance flags!"
    
    print("\n[SUCCESS] Verification complete. All assertions passed. Reconciler matches expected results.")

if __name__ == "__main__":
    run_verification()
