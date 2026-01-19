import streamlit as st
import requests
from tavily import TavilyClient
import PyPDF2
import io
import json
import re
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.colors import HexColor

st.set_page_config(
    page_title="Fact-Checking Web App",
    page_icon="🔍",
    layout="wide"
)

def init_clients():
    if 'clients_initialized' not in st.session_state:
        groq_key = st.secrets.get("GROQ_API_KEY", "")
        tavily_key = st.secrets.get("TAVILY_API_KEY", "")
        
        if not groq_key or not tavily_key:
            st.error("⚠️ API keys not configured. Please add them to Streamlit secrets.")
            st.stop()
        
        try:
            st.session_state.groq_api_key = groq_key
            st.session_state.tavily_client = TavilyClient(api_key=tavily_key)
            st.session_state.clients_initialized = True
        except Exception as e:
            st.error(f"Error initializing clients: {str(e)}")
            st.stop()

def call_groq_api(prompt, api_key):
    """Call Groq API directly using requests"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0,
        "max_tokens": 4000
    }
    
    response = requests.post(url, headers=headers, json=payload)
    
    if response.status_code == 200:
        return response.json()['choices'][0]['message']['content']
    else:
        st.error(f"Groq API error: {response.status_code} - {response.text}")
        return None

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF"""
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.read()))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_claims(text, api_key):
    """Use Groq to extract verifiable claims from text"""
    prompt = f"""Analyze this document and extract ALL verifiable factual claims. Focus on:
- Statistics and percentages (e.g., "grew by 25%", "unemployment at 3.5%", "GDP was -1.5%")
- Specific numerical data (revenue, costs, stock prices, GDP, market cap, rates)
- Technical specifications (speeds, capacities, dimensions)
- Factual statements about events (e.g., "economy entered recession", "market collapsed")
- Market data and rankings
- Growth rates and comparisons

IGNORE these (not verifiable claims):
- Relative date phrases without facts (e.g., "in the upcoming meeting", "last month", "recently")
- Opinions or predictions without data
- Vague statements without numbers or specifics

CRITICAL RULES:
- Extract the COMPLETE factual claim with numbers/specifics, NOT just date fragments
- If a sentence has "GDP was -1.5%" extract that, NOT "in 2025"
- If a sentence has "unemployment at 6.2%" extract that, NOT "has risen"
- Each claim must be independently verifiable against web sources

Good examples:
✓ "Real GDP growth for 2025 was -1.5%"
✓ "Unemployment rate is 6.2%"
✓ "Tesla stock price is $250"
✓ "iPhone 15 costs $799"
✗ "in the upcoming February meeting" (no fact to verify)
✗ "recently announced" (vague, no specifics)
✗ "last quarter" (just a timeframe, no data)

For each claim, extract:
1. The exact claim text with the number/fact (verbatim quote)
2. The type: statistic|financial|technical|factual_statement|comparison
3. Brief context for verification

Return ONLY valid JSON array, no markdown:
[
  {{
    "claim": "exact quoted factual claim from document with numbers",
    "type": "statistic|financial|technical|factual_statement|comparison",
    "context": "what this claim is about"
  }}
]

Document:
{text[:8000]}"""

    response_text = call_groq_api(prompt, api_key)
    if not response_text:
        return []
    
    response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
    
    try:
        claims = json.loads(response_text)
        return claims
    except json.JSONDecodeError as e:
        st.error(f"Error parsing claims: {e}")
        st.code(response_text)
        return []

def search_claim(claim_text, context, tavily):
    """Search the web for information about a claim"""
    query = f"{claim_text} {context}"
    try:
        response = tavily.search(
            query, 
            max_results=8,
            search_depth="advanced",
            include_raw_content=False
        )
        return response.get('results', [])
    except Exception as e:
        st.warning(f"Search error: {e}")
        return []

def verify_claim(claim, search_results, api_key):
    """Use Groq to verify claim against search results"""
    results_text = "\n\n".join([
        f"Source {i+1}: {r.get('url', 'N/A')}\nTitle: {r.get('title', 'N/A')}\nContent: {r.get('content', 'N/A')[:800]}"
        for i, r in enumerate(search_results[:8])
    ])
    
    prompt = f"""You are a precise fact-checker. Verify this claim against current web data with STRICT CONSISTENCY.

CLAIM: "{claim['claim']}"
TYPE: {claim['type']}
CONTEXT: {claim['context']}

SEARCH RESULTS FROM WEB:
{results_text}

VERIFICATION RULES (FOLLOW EXACTLY):
1. VERIFIED = Claim matches current authoritative sources EXACTLY (numbers within ±2% margin for statistics)
2. INACCURATE = Claim WAS accurate historically but is now outdated/changed
3. FALSE = Claim was NEVER accurate or is fabricated

DECISION PROCESS:
Step 1: Extract the specific number/date/fact from the claim
Step 2: Find the MOST RECENT and AUTHORITATIVE source mentioning this
Step 3: Compare exactly - do the numbers match within 2% margin?
Step 4: If numbers don't match, was the claim EVER true? → If yes: INACCURATE, If no: FALSE

CRITICAL RULES FOR CONSISTENCY:
- For financial claims: Use ONLY data from last 6 months unless claim specifies historical date
- For statistics: If multiple sources agree on a number, use that consensus
- For dates: Exact date match required for VERIFIED
- If sources conflict: Mark INACCURATE and cite the most authoritative source
- NEVER guess - if sources don't provide clear answer, mark as FALSE with low confidence

EXAMPLES FOR CALIBRATION:
- Claim: "Bitcoin is $45K" | Current: $43K → INACCURATE (was never exactly $45K, but close)
- Claim: "Bitcoin reached $100K in 2024" | Never happened → FALSE
- Claim: "GPT-4 released in March 2023" | Actually March 2023 → VERIFIED
- Claim: "Company revenue $500M in 2023" | Actually $480M → INACCURATE (wrong number, right timeframe)

YOUR RESPONSE MUST BE DETERMINISTIC - same claim + same sources = same verdict.

Return ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "status": "verified|inaccurate|false",
  "explanation": "State the specific number from claim, specific number from sources, and why they match/don't match",
  "correct_info": "The actual current/correct figure with source",
  "confidence": "high|medium|low",
  "sources": ["url1", "url2"]
}}"""

    response_text = call_groq_api(prompt, api_key)
    if not response_text:
        return {
            "status": "error",
            "explanation": "Could not verify claim",
            "correct_info": "",
            "confidence": "low",
            "sources": []
        }
    
    response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
    
    try:
        result = json.loads(response_text)
        if 'confidence' not in result:
            result['confidence'] = 'medium'
        return result
    except json.JSONDecodeError:
        return {
            "status": "error",
            "explanation": "Could not verify claim",
            "correct_info": "",
            "confidence": "low",
            "sources": []
        }

def generate_pdf_report(results):
    """Generate PDF report from results"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=HexColor('#1f1f1f'),
        spaceAfter=30,
        alignment=1
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        spaceAfter=6
    )
    
    story = []
    
    story.append(Paragraph("Fact-Checking Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", body_style))
    story.append(Spacer(1, 0.3*inch))
    
    verified = sum(1 for r in results if r['status'] == 'verified')
    inaccurate = sum(1 for r in results if r['status'] == 'inaccurate')
    false = sum(1 for r in results if r['status'] == 'false')
    
    story.append(Paragraph("Summary", heading_style))
    story.append(Paragraph(f"Total Claims: {len(results)}", body_style))
    story.append(Paragraph(f"Verified: {verified}", body_style))
    story.append(Paragraph(f"Inaccurate: {inaccurate}", body_style))
    story.append(Paragraph(f"False: {false}", body_style))
    story.append(Spacer(1, 0.3*inch))
    
    story.append(Paragraph("Detailed Results", heading_style))
    story.append(Spacer(1, 0.2*inch))
    
    for idx, result in enumerate(results):
        status_emoji = {"verified": "✓", "inaccurate": "⚠", "false": "✗"}.get(result['status'], "?")
        
        story.append(Paragraph(f"<b>Claim #{idx + 1}: {status_emoji} {result['status'].upper()}</b>", heading_style))
        story.append(Paragraph(f"<b>Claim:</b> {result['claim']}", body_style))
        story.append(Paragraph(f"<b>Type:</b> {result['type']} | <b>Confidence:</b> {result.get('confidence', 'N/A').upper()}", body_style))
        story.append(Paragraph(f"<b>Explanation:</b> {result['explanation']}", body_style))
        
        if result.get('correct_info'):
            story.append(Paragraph(f"<b>Correct Information:</b> {result['correct_info']}", body_style))
        
        if result.get('sources'):
            story.append(Paragraph(f"<b>Sources:</b>", body_style))
            for source in result['sources'][:3]:
                story.append(Paragraph(f"• {source}", body_style))
        
        story.append(Spacer(1, 0.2*inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def main():
    init_clients()
    
    st.title("🔍 Fact-Checking Web App")
    st.markdown("Upload a PDF to automatically verify claims against live web data")
    
    with st.sidebar:
        st.header("About")
        st.markdown("""
        This tool:
        1. **Extracts** verifiable claims from PDFs
        2. **Searches** live web data
        3. **Verifies** accuracy and flags issues
        
        **Status Legend:**
        - 🟢 **Verified**: Matches current data
        - 🟡 **Inaccurate**: Outdated or partially wrong
        - 🔴 **False**: No evidence or contradicted
        """)
        
        st.markdown("---")
        st.markdown(f"**Current Date**: {datetime.now().strftime('%B %d, %Y')}")
        st.markdown("**Powered by**: Groq (Llama 3.3) + Tavily Search")
    
    uploaded_file = st.file_uploader("Upload PDF Document", type=['pdf'])
    
    if uploaded_file:
        with st.spinner("📄 Extracting text from PDF..."):
            text = extract_text_from_pdf(uploaded_file)
            st.success(f"✅ Extracted {len(text)} characters from PDF")
        
        with st.expander("📖 Document Preview"):
            st.text(text[:1000] + "..." if len(text) > 1000 else text)
        
        if st.button("🚀 Start Fact-Checking", type="primary"):
            with st.spinner("🔎 Extracting claims..."):
                claims = extract_claims(text, st.session_state.groq_api_key)
            
            if not claims:
                st.warning("No verifiable claims found in document")
                return
            
            st.success(f"✅ Found {len(claims)} claims to verify")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            results = []
            for idx, claim in enumerate(claims):
                status_text.text(f"Verifying claim {idx + 1}/{len(claims)}: {claim['claim'][:60]}...")
                
                search_results = search_claim(claim['claim'], claim['context'], st.session_state.tavily_client)
                
                verification = verify_claim(claim, search_results, st.session_state.groq_api_key)
                
                results.append({
                    **claim,
                    **verification
                })
                
                progress_bar.progress((idx + 1) / len(claims))
            
            status_text.empty()
            progress_bar.empty()
            
            st.header("📊 Verification Results")
            
            verified = sum(1 for r in results if r['status'] == 'verified')
            inaccurate = sum(1 for r in results if r['status'] == 'inaccurate')
            false = sum(1 for r in results if r['status'] == 'false')
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Claims", len(results))
            col2.metric("🟢 Verified", verified)
            col3.metric("🟡 Inaccurate", inaccurate)
            col4.metric("🔴 False", false)
            
            accuracy_rate = (verified / len(results) * 100) if len(results) > 0 else 0
            issue_rate = ((inaccurate + false) / len(results) * 100) if len(results) > 0 else 0
            
            st.markdown("---")
            
            if accuracy_rate < 20:
                st.error(f"🚨 **Critical Issues Found**: Only {accuracy_rate:.1f}% of claims verified. {issue_rate:.1f}% require attention. This document needs significant review before publication.")
            elif accuracy_rate < 50:
                st.warning(f"⚠️ **Multiple Issues Found**: {accuracy_rate:.1f}% verified, {issue_rate:.1f}% flagged. Review recommended before publication.")
            elif accuracy_rate < 80:
                st.info(f"ℹ️ **Some Issues Found**: {accuracy_rate:.1f}% verified, {issue_rate:.1f}% flagged. Minor corrections needed.")
            else:
                st.success(f"✅ **Document Looks Good**: {accuracy_rate:.1f}% of claims verified. Ready for publication with minor review.")
            
            st.markdown("---")
            
            for idx, result in enumerate(results):
                status = result['status']
                
                if status == 'verified':
                    emoji = "🟢"
                elif status == 'inaccurate':
                    emoji = "🟡"
                else:
                    emoji = "🔴"
                
                with st.container():
                    st.markdown(f"### {emoji} Claim #{idx + 1}: {status.upper()}")
                    
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.markdown(f"**Claim:** _{result['claim']}_")
                        st.markdown(f"**Type:** `{result['type']}` | **Confidence:** `{result.get('confidence', 'N/A').upper()}`")
                        st.markdown(f"**Explanation:** {result['explanation']}")
                        
                        if result.get('correct_info'):
                            st.markdown(f"**✓ Correct Information:** {result['correct_info']}")
                    
                    with col2:
                        if result.get('sources'):
                            st.markdown("**Sources:**")
                            for source in result['sources'][:3]:
                                st.markdown(f"- [{source[:50]}...]({source})")
                    
                    st.markdown("---")
            
            pdf_buffer = generate_pdf_report(results)
            st.download_button(
                label="📥 Download Full Report (PDF)",
                data=pdf_buffer,
                file_name=f"fact_check_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf"
            )

if __name__ == "__main__":
    main()