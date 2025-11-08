
# app_with_validation.py
# Mahabank - Personal Loan Decision Tool (Complete)
# Features:
#  - Automated scoring & eligibility (Annexure 1A/1B rules)
#  - Compliance checklist (KYC, payslips, fraud, bank relation, address)
#  - Pre-Sanction Visit Report (PSVR) enforcement
#  - Sanction letter PDF generation (ReportLab)
#  - Annexure JSON export
#  - Bulk CSV processing
#
# Usage:
#   pip install streamlit pandas numpy reportlab
#   streamlit run app_with_validation.py

import streamlit as st
import pandas as pd
import math
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import date

st.set_page_config(page_title="Mahabank - Personal Loan Decision Tool", layout="wide")

def emi_amount(principal: float, annual_rate_percent: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_percent / 100.0 / 12.0
    if r == 0:
        return principal / months
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return emi

@dataclass
class Applicant:
    name: str
    applicant_type: str
    age: int
    gross_monthly_income: Optional[float] = None
    gross_annual_income: Optional[float] = None
    cibil_score: Optional[int] = None
    salary_account_with_bom: bool = False
    category: Optional[str] = None
    work_experience_years: Optional[float] = 0
    marital_status: Optional[str] = 'single'
    dependents: Optional[int] = 0
    bank_relationship_years: Optional[int] = 0
    residence_type: Optional[str] = 'rented'
    years_at_address: Optional[int] = 0
    spouse_income_annual: Optional[float] = 0.0
    disposable_monthly_income: Optional[float] = 0.0
    emi_nmi_ratio_percent: Optional[float] = 0.0
    repayment_type: Optional[str] = 'others'
    itr_years_filed: Optional[int] = 0
    avg_balance_to_emi_ratio_percent: Optional[float] = 0.0
    credit_history_score_choice: Optional[str] = 'best_36m'
    net_worth: Optional[float] = None
    proposed_loan_amount: Optional[float] = None
    business_turnover_annual: Optional[float] = None
    income_trend: Optional[str] = 'stable'

    kyc_ok: bool = False
    payslips_ok: bool = False
    fraud_ok: bool = False
    bank_rel_ok: bool = False
    address_ok: bool = False
    visit_officer: Optional[str] = None
    visit_date: Optional[str] = None
    visit_verified: bool = False
    visit_remarks: Optional[str] = None

@dataclass
class Decision:
    eligible: bool
    reason: str
    recommended_loan: float = 0.0
    tenure_months: int = 0
    annual_rate_percent: float = 0.0
    emi: float = 0.0
    score: Optional[float] = None
    grade: Optional[int] = None
    details: Dict = None

MARITAL_SCORE = {'single':3, 'married':5, 'divorced':1}
AGE_SCORE = lambda age: 0 if age<=21 else (3 if age<=30 else (5 if age<=45 else (4 if age<=55 else 2)))
DEPENDENT_SCORE = lambda d: 5 if d<2 else (4 if d<=3 else (3 if d<=5 else 1))
BANK_REL_SCORE = lambda yrs: 1 if yrs==0 else (3 if yrs<5 else (4 if yrs<10 else 5))
RESIDENCE_SCORE = {'rented':1, 'owned_non_metro':2, 'owned_metro':3, 'kaccha':1}
YEARS_AT_ADDRESS_SCORE = lambda y: 0 if y<1 else (1 if y<=3 else 2)
SPOUSE_INCOME_SCORE = lambda amt: 5 if amt>500000 else (4 if amt>300000 else (2 if amt>100000 else 0))
DISPOSABLE_INCOME_SCORE = lambda monthly: 0 if monthly<=8000 else (2 if monthly<=15000 else (3 if monthly<=25000 else 5))
EMI_NMI_SCORE = lambda pct: 10 if 20<=pct<=25 else (8 if 25<pct<=40 else (6 if 40<pct<=65 else 0))
REPAYMENT_TYPE_SCORE = {'others':0, 'post_dated_cheques':2, 'nach_other_bank':3, 'si_bom':4, 'checkoff':5}
ITR_SCORE = lambda years: 5 if years>=3 else (4 if years==2 else (3 if years==1 else 0))
AVG_BALANCE_SCORE = lambda ratio_percent: 5 if ratio_percent>200 else (4 if ratio_percent>100 else (3 if ratio_percent>50 else 2))
CIBIL_SCORE_SCORE = lambda s: 10 if s>=800 else (8 if s>=750 else (6 if s>=700 else (0 if s>600 else 3)))
CREDIT_HISTORY_MAP = {'best_36m':10, 'no_overdues_12m_prior':6, 'less_6m_no_arrears':4, 'no_bureau_hit':3,
                      'overdues_12m':2, 'less6m_with_arrears':0, 'weak_with_settlements':0}

PROF_NETWORTH_SCORE = lambda ratio: 0 if ratio<0.5 else (3 if ratio<0.75 else 5)
PROF_INCOME_TREND_SCORE = {'increasing':5, 'stable':2, 'unstable':1, 'decreasing':0}
PROF_TURNOVER_SCORE = lambda t: 1 if t<50e5 else (2 if t<80e5 else (3 if t<120e5 else (4 if t<400e5 else 5)))
PROF_ITR_SCORE = lambda yrs: 5 if yrs>=5 else (4 if yrs>=3 else (3 if yrs>=2 else 0))

RATE_TABLE_SALARIED = {
    ('A','bom',800):0.70, ('A','bom',776):1.00, ('A','bom',750):1.50, ('A','bom',700):2.00, ('A','bom','ntc'):1.70,
    ('A','other',800):1.50, ('A','other',776):2.00, ('A','other',750):2.50, ('A','other',700):3.00, ('A','other','ntc'):2.75,
    ('B','bom',800):1.50, ('B','bom',776):2.00, ('B','bom',750):2.50, ('B','bom',700):3.00, ('B','bom','ntc'):2.75,
    ('B','other',800):1.90, ('B','other',776):2.50, ('B','other',750):3.00, ('B','other',700):3.50, ('B','other','ntc'):3.25,
    ('C','other',800):1.90, ('C','other',776):2.45, ('C','other',750):2.95, ('C','other',700):3.45, ('C','other','ntc'):3.25
}
RATE_TABLE_PROF = {800:2.00, 776:2.50, 750:3.00, 700:3.50, 'ntc':2.75}

def compute_score_salaried(app: Applicant) -> Tuple[float,int]:
    score = 0.0
    score += 3
    score += 2
    we = app.work_experience_years or 0
    if we < 1:
        we_pts = 0
    elif we < 3:
        we_pts = 3
    elif we < 5:
        we_pts = 4
    else:
        we_pts = 5
    score += we_pts
    score += MARITAL_SCORE.get(app.marital_status or 'single',3)
    score += AGE_SCORE(app.age)
    score += DEPENDENT_SCORE(app.dependents or 0)
    score += BANK_REL_SCORE(app.bank_relationship_years or 0)
    score += RESIDENCE_SCORE.get(app.residence_type or 'rented',1)
    score += YEARS_AT_ADDRESS_SCORE(app.years_at_address or 0)
    score += SPOUSE_INCOME_SCORE(app.spouse_income_annual or 0)
    score += DISPOSABLE_INCOME_SCORE(app.disposable_monthly_income or 0)
    score += EMI_NMI_SCORE(app.emi_nmi_ratio_percent or 0)
    score += REPAYMENT_TYPE_SCORE.get(app.repayment_type or 'others',0)
    score += ITR_SCORE(app.itr_years_filed or 0)
    score += AVG_BALANCE_SCORE(app.avg_balance_to_emi_ratio_percent or 0)
    score += CIBIL_SCORE_SCORE(app.cibil_score or 0)
    score += CREDIT_HISTORY_MAP.get(app.credit_history_score_choice or 'best_36m',10)
    score = min(score, 100)
    grade = 1 if score>80 else (2 if score>=71 else (3 if score>=61 else (4 if score>=50 else 5)))
    return score, grade

def compute_score_professional(app: Applicant) -> Tuple[float,int]:
    score = 0.0
    score += 3
    score += DEPENDENT_SCORE(app.dependents or 0)
    we = app.work_experience_years or 0
    if we < 2:
        we_pts = 0
    elif we < 5:
        we_pts = 2
    elif we < 7:
        we_pts = 3
    elif we < 10:
        we_pts = 4
    else:
        we_pts = 5
    score += we_pts
    score += MARITAL_SCORE.get(app.marital_status or 'single',3)
    score += AGE_SCORE(app.age)
    score += BANK_REL_SCORE(app.bank_relationship_years or 0) * (10/5)
    score += RESIDENCE_SCORE.get(app.residence_type or 'rented',1)
    score += YEARS_AT_ADDRESS_SCORE(app.years_at_address or 0)
    score += DISPOSABLE_INCOME_SCORE(app.disposable_monthly_income or 0)
    score += EMI_NMI_SCORE(app.emi_nmi_ratio_percent or 0)
    if app.proposed_loan_amount and app.net_worth is not None and app.proposed_loan_amount>0:
        ratio = app.net_worth / app.proposed_loan_amount
    else:
        ratio = 0.0
    score += PROF_NETWORTH_SCORE(ratio)
    score += PROF_INCOME_TREND_SCORE.get(app.income_trend or 'stable',2)
    score += PROF_TURNOVER_SCORE(app.business_turnover_annual or 0)
    score += PROF_ITR_SCORE(app.itr_years_filed or 0)
    score += AVG_BALANCE_SCORE(app.avg_balance_to_emi_ratio_percent or 0)
    score += CIBIL_SCORE_SCORE(app.cibil_score or 0)
    score += CREDIT_HISTORY_MAP.get(app.credit_history_score_choice or 'best_36m',10)
    score = min(score, 100)
    grade = 1 if score>80 else (2 if score>=71 else (3 if score>=61 else (4 if score>=50 else 5)))
    return score, grade

def determine_interest_rate(app: Applicant, base_rllr_percent: float) -> float:
    if app.applicant_type == 'salaried':
        s = app.cibil_score or 0
        if s>=800:
            slab = 800
        elif s>=776:
            slab = 776
        elif s>=750:
            slab = 750
        elif s>=700:
            slab = 700
        else:
            slab = 'ntc'
        key = (app.category or 'C', 'bom' if app.salary_account_with_bom else 'other', slab)
        spread = RATE_TABLE_SALARIED.get(key, 3.5)
    else:
        s = app.cibil_score or 0
        if s>=800:
            slab = 800
        elif s>=776:
            slab = 776
        elif s>=750:
            slab = 750
        elif s>=700:
            slab = 700
        else:
            slab = 'ntc'
        spread = RATE_TABLE_PROF.get(slab, RATE_TABLE_PROF.get('ntc', 2.75))
    return base_rllr_percent + spread

def eligibility_and_recommendation(app: Applicant, base_rllr_percent: float) -> Decision:
    if not (app.kyc_ok and app.payslips_ok and app.fraud_ok and app.bank_rel_ok and app.address_ok):
        return Decision(False, "Compliance check failed — complete KYC / payslips / fraud / bank relation / address verification.", details={
            'kyc_ok': app.kyc_ok, 'payslips_ok': app.payslips_ok, 'fraud_ok': app.fraud_ok, 'bank_rel_ok': app.bank_rel_ok, 'address_ok': app.address_ok
        })
    if not app.visit_verified:
        return Decision(False, "PSVR incomplete or not satisfactory — cannot sanction until PSVR verified.", details={'visit_verified': app.visit_verified, 'visit_officer': app.visit_officer})
    if (app.cibil_score or 0) < 700:
        return Decision(False, f"CIBIL score below cutoff 700. CIBIL={app.cibil_score}")
    if app.applicant_type == 'salaried' and (app.age < 21 or app.age > 58):
        return Decision(False, f"Age not within allowed band for salaried (21-58). Age={app.age}")
    if app.applicant_type == 'salaried':
        score, grade = compute_score_salaried(app)
    else:
        score, grade = compute_score_professional(app)
    if app.applicant_type == 'salaried':
        gm = app.gross_monthly_income or 0
        eligible_amount = min(20 * gm, 20_00_000)
        tenure_months = 84 if (app.category == 'A' and app.salary_account_with_bom) else 60
        ded_limit_pct = 65 if app.category == 'A' else 60
    else:
        ga = app.gross_annual_income or 0
        eligible_amount = min(1.5 * ga, 20_00_000)
        tenure_months = 60
        ded_limit_pct = 60
    proposed = app.proposed_loan_amount or eligible_amount
    annual_rate = determine_interest_rate(app, base_rllr_percent)
    emi = emi_amount(proposed, annual_rate, tenure_months)
    gross_monthly = app.gross_monthly_income or (app.gross_annual_income / 12 if app.gross_annual_income else 0)
    if gross_monthly <= 0:
        return Decision(False, "Insufficient income data to compute deduction norms.", details={'gross_monthly': gross_monthly})
    proposed_emi_pct = (emi / gross_monthly) * 100
    if proposed_emi_pct > ded_limit_pct:
        return Decision(False, f"Proposed EMI {proposed_emi_pct:.1f}% of gross monthly exceeds deduction norm {ded_limit_pct}%.", details={'proposed_emi_pct': proposed_emi_pct})
    recommended = min(proposed, eligible_amount)
    rec_emi = emi_amount(recommended, annual_rate, tenure_months)
    decision_flag = True if grade <= 3 else False
    reason = "Clear sanction" if grade == 1 else ("Sanction with normal authority" if grade in (2,3) else "Requires higher authority/decline")
    return Decision(decision_flag, reason, recommended, tenure_months, annual_rate, rec_emi, score, grade, {
        'proposed': proposed,
        'eligible_by_income': eligible_amount,
        'proposed_emi_pct': proposed_emi_pct
    })

def generate_sanction_letter_pdf(applicant: Applicant, decision: Decision) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width / 2, height - 60, "BANK OF MAHARASHTRA")
    c.setFont("Helvetica", 11)
    c.drawCentredString(width / 2, height - 80, "Sanction Letter - Personal Loan Scheme")
    c.line(50, height - 90, width - 50, height - 90)
    y = height - 130
    c.setFont("Helvetica", 10)
    today = date.today().strftime("%d %B %Y")
    c.drawString(50, y, f"Date: {today}")
    y -= 20
    c.drawString(50, y, "To,")
    y -= 15
    c.drawString(70, y, f"{applicant.name}")
    y -= 15
    c.drawString(70, y, f"({applicant.applicant_type.capitalize()} Applicant)")
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Subject: Sanction of Personal Loan")
    y -= 25
    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Dear {applicant.name.split()[0]},")
    y -= 20
    para = ("We are pleased to inform you that your application for a Personal Loan has been "
            "sanctioned as per the following terms and conditions:")
    textobj = c.beginText(50, y)
    textobj.textLine(para)
    c.drawText(textobj)
    y -= 40
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "Sanction Details:")
    y -= 20
    c.setFont("Helvetica", 10)
    details = [
        ("Loan Amount (Rs.)", f"{decision.recommended_loan:,.2f}"),
        ("Tenure (months)", f"{decision.tenure_months}"),
        ("Interest Rate (p.a.)", f"{decision.annual_rate_percent:.2f}%"),
        ("EMI (Rs.)", f"{decision.emi:,.2f}"),
        ("Credit Score", f"{decision.score:.1f}"),
        ("Grade", f"{decision.grade}"),
        ("Sanction Type", decision.reason),
    ]
    for k, v in details:
        c.drawString(70, y, f"{k}:")
        c.drawString(250, y, str(v))
        y -= 15
    y -= 15
    c.setFont("Helvetica-Bold", 10)
    c.drawString(60, y, "Conditions / Remarks:")
    y -= 15
    c.setFont("Helvetica", 10)
    conditions = [
        "• Loan to be repaid in Equated Monthly Installments (EMIs) as per schedule.",
        "• Salary account to be maintained with Bank of Maharashtra (if applicable).",
        "• Insurance of borrower / collateral coverage to be ensured by borrower.",
        "• All standard terms & conditions of the Personal Loan Scheme apply.",
        "• This sanction is valid for 30 days from the date of issuance."
    ]
    for line in conditions:
        c.drawString(70, y, line)
        y -= 13
    y -= 20
    c.drawString(50, y, "Kindly contact your branch for documentation and disbursal formalities.")
    y -= 40
    c.drawString(50, y, "Yours faithfully,")
    y -= 20
    c.drawString(50, y, "Branch Manager / Sanctioning Authority")
    y -= 10
    c.line(50, y, 250, y)
    y -= 10
    c.drawString(50, y, "Bank of Maharashtra")
    c.showPage()
    c.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

def generate_annexure_json(applicant: Applicant, decision: Decision) -> str:
    annexure = {
        "ApplicantName": applicant.name,
        "ApplicantType": applicant.applicant_type,
        "Age": applicant.age,
        "CIBIL": applicant.cibil_score,
        "Score": decision.score,
        "Grade": decision.grade,
        "SanctionType": decision.reason,
        "LoanAmount": decision.recommended_loan,
        "TenureMonths": decision.tenure_months,
        "AnnualRatePercent": decision.annual_rate_percent,
        "EMI": decision.emi,
        "ComplianceChecklist": {
            "KYC": applicant.kyc_ok,
            "Payslips_ITR": applicant.payslips_ok,
            "FraudHistoryClear": applicant.fraud_ok,
            "BankRelationVerified": applicant.bank_rel_ok,
            "AddressVerified": applicant.address_ok
        },
        "PSVR": {
            "Officer": applicant.visit_officer,
            "Date": applicant.visit_date,
            "Verified": applicant.visit_verified,
            "Remarks": applicant.visit_remarks
        },
        "DecisionDetails": decision.details
    }
    return json.dumps(annexure, indent=2, default=str)

st.title("Mahabank — Personal Loan Decision Tool (with Compliance & PSVR)")
st.markdown("Automated scoring and sanction recommendations as per the Mahabank Master Circular. Provide current RLLR in sidebar.")

st.sidebar.header("Settings")
base_rllr = st.sidebar.number_input("Current RLLR (base rate %)", value=10.15, step=0.01, format="%.2f")
st.sidebar.write("CIBIL cutoff: 700 (per circular)")

mode = st.radio("Mode", ["Single Applicant", "Bulk CSV"])

def show_decision_ui(applicant: Applicant, decision: Decision):
    col1, col2 = st.columns([2,3])
    with col1:
        st.markdown("### Applicant snapshot")
        st.write({
            'Name': applicant.name,
            'Type': applicant.applicant_type,
            'Age': applicant.age,
            'Gross monthly': applicant.gross_monthly_income,
            'Gross annual': applicant.gross_annual_income,
            'CIBIL': applicant.cibil_score,
            'Category': applicant.category,
            'Salary at BOM': applicant.salary_account_with_bom
        })
    with col2:
        st.markdown("### Decision summary")
        st.metric("Eligible", "Yes" if decision.eligible else "No")
        st.write(f"**Reason:** {decision.reason}")
        if decision.score is not None:
            st.write(f"**Score:** {decision.score:.1f}   |   **Grade:** {decision.grade}")
        st.write(f"**Recommended loan (₹):** {decision.recommended_loan:,.2f}")
        st.write(f"**Tenure (months):** {decision.tenure_months}")
        st.write(f"**Interest rate (annual %):** {decision.annual_rate_percent:.3f}")
        st.write(f"**EMI (₹):** {decision.emi:,.2f}")
        if decision.details:
            st.write("**Details / checks:**")
            st.json(decision.details)
    annexure_json = generate_annexure_json(applicant, decision)
    st.download_button("📋 Download Annexure JSON", annexure_json, file_name=f"Annexure_{applicant.name.replace(' ','_')}.json", mime="application/json")
    if decision.eligible:
        pdf_bytes = generate_sanction_letter_pdf(applicant, decision)
        st.download_button("📄 Generate Sanction Letter (PDF)", data=pdf_bytes, file_name=f"Sanction_Letter_{applicant.name.replace(' ','_')}.pdf", mime="application/pdf")
    else:
        st.info("Sanction letter available only when eligible = Yes and PSVR/compliance complete.")

if mode == "Single Applicant":
    with st.form("app_form"):
        st.subheader("Applicant Information")
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Full name", "Applicant Name")
            applicant_type = st.selectbox("Applicant type", ["salaried","professional"])
            age = st.number_input("Age (years)", min_value=18, max_value=75, value=30)
            category = st.selectbox("Category (salaried) - A/B/C", ["A","B","C"]) if applicant_type=="salaried" else st.selectbox("Category (ignored for professionals)", ["N/A"], index=0)
            salary_with_bom = st.checkbox("Salary account with BOM?", value=True) if applicant_type=="salaried" else False
            cibil = st.number_input("CIBIL score (numeric)", min_value=0, max_value=999, value=780)
        with col2:
            if applicant_type=="salaried":
                gross_monthly = st.number_input("Gross monthly income (₹)", min_value=0.0, value=50000.0, step=1000.0, format="%.2f")
                gross_annual = None
            else:
                gross_annual = st.number_input("Average annual income (last 2 yrs) (₹)", min_value=0.0, value=800000.0, step=10000.0, format="%.2f")
                gross_monthly = None
            proposed = st.number_input("Proposed loan amount (₹)", min_value=0.0, value=500000.0, step=10000.0, format="%.2f")
            work_exp = st.number_input("Work/Profession experience (years)", min_value=0.0, value=5.0, step=0.5)
        st.markdown("### Other / risk parameters (help model accuracy)")
        col3, col4 = st.columns(2)
        with col3:
            marital = st.selectbox("Marital status", ["single","married","divorced"])
            dependents = st.number_input("No. of dependents", min_value=0, max_value=10, value=1)
            bank_rel = st.number_input("Bank relationship (years)", min_value=0, max_value=50, value=3)
            residence = st.selectbox("Residence type", ["rented","owned_non_metro","owned_metro","kaccha"])
            years_at_addr = st.number_input("Years at address", min_value=0, max_value=50, value=2)
        with col4:
            spouse_inc = st.number_input("Spouse annual income (₹)", min_value=0.0, value=0.0, step=10000.0, format="%.2f")
            disposable = st.number_input("Disposable monthly income (₹)", min_value=0.0, value=15000.0, step=500.0, format="%.2f")
            emi_nmi = st.number_input("Existing EMI / Net monthly income (%)", min_value=0.0, value=10.0, step=0.5, format="%.2f")
            repayment_type = st.selectbox("Repayment type", list(REPAYMENT_TYPE_SCORE.keys()))
            itr_years = st.number_input("ITR years filed", min_value=0, max_value=20, value=2)
            avg_bal_ratio = st.number_input("Avg bal to EMI ratio (%)", min_value=0.0, value=100.0, step=1.0, format="%.2f")
            credit_hist = st.selectbox("Credit history track", list(CREDIT_HISTORY_MAP.keys()), index=0)
        net_worth = None
        biz_turnover = None
        income_trend = None
        if applicant_type == "professional":
            st.markdown("### Professional-specific fields")
            colp1, colp2 = st.columns(2)
            with colp1:
                net_worth = st.number_input("Net Worth (₹)", min_value=0.0, value=1000000.0, step=10000.0, format="%.2f")
                biz_turnover = st.number_input("Annual turnover (₹)", min_value=0.0, value=2000000.0, step=10000.0, format="%.2f")
            with colp2:
                income_trend = st.selectbox("Income trend", ["increasing","stable","unstable","decreasing"])
        st.markdown("### Compliance / Fraud-Prevention Checklist (mandatory)")
        colc1, colc2 = st.columns(2)
        with colc1:
            kyc_ok = st.checkbox("KYC (PAN & Aadhaar) verified", value=False)
            payslips_ok = st.checkbox("Latest 3 payslips / ITR verified", value=False)
            fraud_ok = st.checkbox("No CIBIL/CIC fraud or write-off record", value=False)
        with colc2:
            bank_rel_ok = st.checkbox("Bank relationship verified in CBS", value=False)
            address_ok = st.checkbox("Residence/Office address verified", value=False)
        st.markdown("### Pre-Sanction Visit Report (PSVR)")
        colv1, colv2 = st.columns(2)
        with colv1:
            visit_officer = st.text_input("Officer name performing PSVR", value="")
            visit_date = st.date_input("Visit date")
        with colv2:
            visit_verified = st.checkbox("Income & address verified satisfactory?", value=False)
            visit_remarks = st.text_area("PSVR remarks", value="")
        submitted = st.form_submit_button("Evaluate Applicant")
        if submitted:
            applicant = Applicant(
                name=name,
                applicant_type=applicant_type,
                age=int(age),
                gross_monthly_income=float(gross_monthly) if gross_monthly else None,
                gross_annual_income=float(gross_annual) if gross_annual else None,
                cibil_score=int(cibil),
                salary_account_with_bom=salary_with_bom,
                category=category if applicant_type=="salaried" else None,
                work_experience_years=float(work_exp),
                marital_status=marital,
                dependents=int(dependents),
                bank_relationship_years=int(bank_rel),
                residence_type=residence,
                years_at_address=int(years_at_addr),
                spouse_income_annual=float(spouse_inc),
                disposable_monthly_income=float(disposable),
                emi_nmi_ratio_percent=float(emi_nmi),
                repayment_type=repayment_type,
                itr_years_filed=int(itr_years),
                avg_balance_to_emi_ratio_percent=float(avg_bal_ratio),
                credit_history_score_choice=credit_hist,
                net_worth=float(net_worth) if net_worth else None,
                proposed_loan_amount=float(proposed),
                business_turnover_annual=float(biz_turnover) if biz_turnover else None,
                income_trend=income_trend,
                kyc_ok=bool(kyc_ok),
                payslips_ok=bool(payslips_ok),
                fraud_ok=bool(fraud_ok),
                bank_rel_ok=bool(bank_rel_ok),
                address_ok=bool(address_ok),
                visit_officer=visit_officer,
                visit_date=str(visit_date),
                visit_verified=bool(visit_verified),
                visit_remarks=visit_remarks
            )
            decision = eligibility_and_recommendation(applicant, base_rllr)
            show_decision_ui(applicant, decision)

if mode == "Bulk CSV":
    # Call bulk CSV section
    st.subheader("Bulk Upload (CSV)")
    st.markdown("CSV must contain columns (case-sensitive): name,applicant_type,age,gross_monthly_income,gross_annual_income,cibil_score,salary_account_with_bom,category,work_experience_years,marital_status,dependents,bank_relationship_years,residence_type,years_at_address,spouse_income_annual,disposable_monthly_income,emi_nmi_ratio_percent,repayment_type,itr_years_filed,avg_balance_to_emi_ratio_percent,credit_history_score_choice,net_worth,proposed_loan_amount,business_turnover_annual,income_trend,kyc_ok,payslips_ok,fraud_ok,bank_rel_ok,address_ok,visit_officer,visit_date,visit_verified,visit_remarks")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    example_csv = st.checkbox("Show example template / download sample CSV")
    if example_csv:
        sample = pd.DataFrame([{
            'name':'Rahul Sharma','applicant_type':'salaried','age':34,'gross_monthly_income':60000,'gross_annual_income':None,
            'cibil_score':790,'salary_account_with_bom':True,'category':'A','work_experience_years':6,'marital_status':'married',
            'dependents':1,'bank_relationship_years':4,'residence_type':'owned_non_metro','years_at_address':4,'spouse_income_annual':200000,
            'disposable_monthly_income':20000,'emi_nmi_ratio_percent':20,'repayment_type':'si_bom','itr_years_filed':3,'avg_balance_to_emi_ratio_percent':150,
            'credit_history_score_choice':'best_36m','net_worth':None,'proposed_loan_amount':800000,'business_turnover_annual':None,'income_trend':None,
            'kyc_ok':True,'payslips_ok':True,'fraud_ok':True,'bank_rel_ok':True,'address_ok':True,'visit_officer':'Officer A','visit_date':'2025-11-01','visit_verified':True,'visit_remarks':'OK'
        }])
        st.download_button("Download sample CSV", sample.to_csv(index=False), file_name="sample_applicants_with_checks.csv", mime="text/csv")
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        st.write(f"Uploaded {len(df)} rows")
        results = []
        annexures = []
        for idx, row in df.iterrows():
            try:
                applicant = Applicant(
                    name = row.get('name', f'row{idx}'),
                    applicant_type = row.get('applicant_type','salaried'),
                    age = int(row.get('age', 30)),
                    gross_monthly_income = float(row['gross_monthly_income']) if not pd.isna(row.get('gross_monthly_income')) else None,
                    gross_annual_income = float(row['gross_annual_income']) if not pd.isna(row.get('gross_annual_income')) else None,
                    cibil_score = int(row['cibil_score']) if not pd.isna(row.get('cibil_score')) else None,
                    salary_account_with_bom = bool(row.get('salary_account_with_bom', False)),
                    category = row.get('category'),
                    work_experience_years = float(row.get('work_experience_years',0)),
                    marital_status = row.get('marital_status'),
                    dependents = int(row.get('dependents',0)),
                    bank_relationship_years = int(row.get('bank_relationship_years',0)),
                    residence_type = row.get('residence_type'),
                    years_at_address = int(row.get('years_at_address',0)),
                    spouse_income_annual = float(row.get('spouse_income_annual',0)) if not pd.isna(row.get('spouse_income_annual')) else 0.0,
                    disposable_monthly_income = float(row.get('disposable_monthly_income',0)) if not pd.isna(row.get('disposable_monthly_income')) else 0.0,
                    emi_nmi_ratio_percent = float(row.get('emi_nmi_ratio_percent',0)) if not pd.isna(row.get('emi_nmi_ratio_percent')) else 0.0,
                    repayment_type = row.get('repayment_type','others'),
                    itr_years_filed = int(row.get('itr_years_filed',0)),
                    avg_balance_to_emi_ratio_percent = float(row.get('avg_balance_to_emi_ratio_percent',0)) if not pd.isna(row.get('avg_balance_to_emi_ratio_percent')) else 0.0,
                    credit_history_score_choice = row.get('credit_history_score_choice','best_36m'),
                    net_worth = float(row.get('net_worth')) if not pd.isna(row.get('net_worth')) else None,
                    proposed_loan_amount = float(row.get('proposed_loan_amount')) if not pd.isna(row.get('proposed_loan_amount')) else None,
                    business_turnover_annual = float(row.get('business_turnover_annual')) if not pd.isna(row.get('business_turnover_annual')) else None,
                    income_trend = row.get('income_trend'),
                    kyc_ok = bool(row.get('kyc_ok', False)),
                    payslips_ok = bool(row.get('payslips_ok', False)),
                    fraud_ok = bool(row.get('fraud_ok', False)),
                    bank_rel_ok = bool(row.get('bank_rel_ok', False)),
                    address_ok = bool(row.get('address_ok', False)),
                    visit_officer = row.get('visit_officer'),
                    visit_date = row.get('visit_date'),
                    visit_verified = bool(row.get('visit_verified', False)),
                    visit_remarks = row.get('visit_remarks')
                )
            except Exception as e:
                st.warning(f"Skipping row {idx} due to parsing error: {e}")
                continue
            dec = eligibility_and_recommendation(applicant, base_rllr)
            results.append({
                'name': applicant.name,
                'type': applicant.applicant_type,
                'score': dec.score,
                'grade': dec.grade,
                'eligible': dec.eligible,
                'reason': dec.reason,
                'recommended_loan': dec.recommended_loan,
                'tenure_months': dec.tenure_months,
                'annual_rate_percent': dec.annual_rate_percent,
                'emi': dec.emi
            })
            annexures.append(json.loads(generate_annexure_json(applicant, dec)))
        results_df = pd.DataFrame(results)
        st.dataframe(results_df)
        st.download_button("Download results CSV", results_df.to_csv(index=False), file_name="personal_loan_decisions.csv", mime="text/csv")
        st.download_button("Download annexures JSON (all)", json.dumps(annexures, indent=2), file_name="annexures_all.json", mime="application/json")

st.markdown("---")
st.caption("Reference implementation. Update RLLR/cutoffs/scoring if policy changes.")
