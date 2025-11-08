# app.py
"""
Streamlit Personal Loan Decision App
Implements Mahabank Personal Loan decision model from the uploaded master circular.
Save as `app.py` and run:
    pip install streamlit pandas numpy
    streamlit run app.py

User inputs current RLLR (base rate). The app supports single applicant entry and CSV bulk upload.
"""

import streamlit as st
import pandas as pd
import math
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple

st.set_page_config(page_title="Mahabank - Personal Loan Decision Tool", layout="wide")

# ---------------------------
# Helper financial functions
# ---------------------------
def emi_amount(principal: float, annual_rate_percent: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_percent / 100.0 / 12.0
    if r == 0:
        return principal / months
    emi = principal * r * (1 + r) ** months / ((1 + r) ** months - 1)
    return emi

# ---------------------------
# Dataclasses
# ---------------------------
@dataclass
class Applicant:
    name: str
    applicant_type: str  # 'salaried' or 'professional'
    age: int
    gross_monthly_income: Optional[float] = None
    gross_annual_income: Optional[float] = None
    cibil_score: Optional[int] = None
    salary_account_with_bom: bool = False
    category: Optional[str] = None  # 'A','B','C'
    work_experience_years: Optional[float] = 0
    marital_status: Optional[str] = None
    dependents: Optional[int] = 0
    bank_relationship_years: Optional[int] = 0
    residence_type: Optional[str] = None
    years_at_address: Optional[int] = 0
    spouse_income_annual: Optional[float] = 0.0
    disposable_monthly_income: Optional[float] = 0.0
    emi_nmi_ratio_percent: Optional[float] = None
    repayment_type: Optional[str] = None
    itr_years_filed: Optional[int] = 0
    avg_balance_to_emi_ratio_percent: Optional[float] = None
    credit_history_score_choice: Optional[str] = None
    # professional
    net_worth: Optional[float] = None
    proposed_loan_amount: Optional[float] = None
    business_turnover_annual: Optional[float] = None
    income_trend: Optional[str] = None

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

# ---------------------------
# Scoring helpers (compact)
# ---------------------------
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

# Professional
PROF_NETWORTH_SCORE = lambda ratio: 0 if ratio<0.5 else (3 if ratio<0.75 else 5)
PROF_INCOME_TREND_SCORE = {'increasing':5, 'stable':2, 'unstable':1, 'decreasing':0}
PROF_TURNOVER_SCORE = lambda t: 1 if t<50e5 else (2 if t<80e5 else (3 if t<120e5 else (4 if t<400e5 else 5)))
PROF_ITR_SCORE = lambda yrs: 5 if yrs>=5 else (4 if yrs>=3 else (3 if yrs>=2 else 0))

# ---------------------------
# Rate tables (extracted mapping)
# ---------------------------
RATE_TABLE_SALARIED = {
    ('A','bom',800):0.70, ('A','bom',776):1.00, ('A','bom',750):1.50, ('A','bom',700):2.00, ('A','bom','ntc'):1.70,
    ('A','other',800):1.50, ('A','other',776):2.00, ('A','other',750):2.50, ('A','other',700):3.00, ('A','other','ntc'):2.75,
    ('B','bom',800):1.50, ('B','bom',776):2.00, ('B','bom',750):2.50, ('B','bom',700):3.00, ('B','bom','ntc'):2.75,
    ('B','other',800):1.90, ('B','other',776):2.50, ('B','other',750):3.00, ('B','other',700):3.50, ('B','other','ntc'):3.25,
    ('C','other',800):1.90, ('C','other',776):2.45, ('C','other',750):2.95, ('C','other',700):3.45, ('C','other','ntc'):3.25
}
RATE_TABLE_PROF = {800:2.00, 776:2.50, 750:3.00, 700:3.50, 'ntc':2.75}

# ---------------------------
# Scoring functions
# ---------------------------
def compute_score_salaried(app: Applicant) -> Tuple[float,int]:
    score = 0.0
    # base academic default
    score += 3
    # employment type default (not in form) -> team can extend
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
    score += MARITAL_SCORE.get((app.marital_status or 'single').lower(),3)
    score += AGE_SCORE(app.age or 0)
    score += DEPENDENT_SCORE(app.dependents or 0)
    score += BANK_REL_SCORE(app.bank_relationship_years or 0)
    score += RESIDENCE_SCORE.get((app.residence_type or 'rented'),1)
    score += YEARS_AT_ADDRESS_SCORE(app.years_at_address or 0)
    score += SPOUSE_INCOME_SCORE(app.spouse_income_annual or 0)
    score += DISPOSABLE_INCOME_SCORE(app.disposable_monthly_income or 0)
    score += EMI_NMI_SCORE(app.emi_nmi_ratio_percent or 0)
    score += REPAYMENT_TYPE_SCORE.get((app.repayment_type or 'others'),0)
    score += ITR_SCORE(app.itr_years_filed or 0)
    score += AVG_BALANCE_SCORE(app.avg_balance_to_emi_ratio_percent or 0)
    score += CIBIL_SCORE_SCORE(app.cibil_score or 0)
    score += CREDIT_HISTORY_MAP.get((app.credit_history_score_choice or 'best_36m'),10)
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
    score += MARITAL_SCORE.get((app.marital_status or 'single').lower(),3)
    score += AGE_SCORE(app.age or 0)
    score += BANK_REL_SCORE(app.bank_relationship_years or 0) * (10/5)
    score += RESIDENCE_SCORE.get((app.residence_type or 'rented'),1)
    score += YEARS_AT_ADDRESS_SCORE(app.years_at_address or 0)
    score += DISPOSABLE_INCOME_SCORE(app.disposable_monthly_income or 0)
    score += EMI_NMI_SCORE(app.emi_nmi_ratio_percent or 0)
    if app.proposed_loan_amount and app.net_worth is not None and app.proposed_loan_amount>0:
        ratio = app.net_worth / app.proposed_loan_amount
    else:
        ratio = 0.0
    score += PROF_NETWORTH_SCORE(ratio)
    score += PROF_INCOME_TREND_SCORE.get((app.income_trend or 'stable'),2)
    score += PROF_TURNOVER_SCORE(app.business_turnover_annual or 0)
    score += PROF_ITR_SCORE(app.itr_years_filed or 0)
    score += AVG_BALANCE_SCORE(app.avg_balance_to_emi_ratio_percent or 0)
    score += CIBIL_SCORE_SCORE(app.cibil_score or 0)
    score += CREDIT_HISTORY_MAP.get((app.credit_history_score_choice or 'best_36m'),10)
    score = min(score, 100)
    grade = 1 if score>80 else (2 if score>=71 else (3 if score>=61 else (4 if score>=50 else 5)))
    return score, grade

# ---------------------------
# Rate selection
# ---------------------------
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
        spread = RATE_TABLE_SALARIED.get(key)
        if spread is None:
            spread = 3.5
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

# ---------------------------
# Eligibility & recommendation
# ---------------------------
def eligibility_and_recommendation(app: Applicant, base_rllr_percent: float) -> Decision:
    if app.applicant_type not in ('salaried','professional'):
        return Decision(False, "Applicant type must be 'salaried' or 'professional'")
    # CIBIL check - circular uses 700 cutoff (we allow None to proceed with caution)
    if (app.cibil_score is not None) and (app.cibil_score < 700):
        return Decision(False, f"CIBIL score below minimum cut-off 700 (CIBIL={app.cibil_score})")
    # Age checks for salaried
    if app.applicant_type == 'salaried':
        if app.age < 21 or app.age > 58:
            return Decision(False, f"Age not within permissible range for salaried (21-58). Age={app.age}")
    # compute score
    if app.applicant_type == 'salaried':
        score, grade = compute_score_salaried(app)
    else:
        score, grade = compute_score_professional(app)
    # determine eligible amount
    if app.applicant_type == 'salaried':
        gm = app.gross_monthly_income or 0
        eligible_by_income = 20 * gm
        max_limit = 20_00_000
        eligible_amount = min(eligible_by_income, max_limit)
        if app.category == 'A' and app.salary_account_with_bom:
            tenure_months = 84
        else:
            tenure_months = 60
        ded_limit_pct = 65 if app.category == 'A' else 60
    else:
        ga = app.gross_annual_income or 0
        eligible_amount = min(1.5 * ga, 20_00_000)
        tenure_months = 60
        ded_limit_pct = 60
    proposed = app.proposed_loan_amount or eligible_amount
    annual_rate = determine_interest_rate(app, base_rllr_percent)
    emi = emi_amount(proposed, annual_rate, tenure_months)
    gross_monthly = app.gross_monthly_income or (app.gross_annual_income/12 if app.gross_annual_income else 0)
    if gross_monthly <= 0:
        return Decision(False, "Insufficient income data to compute eligibility", details={'score':score,'grade':grade})
    proposed_emi_pct = (emi / gross_monthly) * 100
    if proposed_emi_pct > ded_limit_pct:
        return Decision(False, f"Proposed EMI {emi:.2f} (={proposed_emi_pct:.2f}% of gross monthly) exceeds allowed deduction norm of {ded_limit_pct}%.", details={'score':score,'grade':grade,'proposed_emi_pct':proposed_emi_pct})
    if proposed > eligible_amount:
        recommended = eligible_amount
        rec_emi = emi_amount(recommended, annual_rate, tenure_months)
    else:
        recommended = proposed
        rec_emi = emi
    decision_flag = True if grade <= 3 else False
    reason = "Clear sanction" if grade==1 else ("Sanction with normal authority" if grade in (2,3) else "Requires higher authority/decline")
    return Decision(decision_flag, reason, recommended_loan=recommended, tenure_months=tenure_months, annual_rate_percent=annual_rate, emi=rec_emi, score=score, grade=grade, details={
        'proposed':proposed,
        'eligible_by_income':eligible_amount,
        'proposed_emi_pct': proposed_emi_pct
    })

# ---------------------------
# UI / App layout
# ---------------------------
st.title("Mahabank — Personal Loan Decision Tool")
st.markdown("""
This app implements the Personal Loan rules from the Mahabank Master Circular (Annexure scoring, deduction norms, rate mapping).
- Provide the current **RLLR** (base rate) used by the bank — app computes Annual Rate = RLLR + spread.
- Choose **Single Applicant** to evaluate one case, or **Bulk CSV** to score many applicants.
""")

# Sidebar: global settings
st.sidebar.header("Settings")
base_rllr = st.sidebar.number_input("Current RLLR (base rate %) — enter numeric", value=10.15, step=0.01, format="%.2f")
st.sidebar.write("CIBIL cutoff used: 700 (per circular).")

mode = st.radio("Mode", ["Single Applicant", "Bulk CSV"])

# ---------------------------
# Single Applicant form
# ---------------------------
def single_app_form():
    with st.form("app_form", clear_on_submit=False):
        st.subheader("Applicant Information")
        col1, col2 = st.columns([2,2])
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
        st.markdown("**Other / risk parameters (help model accuracy)**")
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
        # professional-only fields
        net_worth = None
        biz_turnover = None
        income_trend = None
        if applicant_type == "professional":
            st.markdown("**Professional-specific fields**")
            colp1, colp2 = st.columns(2)
            with colp1:
                net_worth = st.number_input("Net Worth (₹)", min_value=0.0, value=1000000.0, step=10000.0, format="%.2f")
                biz_turnover = st.number_input("Annual turnover (₹)", min_value=0.0, value=2000000.0, step=10000.0, format="%.2f")
            with colp2:
                income_trend = st.selectbox("Income trend", ["increasing","stable","unstable","decreasing"])
        submit = st.form_submit_button("Evaluate Applicant")
        if submit:
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
                income_trend=income_trend
            )
            decision = eligibility_and_recommendation(applicant, base_rllr)
            # show result
            st.success("Decision computed")
            show_decision_ui(applicant, decision)

# ---------------------------
# Bulk CSV processing
# ---------------------------
def bulk_csv_processor():
    st.subheader("Bulk Upload (CSV)")
    st.markdown("CSV must contain columns matching these field names (case-sensitive):\n"
                "`name,applicant_type,age,gross_monthly_income,gross_annual_income,cibil_score,salary_account_with_bom,category,work_experience_years,marital_status,dependents,bank_relationship_years,residence_type,years_at_address,spouse_income_annual,disposable_monthly_income,emi_nmi_ratio_percent,repayment_type,itr_years_filed,avg_balance_to_emi_ratio_percent,credit_history_score_choice,net_worth,proposed_loan_amount,business_turnover_annual,income_trend`")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    example_csv = st.checkbox("Show example template / download sample CSV")
    if example_csv:
        sample = pd.DataFrame([{
            'name':'Rahul Sharma','applicant_type':'salaried','age':34,'gross_monthly_income':60000,'gross_annual_income':None,
            'cibil_score':790,'salary_account_with_bom':True,'category':'A','work_experience_years':6,'marital_status':'married',
            'dependents':1,'bank_relationship_years':4,'residence_type':'owned_non_metro','years_at_address':4,'spouse_income_annual':200000,
            'disposable_monthly_income':20000,'emi_nmi_ratio_percent':20,'repayment_type':'si_bom','itr_years_filed':3,'avg_balance_to_emi_ratio_percent':150,
            'credit_history_score_choice':'best_36m','net_worth':None,'proposed_loan_amount':800000,'business_turnover_annual':None,'income_trend':None
        }])
        st.download_button("Download sample CSV", sample.to_csv(index=False), file_name="sample_applicants.csv", mime="text/csv")
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        st.write(f"Uploaded {len(df)} rows")
        # Process each row
        results = []
        for idx, row in df.iterrows():
            # safe conversions / defaults
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
                    income_trend = row.get('income_trend')
                )
            except Exception as e:
                st.warning(f"Skipping row {idx} due to parsing error: {e}")
                continue
            dec = eligibility_and_recommendation(applicant, base_rllr)
            r = {
                'name': applicant.name,
                'applicant_type': applicant.applicant_type,
                'score': dec.score,
                'grade': dec.grade,
                'eligible': dec.eligible,
                'reason': dec.reason,
                'recommended_loan': dec.recommended_loan,
                'tenure_months': dec.tenure_months,
                'annual_rate_percent': dec.annual_rate_percent,
                'emi': dec.emi
            }
            # merge details if present
            if dec.details:
                for k,v in dec.details.items():
                    r[k] = v
            results.append(r)
        results_df = pd.DataFrame(results)
        st.dataframe(results_df)
        csv_result = results_df.to_csv(index=False)
        st.download_button("Download results CSV", csv_result, file_name="personal_loan_decisions.csv", mime="text/csv")
        st.download_button("Download results JSON", results_df.to_json(orient='records'), file_name="personal_loan_decisions.json", mime="application/json")

# ---------------------------
# Decision UI rendering
# ---------------------------
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
        st.write(f"**Score:** {decision.score:.1f}   |   **Grade:** {decision.grade}")
        st.write(f"**Recommended loan (₹):** {decision.recommended_loan:,.2f}")
        st.write(f"**Tenure (months):** {decision.tenure_months}")
        st.write(f"**Interest rate (annual %):** {decision.annual_rate_percent:.3f}")
        st.write(f"**EMI (₹):** {decision.emi:,.2f}")
        if decision.details:
            st.write("**Details / checks:**")
            st.json(decision.details)
    # download sanction summary
    summary = {
        'name': applicant.name,
        'eligible': decision.eligible,
        'reason': decision.reason,
        'score': decision.score,
        'grade': decision.grade,
        'recommended_loan': decision.recommended_loan,
        'tenure_months': decision.tenure_months,
        'annual_rate_percent': decision.annual_rate_percent,
        'emi': decision.emi
    }
    st.download_button("Download sanction summary (JSON)", pd.Series(summary).to_json(), file_name=f"sanction_{applicant.name.replace(' ','_')}.json", mime="application/json")

# ---------------------------
# Main mode switch
# ---------------------------
if mode == "Single Applicant":
    single_app_form()
else:
    bulk_csv_processor()

st.markdown("---")
st.caption("Model implements rules & scoring from Mahabank Master Circular (Personal Loan). Use current RLLR provided by operations; adjust RLLR and policy cutoffs in code if circular changes.")
