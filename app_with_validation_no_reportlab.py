# app_with_validation_no_reportlab.py
# Mahabank - Personal Loan Decision Tool (HTML-based sanction letter version)
# Generates sanction letter as HTML (print -> Save as PDF) with print settings panel
#
# Usage:
#   pip install streamlit pandas numpy
#   streamlit run app_with_validation_no_reportlab.py

import streamlit as st
import pandas as pd
import json
from dataclasses import dataclass
from typing import Optional, Dict, Tuple
from datetime import date
import html

st.set_page_config(page_title="Mahabank - Personal Loan Decision Tool (HTML)", layout="wide")

# ---------------------------
# Helper: EMI calculation
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
# Data models
# ---------------------------
@dataclass
class Applicant:
    name: str
    applicant_type: str
    age: int
    gross_monthly_income: Optional[float] = None
    cibil_score: Optional[int] = None
    kyc_ok: bool = False
    payslips_ok: bool = False
    fraud_ok: bool = False
    bank_rel_ok: bool = False
    address_ok: bool = False
    visit_verified: bool = False

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


# ---------------------------
# Generate sanction letter HTML (print to PDF)
# ---------------------------
def generate_sanction_letter_html(applicant: Applicant, decision: Decision) -> str:
    today = date.today().strftime("%d %B %Y")
    name = html.escape(applicant.name)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Sanction Letter - {name}</title>
    <style>
        body{{font-family:Arial;margin:40px;color:#111}}
        .header{{text-align:center}}
        h1{{font-size:18pt}}
        table{{width:100%;border-collapse:collapse;margin-top:20px}}
        td{{padding:6px 8px}}
    </style></head>
    <body>
        <div class='header'>
            <h1>BANK OF MAHARASHTRA</h1>
            <h3>Sanction Letter - Personal Loan Scheme</h3>
            <hr>
        </div>
        <p>Date: {today}</p>
        <p>To,<br><b>{name}</b><br>({applicant.applicant_type.capitalize()} Applicant)</p>
        <p><b>Subject:</b> Sanction of Personal Loan</p>
        <p>Dear {name.split()[0]},</p>
        <p>We are pleased to inform you that yo
