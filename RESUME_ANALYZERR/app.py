import streamlit as st
import pdf2image
import pytesseract
from PIL import Image
import os
import json
import re
from groq import Groq
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter

# -------------------- CONFIG --------------------
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# -------------------- HELPERS --------------------
def extract_text_from_pdf(pdf_file):
    pages = pdf2image.convert_from_bytes(pdf_file.read())
    return "\n".join(pytesseract.image_to_string(p) for p in pages)

def extract_json(text):
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        return json.loads(match.group()) if match else None
    except:
        return None

def safe_groq_call(messages, temperature=0.1):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=temperature
    )
    return response.choices[0].message.content

# -------------------- AI: FULL ATS ANALYSIS --------------------
def groq_full_analysis(resume_text, jd_text):
    system_prompt = (
        "Return ONLY JSON:\n"
        "{"
        '"ats_score":0,'
        '"ats_summary":"",'
        '"improvements":[],'
        '"skills_found":[],'
        '"skills_missing":[],'
        '"strengths":[],'
        '"weaknesses":[],'
        '"resume_rewrite":""'
        "}"
    )

    user_prompt = f"""
Resume:
{resume_text}

Job Description:
{jd_text}
"""

    try:
        raw = safe_groq_call([
            {"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt}
        ], temperature=0.05)

        return extract_json(raw) or {}
    except:
        return {}

# -------------------- AI: SUMMARY --------------------
def groq_summary(resume_text, jd_text):
    prompt = f"""
Write one paragraph comparing resume and job description.

Resume:
{resume_text}

Job Description:
{jd_text}
"""
    return safe_groq_call([{"role":"user","content":prompt}], temperature=0.3)

# -------------------- AI: ATS EXPLANATION --------------------
def groq_ats_explanation(resume_text, jd_text, score):
    prompt = f"""
Explain why ATS score is {score}% in simple English.

Resume:
{resume_text}

Job Description:
{jd_text}
"""
    return safe_groq_call([{"role":"user","content":prompt}], temperature=0.2)

# -------------------- AI: CAREER RECOMMENDATIONS --------------------
def groq_career_recommendation(resume_text, jd_text):
    system_prompt = (
        "Return ONLY JSON with keys: "
        "recommended_roles (list), why_fit (string), "
        "skills_to_improve (list), resume_upgrade_tips (list)"
    )

    user_prompt = f"""
Resume:
{resume_text}

Job Description:
{jd_text}
"""

    try:
        raw = safe_groq_call([
            {"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt}
        ], temperature=0.05)

        return extract_json(raw) or {}
    except:
        return {}

# -------------------- PDF REPORT --------------------
def generate_pdf_report(data):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate("ATS_Report.pdf", pagesize=letter)
    story = []

    story.append(Paragraph("ATS Resume Analysis Report", styles["Heading1"]))
    story.append(Spacer(1,10))
    story.append(Paragraph(f"ATS Score: {data.get('ats_score',0)}%", styles["Normal"]))
    story.append(Spacer(1,10))

    for section in ["skills_found","skills_missing","strengths","weaknesses","improvements"]:
        story.append(Paragraph(section.replace("_"," ").title(), styles["Heading3"]))
        for item in data.get(section,[]):
            story.append(Paragraph(f"- {item}", styles["Normal"]))
        story.append(Spacer(1,8))

    doc.build(story)
    with open("ATS_Report.pdf","rb") as f:
        return f.read()

# -------------------- STREAMLIT UI --------------------
st.set_page_config("Bhaskar AI Resume Analyzer", layout="wide")
st.title("📄 Bhaskar's AI Resume Analyzer")

with st.sidebar:
    jd_text = st.text_area("Paste Job Description", height=200)
    uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])
    analyze = st.button("Analyze Resume")

if analyze:
    if not uploaded_file or not jd_text.strip():
        st.error("Please upload resume and job description")
    else:
        resume_text = extract_text_from_pdf(uploaded_file)

        ats = groq_full_analysis(resume_text, jd_text)
        score = max(0, min(100, int(ats.get("ats_score",0))))

        rating = (
            "🌟 Excellent Match" if score>=85 else
            "✅ Strong Match" if score>=70 else
            "⚠ Average Match" if score>=50 else
            "❌ Weak Match"
        )

        st.subheader("🧠 ATS Score")
        st.progress(score)
        st.markdown(f"{score}% — {rating}")

        st.subheader("📌 ATS Score Explanation")
        st.info(groq_ats_explanation(resume_text, jd_text, score))

        st.subheader("📝 AI Summary")
        st.info(groq_summary(resume_text, jd_text))

        with st.expander("✔ Skills / ❌ Missing / 💪 Strengths / ⚠ Weaknesses", expanded=True):
            st.success("Skills Found: " + ", ".join(ats.get("skills_found",[])))
            st.error("Missing Skills: " + ", ".join(ats.get("skills_missing",[])))

            st.subheader("Strengths")
            for s in ats.get("strengths",[]): st.success(s)

            st.subheader("Weaknesses")
            for w in ats.get("weaknesses",[]): st.warning(w)

        # ✍ RESUME REWRITE
        with st.expander("✍ AI Resume Rewrite (ATS-friendly)", expanded=False):
            rewrite = ats.get("resume_rewrite","")
            st.text_area("Rewritten Resume", rewrite, height=300)
            st.download_button("Download Rewritten Resume", rewrite, "rewritten_resume.txt")

        # 🎯 CAREER RECOMMENDATIONS
        career = groq_career_recommendation(resume_text, jd_text)

        with st.expander("🎯 AI Career Fit Recommendations", expanded=True):
            st.subheader("Recommended Roles")
            for r in career.get("recommended_roles",[]): st.success(r)

            st.subheader("Why you fit")
            st.info(career.get("why_fit",""))

            st.subheader("Skills to improve")
            for s in career.get("skills_to_improve",[]): st.warning(s)

            st.subheader("Resume upgrade tips")
            for t in career.get("resume_upgrade_tips",[]): st.info(t)

        pdf = generate_pdf_report(ats)
        st.download_button("📥 Download ATS PDF Report", pdf, "ATS_Report.pdf")
