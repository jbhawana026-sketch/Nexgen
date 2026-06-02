import sqlite3
from database import init_db, load_ndis_price_guide, load_shiftcare_shifts, load_xero_invoices, get_db
from reconciler import run_reconciliation

def run_verification():
    print("--- Starting XML Ingestion & Reconciliation Verification ---")
    
    # 1. Initialize and clean the database
    init_db()
    
    # 2. Load generated sample XML files
    print("\n[Loading sample XML files...]")
    price_rules_count = load_ndis_price_guide("sample_data/ndis_price_guide_2025_26.xml")
    print(f"Loaded {price_rules_count} NDIS Price Guide rules.")
    
    shifts_count = load_shiftcare_shifts("sample_data/shiftcare_shifts_sample.xml")
    print(f"Loaded {shifts_count} ShiftCare shifts.")
    
    invoices_count = load_xero_invoices("sample_data/xero_invoices_sample.xml")
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
    
    print("\n--- Verification Summary Results (XML) ---")
    print(f"Total Reconciliation Results logged: {results_count}")
    print(f"  - Perfect Matches: {matched_count}")
    print(f"  - Partial Mismatches: {partial_count}")
    print(f"  - Unmatched anomalies: {unmatched_count}")
    print(f"Total Unbilled Care Shifts (Revenue Leakage): {unbilled_count} shifts")
    print(f"Total Estimated Revenue Leakage value: ${revenue_leakage:.2f}")
    print(f"Total NDIS Compliance Flags raised: {flags_count}")
    
    # Assert counts match the CSV results exactly
    assert price_rules_count == 9, f"Expected 9 price rules, got {price_rules_count}"
    assert shifts_count == 17, f"Expected 17 shifts, got {shifts_count}"
    assert invoices_count == 17, f"Expected 17 invoice lines, got {invoices_count}"
    assert results_count == 19, f"Expected 19 results, got {results_count}"
    assert matched_count == 13, f"Expected 13 matched shifts, got {matched_count}"
    assert partial_count == 2, f"Expected 2 partial mismatches, got {partial_count}"
    assert unmatched_count == 4, f"Expected 4 unmatched anomalies, got {unmatched_count}"
    assert flags_count == 3, f"Expected 3 compliance flags, got {flags_count}"
    
    print("\n[SUCCESS] XML Ingestion Verification complete. All assertions passed. XML records parsed and matched exactly like CSV records.")

if __name__ == "__main__":
    run_verification()
