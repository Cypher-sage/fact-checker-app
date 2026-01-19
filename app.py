import streamlit as st
import requests
from tavily import TavilyClient
import PyPDF2
import io
import json
import re
import time
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.colors import HexColor

st.set_page_config(
    page_title="Fact-Checking Web App",
    page_icon="🔍",
    layout="wide"
)

def init_clients():
    """Initialize API clients in session state"""
    if 'clients_initialized' not in st.session_state:
        groq_key = st.secrets.get("GROQ_API_KEY", "")
        tavily_key = st.secrets.get("TAVILY_API_KEY", "")
        
        if not groq_key or not tavily_key:
            st.error("⚠️ API keys not configured. Please add them to Streamlit secrets.")
            st.stop()
        
        st.session_state.groq_api_key = groq_key
        st.session_state.tavily_client = TavilyClient(api_key=tavily_key)
        st.session_state.clients_initialized = True

def call_groq_api(prompt, api_key, model="llama-3.1-8b-instant", max_retries=3):
    """Call Groq API with retry logic and rate limit handling"""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 4000
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            elif response.status_code == 429:
                wait_time = min((attempt + 1) * 15, 60)
                st.warning(f"⏳ Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                st.error(f"API error {response.status_code}: {response.text[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return None
        except requests.exceptions.Timeout:
            st.warning(f"Request timeout. Retry {attempt + 1}/{max_retries}...")
            time.sleep(5)
        except Exception as e:
            st.error(f"Error: {str(e)[:200]}")
            if attempt < max_retries - 1:
                time.sleep(5)
            else:
                return None
    
    return None

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        st.error(f"PDF extraction error: {str(e)}")
        return ""

def extract_claims(text, api_key):
    """Extract verifiable claims from text using Groq API"""
    prompt = f"""Extract ALL verifiable factual claims from this document. Focus on:
- Statistics with numbers (e.g., "GDP was -1.5%", "unemployment at 6.2%")
- Financial data (stock prices, revenue, costs)
- Technical specs (speeds, capacities)
- Factual events (e.g., "economy entered recession")

IGNORE: vague statements, opinions, predictions without data, date-only phrases.

Return ONLY a JSON array (no markdown):
[
  {{
    "claim": "exact factual claim with numbers from document",
    "type": "statistic|financial|technical|factual_statement",
    "context": "brief context for verification"
  }}
]

Document (first 6000 chars):
{text[:6000]}"""

    response = call_groq_api(prompt, api_key)
    if not response:
        return []
    
    response = re.sub(r'```json\s*|\s*```', '', response).strip()
    
    try:
        claims = json.loads(response)
        return claims if isinstance(claims, list) else []
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse claims: {str(e)[:100]}")
        return []

def search_claim(claim_text, context, tavily_client):
    """Search web for claim information"""
    query = f"{claim_text} {context}"
    try:
        response = tavily_client.search(
            query, 
            max_results=6,
            search_depth="basic",
            include_raw_content=False
        )
        return response.get('results', [])
    except Exception as e:
        st.warning(f"Search error: {str(e)[:100]}")
        return []

def verify_claim(claim, search_results, api_key):
    """Verify claim against search results"""
    if not search_results:
        return {
            "status": "error",
            "explanation": "No search results available",
            "correct_info": "",
            "confidence": "low",
            "sources": []
        }
    
    results_text = "\n\n".join([
        f"Source {i+1}: {r.get('title', 'N/A')}\n{r.get('content', 'N/A')[:600]}"
        for i, r in enumerate(search_results[:5])
    ])
    
    prompt = f"""Verify this claim against web search results.

CLAIM: "{claim['claim']}"
TYPE: {claim['type']}

SEARCH RESULTS:
{results_text}

RULES:
1. VERIFIED = Claim matches current sources (±2% for numbers)
2. INACCURATE = Was true but now outdated/changed
3. FALSE = Never accurate or fabricated

Return ONLY JSON (no markdown):
{{
  "status": "verified|inaccurate|false",
  "explanation": "Why claim matches/doesn't match sources",
  "correct_info": "Current correct information if different",
  "confidence": "high|medium|low",
  "sources": ["{search_results[0].get('url', '')}"]
}}"""

    response = call_groq_api(prompt, api_key)
    if not response:
        return {
            "status": "error",
            "explanation": "Verification failed",
            "correct_info": "",
            "confidence": "low",
            "sources": []
        }
    
    response = re.sub(r'```json\s*|\s*```', '', response).strip()
    
    try:
        result = json.loads(response)
        result.setdefault('confidence', 'medium')
        result.setdefault('sources', [r.get('url', '') for r in search_results[:2]])
        return result
    except json.JSONDecodeError:
        return {
            "status": "error",
            "explanation": "Could not parse verification",
            "correct_info": "",
            "confidence": "low",
            "sources": []
        }

def generate_pdf_report(results):
    """Generate PDF report"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, 
                           topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                 fontSize=24, textColor=HexColor('#1f1f1f'),
                                 spaceAfter=30, alignment=1)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'],
                                  fontSize=14, textColor=HexColor('#2c3e50'),
                                  spaceAfter=12, spaceBefore=12)
    body_style = ParagraphStyle('CustomBody', parent=styles['BodyText'],
                               fontSize=10, spaceAfter=6)
    
    story = []
    story.append(Paragraph("Fact-Checking Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", 
                          body_style))
    story.append(Spacer(1, 0.3*inch))
    
    verified = sum(1 for r in results if r.get('status') == 'verified')
    inaccurate = sum(1 for r in results if r.get('status') == 'inaccurate')
    false = sum(1 for r in results if r.get('status') == 'false')
    
    story.append(Paragraph("Summary", heading_style))
    story.append(Paragraph(f"Total: {len(results)} | Verified: {verified} | "
                          f"Inaccurate: {inaccurate} | False: {false}", body_style))
    story.append(Spacer(1, 0.3*inch))
    
    for idx, result in enumerate(results):
        status_emoji = {"verified": "✓", "inaccurate": "⚠", "false": "✗"}.get(
            result.get('status', 'error'), "?")
        
        story.append(Paragraph(f"<b>#{idx + 1}: {status_emoji} {result.get('status', 'ERROR').upper()}</b>", 
                              heading_style))
        story.append(Paragraph(f"<b>Claim:</b> {result.get('claim', 'N/A')}", body_style))
        story.append(Paragraph(f"<b>Explanation:</b> {result.get('explanation', 'N/A')}", 
                              body_style))
        
        if result.get('correct_info'):
            story.append(Paragraph(f"<b>Correct Info:</b> {result['correct_info']}", 
                                  body_style))
        story.append(Spacer(1, 0.2*inch))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def main():
    init_clients()
    
    st.title("🔍 Fact-Checking Web App")
    st.markdown("Upload a PDF to verify claims against live web data")
    
    with st.sidebar:
        st.header("About")
        st.markdown("""
        **How it works:**
        1. Extracts verifiable claims from PDFs
        2. Searches live web data
        3. Verifies accuracy
        
        **Status:**
        - 🟢 **Verified**: Matches current data
        - 🟡 **Inaccurate**: Outdated/wrong
        - 🔴 **False**: No evidence
        """)
        st.markdown("---")
        st.markdown(f"**Date**: {datetime.now().strftime('%B %d, %Y')}")
        st.markdown("**Powered by**: Groq + Tavily")
    
    uploaded_file = st.file_uploader("Upload PDF Document", type=['pdf'])
    
    if not uploaded_file:
        st.info("👆 Upload a PDF to start fact-checking")
        return
    
    with st.spinner("📄 Extracting text..."):
        text = extract_text_from_pdf(uploaded_file)
    
    if not text:
        st.error("Failed to extract text from PDF")
        return
    
    st.success(f"✅ Extracted {len(text)} characters")
    
    with st.expander("📖 Document Preview"):
        st.text(text[:1000] + "..." if len(text) > 1000 else text)
    
    if not st.button("🚀 Start Fact-Checking", type="primary"):
        return
    
    with st.spinner("🔎 Extracting claims..."):
        claims = extract_claims(text, st.session_state.groq_api_key)
    
    if not claims:
        st.warning("⚠️ No verifiable claims found in document")
        return
    
    st.success(f"✅ Found {len(claims)} claims to verify")
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    results = []
    
    for idx, claim in enumerate(claims):
        status_text.text(f"Verifying {idx + 1}/{len(claims)}: {claim.get('claim', '')[:50]}...")
        
        search_results = search_claim(claim.get('claim', ''), 
                                     claim.get('context', ''), 
                                     st.session_state.tavily_client)
        
        time.sleep(1)  # Rate limit protection
        
        verification = verify_claim(claim, search_results, st.session_state.groq_api_key)
        
        results.append({**claim, **verification})
        progress_bar.progress((idx + 1) / len(claims))
        
        time.sleep(2)  # Rate limit protection between claims
    
    status_text.empty()
    progress_bar.empty()
    
    # Display results
    st.header("📊 Verification Results")
    
    verified = sum(1 for r in results if r.get('status') == 'verified')
    inaccurate = sum(1 for r in results if r.get('status') == 'inaccurate')
    false = sum(1 for r in results if r.get('status') == 'false')
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", len(results))
    col2.metric("🟢 Verified", verified)
    col3.metric("🟡 Inaccurate", inaccurate)
    col4.metric("🔴 False", false)
    
    accuracy = (verified / len(results) * 100) if results else 0
    
    st.markdown("---")
    
    if accuracy < 20:
        st.error(f"🚨 Critical: Only {accuracy:.1f}% verified. Review needed.")
    elif accuracy < 50:
        st.warning(f"⚠️ Issues found: {accuracy:.1f}% verified.")
    elif accuracy < 80:
        st.info(f"ℹ️ Minor issues: {accuracy:.1f}% verified.")
    else:
        st.success(f"✅ Good: {accuracy:.1f}% verified.")
    
    st.markdown("---")
    
    # Show individual results
    for idx, result in enumerate(results):
        status = result.get('status', 'error')
        emoji = {"verified": "🟢", "inaccurate": "🟡", "false": "🔴"}.get(status, "⚪")
        
        with st.expander(f"{emoji} Claim #{idx + 1}: {status.upper()}", expanded=(status != 'verified')):
            st.markdown(f"**Claim:** _{result.get('claim', 'N/A')}_")
            st.markdown(f"**Type:** `{result.get('type', 'N/A')}` | **Confidence:** `{result.get('confidence', 'N/A').upper()}`")
            st.markdown(f"**Explanation:** {result.get('explanation', 'N/A')}")
            
            if result.get('correct_info'):
                st.markdown(f"**✓ Correct Info:** {result['correct_info']}")
            
            if result.get('sources'):
                st.markdown("**Sources:**")
                for source in result['sources'][:2]:
                    if source:
                        st.markdown(f"- [{source[:60]}...]({source})")
    
    # PDF download
    pdf_buffer = generate_pdf_report(results)
    st.download_button(
        label="📥 Download Full Report (PDF)",
        data=pdf_buffer,
        file_name=f"fact_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf"
    )

if __name__ == "__main__":
    main()