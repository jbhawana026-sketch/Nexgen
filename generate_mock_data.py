import os
import csv
import pandas as pd
from datetime import datetime, timedelta

def save_df_to_xml(df, root_name, child_name, filepath):
    import xml.etree.ElementTree as ET
    root = ET.Element(root_name)
    for _, row in df.iterrows():
        child = ET.SubElement(root, child_name)
        for col in df.columns:
            sub = ET.SubElement(child, col)
            val = row[col]
            if pd.isna(val):
                sub.text = ""
            elif isinstance(val, float):
                if col in ['price_limit_national', 'line_total', 'duration_hours', 'quantity']:
                    sub.text = f"{val:.2f}"
                else:
                    sub.text = str(val)
            else:
                sub.text = str(val)
    # Pretty print helper
    from xml.dom import minidom
    xml_str = ET.tostring(root, encoding='utf-8')
    reparsed = minidom.parseString(xml_str)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(pretty_xml)

def generate_data():
    os.makedirs('sample_data', exist_ok=True)
    
    # 1. Generate NDIS Price Guide 2025-26
    price_guide_items = [
        {
            "support_item_code": "01_011_0107_1_1",
            "service_description": "Access Community Social and Rec Activ - Standard - Weekday",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "H",
            "price_limit_national": 67.56,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "01_015_0107_1_1",
            "service_description": "Access Community Social and Rec Activ - Standard - Evening",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "H",
            "price_limit_national": 74.45,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "01_013_0107_1_1",
            "service_description": "Access Community Social and Rec Activ - Standard - Saturday",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "H",
            "price_limit_national": 94.90,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "01_014_0107_1_1",
            "service_description": "Access Community Social and Rec Activ - Standard - Sunday",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "H",
            "price_limit_national": 122.25,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "01_012_0107_1_1",
            "service_description": "Access Community Social and Rec Activ - Standard - Public Holiday",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "H",
            "price_limit_national": 149.60,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "15_055_0128_1_3",
            "service_description": "Assessment Recommendation Therapy or Training - Physiotherapist",
            "registration_group": "Therapeutic Supports",
            "unit": "H",
            "price_limit_national": 193.99,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "15_056_0128_1_3",
            "service_description": "Assessment Recommendation Therapy or Training - Occupational Therapist",
            "registration_group": "Therapeutic Supports",
            "unit": "H",
            "price_limit_national": 193.99,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "01_799_0107_1_1",
            "service_description": "Provider Travel - Non-Labor Costs",
            "registration_group": "Assist Access/Maintain Employ",
            "unit": "KM",
            "price_limit_national": 0.97,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        },
        {
            "support_item_code": "04_111_0136_6_1",
            "service_description": "Group Activities in a Centre - Standard - Weekday",
            "registration_group": "Group/Centre Activities",
            "unit": "H",
            "price_limit_national": 35.40,
            "effective_from": "2025-07-01",
            "effective_to": "2026-06-30"
        }
    ]
    
    # Save NDIS Price Guide CSV
    df_rules = pd.DataFrame(price_guide_items)
    df_rules.to_csv('sample_data/ndis_price_guide_2025_26.csv', index=False)
    
    # Save NDIS Price Guide XML
    save_df_to_xml(df_rules, "price_rules", "price_rule", "sample_data/ndis_price_guide_2025_26.xml")
        
    participants = {
        "P001": "John Doe",
        "P002": "Sarah Jenkins",
        "P003": "Alex Smith",
        "P004": "Emma Watson",
        "P005": "David Miller"
    }
    
    staff = ["ST001", "ST002", "ST003", "ST004"]
    start_date = datetime(2026, 5, 1)
    
    shifts = []
    invoices = []
    
    date_formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y"]
    
    invoice_seq = 1000
    shift_seq = 5000
    
    for i in range(15):
        current_date = start_date + timedelta(days=i)
        is_weekend = current_date.weekday() in [5, 6]
        is_saturday = current_date.weekday() == 5
        is_sunday = current_date.weekday() == 6
        
        date_format = date_formats[i % len(date_formats)]
        date_str_shift = current_date.strftime(date_format)
        date_str_invoice = current_date.strftime(date_formats[(i + 1) % len(date_formats)])
        
        # 1. Clean Match: John Doe weekday shift
        if not is_weekend:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P001",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "09:00",
                "end_time": "12:00",
                "duration_hours": 3.0,
                "staff_id": "ST001",
                "location": "Sydney Central",
                "claim_status": "claimed"
            })
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P001",
                "support_item_code": "01_011_0107_1_1",
                "description": "Access Community Social - Weekday service for John Doe",
                "quantity": 3.0,
                "unit_amount": "$67.56",
                "line_total": 202.68,
                "payment_status": "Paid"
            })
            
        # 2. Rate Limit Compliance Violation: Sarah Jenkins weekday therapy
        if not is_weekend and i == 2:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P002",
                "support_item_code": "15_055_0128_1_3",
                "service_date": date_str_shift,
                "start_time": "14:00",
                "end_time": "15:00",
                "duration_hours": 1.0,
                "staff_id": "ST002",
                "location": "North Sydney",
                "claim_status": "claimed"
            })
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P002",
                "support_item_code": "15_055_0128_1_3",
                "description": "Physiotherapy Session - Sarah Jenkins",
                "quantity": 1.0,
                "unit_amount": "$210.00",
                "line_total": 210.00,
                "payment_status": "Awaiting Payment"
            })
            
        # 3. Revenue Leakage: Unbilled Saturday shift
        if is_saturday and i == 1:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P003",
                "support_item_code": "01_013_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "10:00",
                "end_time": "14:00",
                "duration_hours": 4.0,
                "staff_id": "ST003",
                "location": "Parramatta",
                "claim_status": "unclaimed"
            })
            
        # 4. Invoice with No Matching Shift (Billing Error)
        if not is_weekend and i == 4:
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P004",
                "support_item_code": "01_011_0107_1_1",
                "description": "Extra community access service billed",
                "quantity": 2.0,
                "unit_amount": "$67.56",
                "line_total": 135.12,
                "payment_status": "Awaiting Payment"
            })
            
        # 5. Quantity / Duration Mismatch
        if not is_weekend and i == 7:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P001",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "12:00",
                "end_time": "16:00",
                "duration_hours": 4.0,
                "staff_id": "ST001",
                "location": "Sydney Central",
                "claim_status": "claimed"
            })
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P001",
                "support_item_code": "01_011_0107_1_1",
                "description": "Access Community Social - John Doe",
                "quantity": 5.0,
                "unit_amount": "$67.56",
                "line_total": 337.80,
                "payment_status": "Paid"
            })
            
        # 6. Secondary Match: Invoice billed late (+1 day)
        if not is_weekend and i == 8:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P002",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "10:00",
                "end_time": "12:00",
                "duration_hours": 2.0,
                "staff_id": "ST002",
                "location": "North Sydney",
                "claim_status": "claimed"
            })
            
            invoice_date = current_date + timedelta(days=1)
            invoice_date_str = invoice_date.strftime(date_format)
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": invoice_date_str,
                "participant_reference": "P002",
                "support_item_code": "01_011_0107_1_1",
                "description": "Access Community - Late billed for Sarah Jenkins",
                "quantity": 2.0,
                "unit_amount": "$67.56",
                "line_total": 135.12,
                "payment_status": "Paid"
            })
            
        # 7. Tertiary Match: Same month, but different day (+5 days) - Loose Match
        if not is_weekend and i == 9:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P005",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "09:00",
                "end_time": "11:00",
                "duration_hours": 2.0,
                "staff_id": "ST004",
                "location": "Ryde",
                "claim_status": "claimed"
            })
            
            invoice_date = current_date + timedelta(days=5)
            invoice_date_str = invoice_date.strftime(date_format)
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": invoice_date_str,
                "participant_reference": "P005",
                "support_item_code": "01_011_0107_1_1",
                "description": "Loose match service for David Miller",
                "quantity": 2.0,
                "unit_amount": "$67.56",
                "line_total": 135.12,
                "payment_status": "Awaiting Payment"
            })
            
        # 8. Unreasonable Duration Compliance Flag (26 hours billed!)
        if not is_weekend and i == 11:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P001",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "08:00",
                "end_time": "14:00",
                "duration_hours": 6.0,
                "staff_id": "ST001",
                "location": "Sydney Central",
                "claim_status": "claimed"
            })
            
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P001",
                "support_item_code": "01_011_0107_1_1",
                "description": "Access Community - Typos in quantity (26 hours billed!)",
                "quantity": 26.0,
                "unit_amount": "$67.56",
                "line_total": 1756.56,
                "payment_status": "Awaiting Payment"
            })
            
        # 9. Time-of-day Pricing Underclaiming
        if is_saturday and i == 8:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P002",
                "support_item_code": "01_013_0107_1_1", # Saturday
                "service_date": date_str_shift,
                "start_time": "13:00",
                "end_time": "15:00",
                "duration_hours": 2.0,
                "staff_id": "ST002",
                "location": "North Sydney",
                "claim_status": "claimed"
            })
            
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P002",
                "support_item_code": "01_011_0107_1_1", # Weekday code used on Saturday
                "description": "Saturday service billed at standard weekday rate",
                "quantity": 2.0,
                "unit_amount": "$67.56",
                "line_total": 135.12,
                "payment_status": "Paid"
            })
            
        # 10. Cancellation Compliance Flag (Cancelled shift fully billed)
        if not is_weekend and i == 12:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P003",
                "support_item_code": "01_011_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "09:00",
                "end_time": "11:00",
                "duration_hours": 2.0,
                "staff_id": "ST003",
                "location": "Parramatta",
                "claim_status": "cancelled"
            })
            
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": date_str_invoice,
                "participant_reference": "P003",
                "support_item_code": "01_011_0107_1_1",
                "description": "Community Standard Weekday - Cancelled without notice but billed full rate",
                "quantity": 2.0,
                "unit_amount": "$67.56",
                "line_total": 135.12,
                "payment_status": "Paid"
            })
            
        # 11. Midnight shift spanning check
        if not is_weekend and i == 13:
            shift_id = f"SH{shift_seq}"
            shift_seq += 1
            invoice_num = f"INV-{invoice_seq}"
            invoice_seq += 1
            
            shifts.append({
                "shift_id": shift_id,
                "participant_id": "P001",
                "support_item_code": "01_015_0107_1_1",
                "service_date": date_str_shift,
                "start_time": "22:00",
                "end_time": "02:00",
                "duration_hours": 4.0,
                "staff_id": "ST001",
                "location": "Sydney Central",
                "claim_status": "claimed"
            })
            
            invoice_date = current_date + timedelta(days=1)
            invoice_date_str = invoice_date.strftime(date_format)
            invoices.append({
                "invoice_number": invoice_num,
                "line_date": invoice_date_str,
                "participant_reference": "P001",
                "support_item_code": "01_015_0107_1_1",
                "description": "Midnight shift community access - John Doe",
                "quantity": 4.0,
                "unit_amount": "$74.45",
                "line_total": 297.80,
                "payment_status": "Paid"
            })

    # Save Shifts CSV & XML
    df_shifts = pd.DataFrame(shifts)
    df_shifts.to_csv('sample_data/shiftcare_shifts_sample.csv', index=False)
    save_df_to_xml(df_shifts, "shifts", "shift", "sample_data/shiftcare_shifts_sample.xml")
    
    # Save Invoices CSV & XML
    df_invoices = pd.DataFrame(invoices)
    df_invoices.to_csv('sample_data/xero_invoices_sample.csv', index=False)
    save_df_to_xml(df_invoices, "invoices", "invoice_line", "sample_data/xero_invoices_sample.xml")
    
    print("Mock files (CSV and XML) created successfully in 'sample_data/'!")

if __name__ == "__main__":
    generate_data()
