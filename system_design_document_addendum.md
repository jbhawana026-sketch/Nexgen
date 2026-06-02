# System Design Document (SDD) Addendum
## Splana NDIS Reconciliation Platform

This document serves as an addendum to the Splana System Design Document (Section 5 of the Final Report). It explains the root causes of three critical issues identified in the prototype reconciliation engine and details how a production-grade system would solve them.

---

## 1. Dashboard Discrepancy & Reconciliation (Issue 1)

### The Problem in the Prototype
The dashboard totals did not reconcile with the sub-page counts. Specifically, the **Revenue Leakage** card on the dashboard showed a different sum than what a user would calculate by adding the values on the **Unmatched Shifts** sub-page. 
This happened because of two inconsistencies:
1. **Misclassification**: Underbilled duration mismatches (shifts that were longer than the invoiced quantity) were classified as `duration_mismatch` in the database. The dashboard grouped all `duration_mismatch` rows under **Invoice Error Cost**. However, the **Unmatched Shifts** sub-page displayed these rows because they represent unbilled hours (leakage). Consequently, the same dollar value was counted as an "Invoice Error Cost" on the dashboard but as "Revenue Leakage" on the sub-page.
2. **Breakdown Tables**: The dashboard's "Revenue Leakage by Participant" and "Revenue Leakage by Care Staff" breakdown tables summed *all* discrepancies (including overbilling and rate overruns), even though they were titled "Revenue Leakage".

### The Prototype Fix
We tightened the query logic in `app.py` to establish consistent definitions:
- **Revenue Leakage** = Unmatched active shifts (`unbilled_shift`) + Underbilled duration mismatches (where `shift.duration_hours > invoice.quantity`).
- **Invoice Error Cost** = Unmatched invoices (`missing_shift`) + Rate overruns (`rate_mismatch`) + Overbilled duration mismatches (where `shift.duration_hours < invoice.quantity`).
- The dashboard breakdowns and sub-pages were updated to use these exact queries, and summary cards were added to `unmatched_shifts.html` and `invoice_errors.html` to display the reconciled totals.

### Production Solution
In a production-ready application, this matching state should not be derived via complex SQL joins on a temporary flat table.
1. **Billing Reconciliation State Machine**: The database should model the reconciliation status as a first-class state machine with columns for `billing_state` (`UNBILLED`, `BILLED_PARTIAL`, `BILLED_COMPLETE`, `OVERBILLED`).
2. **Double-Entry Ledger Schema**: A ledger-based schema would record the expected revenue (from shifts) and actual invoiced revenue (from invoice lines). Leakage is simply `max(0, expected_revenue - actual_revenue)`. This ensures that totals are mathematically guaranteed to reconcile across all views.

---

## 2. Revenue Leakage Under-reporting & Unit Rate Bug (Issue 2)

### The Problem in the Prototype
Some unmatched shifts in the prototype were displaying the *unit rate alone* (e.g. $70.23) as the leakage amount instead of the full shift amount (e.g. 6 hours * $70.23 = $421.38).
This occurred due to a side-effect of **Tier 3 (Same Month) Matching**:
- A shift of 6 hours was incorrectly matched to an invoice line of 5 hours for the same participant and support code later in the month.
- Because they matched, the shift was marked as `matched` / `partial` and removed from the unmatched shift registry (saving it from showing 100% leakage of $421.38).
- The engine calculated a `duration_diff` of `6.0 - 5.0 = 1.0` hour and flagged it as a duration mismatch.
- The discrepancy amount was recorded as `1.0 * unit_amount = $70.23` (the unit rate alone).
- In reality, these were two completely different shifts. The 6-hour shift was never billed, representing $421.38 of leakage. The 5-hour invoice line was for a different day. The prototype thus under-reported the leakage by $351.15 for this single pair.

### The Prototype Fix
- We refactored `process_match` in `reconciler.py` to calculate mismatch amounts using the national price limit rather than the invoiced rate, ensuring underbilled amounts are valued at the maximum rate the provider is entitled to claim.
- We updated `app.py` to treat underbilled duration mismatches as leakage, reconciling the display.

### Production Solution
A production build must prevent date-slippage matches:
1. **Dynamic Rate Evaluation**: The leakage formula should always be `duration * price_limit` for unmatched logs.
2. **Disable Loose Date Heuristics**: Tier 3 matching (month-level) must be deactivated. Date-based matching must be restricted to a strict 24-hour window (±1 day) to handle night shifts spanning midnight.
3. **Manual Review Queue**: If date-slippage matches are allowed, they must be routed to a "Draft Match" approval queue and never count as reconciled until a finance officer confirms they represent the same service.

---

## 3. False-Positive Rate on Unmatched Shifts (Issue 3)

### Analysis of the Prototype Date-Slippage Heuristics
The prototype uses a three-tier matching heuristic. Let's analyze the matches in the December 2025 dataset:
- **Tier 1 (Exact Match)**: Matches 430 shifts.
- **Tier 2 (±1 Day Match)**: Matches 1 shift.
- **Tier 3 (Same Month Match)**: Matches 9 shifts.

An audit of the **Tier 3 matches** reveals severe date-slippage:
- Shift `SH-1048` (**Dec 3rd**) matched to invoice `INV-5067` (**Dec 13th**) — **10 days apart**.
- Shift `SH-1075` (**Dec 5th**) matched to invoice `INV-5150` (**Dec 24th**) — **19 days apart**.
- Shift `SH-1368` (**Dec 23rd**) matched to invoice `INV-5033` (**Dec 7th**) — — **16 days apart**.

### The False-Positive Rate
In NDIS billing, services are rendered on specific dates and must be claimed with those exact dates. A shift on Dec 5th cannot be billed against an invoice line dated Dec 24th. 
Therefore, **100% of the 9 Tier 3 matches in the sample data are false-positives**.
- **Impact**: These 9 false-positive matches hid 9 unbilled shifts, under-reporting the true revenue leakage by **$3,255.42** (the sum of those 9 shifts).
- **False-Negative Rate**: The actual number of unmatched shifts was 32, but the prototype only reported 23, representing a **28% false-negative rate** (failing to identify unbilled shifts).

### Production Solution
To achieve a **0% false-positive rate** in production:
1. **Unique Reference Keys (Single Source of Truth)**:
   - When a support worker completes a shift in ShiftCare, the system must generate a unique, non-sequential `Shift_Transaction_ID`.
   - When the invoice is drafted in Xero, this `Shift_Transaction_ID` must be written into a custom field on the invoice line item or appended to the description.
   - The reconciliation engine will then match records **strictly on the unique ID**, bypassing all date and code heuristics.
2. **Direct API Integration & Synchronization**:
   - Implement webhooks or a cron sync task using Xero API and ShiftCare API.
   - Instead of manual CSV uploads, the system should fetch shifts and invoices automatically.
   - The system should automatically draft Xero invoice lines from ShiftCare shift records, establishing a database-level link (`foreign key`) at the time of creation.
3. **Audit Trail**:
   - If a manual link is made by a finance officer, it must be recorded in an audit trail table with the user's ID, timestamp, and justification, preserving system integrity.
