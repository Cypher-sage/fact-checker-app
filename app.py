import streamlit as st
from groq import Groq
from tavily import TavilyClient
import PyPDF2
import io
import json
import re
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT

st.set_page_config(
    page_title="Fact-Checking Web App",
    page_icon="🔍",
    layout="wide"
)

@st.cache_resource
def get_clients():
    groq_key = st.secrets.get("GROQ_API_KEY", "")
    tavily_key = st.secrets.get("TAVILY_API_KEY", "")
    
    if not groq_key or not tavily_key:
        st.error("⚠️ API keys not configured. Please add them to Streamlit secrets.")
        st.stop()
    
    return Groq(api_key=groq_key), TavilyClient(api_key=tavily_key)

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_file.read()))
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() + "\n"
    return text

def extract_claims(text, client):
    prompt = f"""Analyze this document and extract ALL verifiable factual claims. Focus on:
- Statistics and percentages (e.g., "grew by 25%", "unemployment at 3.5%")
- Dates and timeframes (e.g., "in 2023", "Q4 2024")
- Financial figures (revenue, costs, stock prices, GDP, market cap)
- Technical specifications (speeds, capacities, dimensions)
- Market data and rankings
- Growth rates and comparisons

For each claim, extract:
1. The exact claim text (verbatim quote)
2. The type: statistic|date|financial|technical|comparison
3. Brief context for verification

Return ONLY valid JSON array, no markdown:
[
  {{
    "claim": "exact quoted text from document",
    "type": "statistic|date|financial|technical|comparison",
    "context": "what this claim is about"
  }}
]

Document:
{text[:8000]}"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        max_tokens=4000,
    )
    
    response_text = chat_completion.choices[0].message.content.strip()
    response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
    
    try:
        claims = json.loads(response_text)
        return claims
    except json.JSONDecodeError as e:
        st.error(f"Error parsing claims: {e}")
        st.code(response_text)
        return []

def search_claim(claim_text, context, tavily):
    query = f"{claim_text} {context}"
    try:
        response = tavily.search(query, max_results=5)
        return response.get('results', [])
    except Exception as e:
        st.warning(f"Search error: {e}")
        return []

def verify_claim(claim, search_results, client):
    results_text = "\n\n".join([
        f"Source: {r.get('url', 'N/A')}\nTitle: {r.get('title', 'N/A')}\nContent: {r.get('content', 'N/A')[:500]}"
        for r in search_results[:5]
    ])
    
    prompt = f"""Verify this claim against current web data:

CLAIM: "{claim['claim']}"
TYPE: {claim['type']}
CONTEXT: {claim['context']}

SEARCH RESULTS:
{results_text}

CRITICAL INSTRUCTIONS:
- VERIFIED: Use ONLY if the exact claim matches current, authoritative sources (within reasonable margins)
- INACCURATE: Use if the claim WAS true but is now outdated (old prices, old stats, old dates that have changed)
- FALSE: Use if the claim is fabricated, never was true, or is completely contradicted by all sources

IMPORTANT DISTINCTIONS:
- A product that existed but has updated specs = INACCURATE (not FALSE)
- A statistic that was true in the past but changed = INACCURATE
- A claim about something that NEVER existed or happened = FALSE
- A number that's completely wrong and never was accurate = FALSE

Examples:
- "Tesla stock was $200 in 2023" but now it's $250 = INACCURATE (price changed)
- "GPT-5 was released in 2024" but GPT-5 doesn't exist = FALSE (fabricated)
- "Bitcoin hit $150,000" but it never reached that = FALSE (never happened)
- "iPhone 15 costs $799" and it does = VERIFIED

For financial/statistical claims, check if numbers match current OR historical data.
If a claim was accurate in the past but outdated now = INACCURATE (with current figures).
If a claim was NEVER accurate = FALSE.

Return ONLY valid JSON, no markdown:
{{
  "status": "verified|inaccurate|false",
  "explanation": "Clear explanation with specifics (e.g., 'Claim says $150K but Bitcoin never exceeded $69K')",
  "correct_info": "Current accurate information with numbers",
  "confidence": "high|medium|low",
  "sources": ["url1", "url2"]
}}"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        max_tokens=1500,
    )
    
    response_text = chat_completion.choices[0].message.content.strip()
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

def create_pdf_report(results, filename):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    story.append(Paragraph("Fact-Checking Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))
    story.append(Spacer(1, 0.3*inch))
    
    verified = sum(1 for r in results if r.get('status') == 'verified')
    inaccurate = sum(1 for r in results if r.get('status') == 'inaccurate')
    false = sum(1 for r in results if r.get('status') == 'false')
    
    summary_data = [
        ['Metric', 'Count'],
        ['Total Claims', str(len(results))],
        ['Verified', str(verified)],
        ['Inaccurate', str(inaccurate)],
        ['False', str(false)]
    ]
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3b82f6')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    
    story.append(Paragraph("Executive Summary", heading_style))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    accuracy_rate = (verified / len(results) * 100) if len(results) > 0 else 0
    if accuracy_rate < 20:
        assessment = f"Critical Issues Found: Only {accuracy_rate:.1f}% of claims verified. Document needs significant review."
    elif accuracy_rate < 50:
        assessment = f"Multiple Issues Found: {accuracy_rate:.1f}% verified. Review recommended before publication."
    elif accuracy_rate < 80:
        assessment = f"Some Issues Found: {accuracy_rate:.1f}% verified. Minor corrections needed."
    else:
        assessment = f"Document Looks Good: {accuracy_rate:.1f}% of claims verified."
    
    story.append(Paragraph(f"<b>Assessment:</b> {assessment}", styles['Normal']))
    story.append(Spacer(1, 0.4*inch))
    story.append(PageBreak())
    
    story.append(Paragraph("Detailed Findings", heading_style))
    story.append(Spacer(1, 0.2*inch))
    
    for idx, result in enumerate(results):
        status = result.get('status', 'unknown')
        if status == 'verified':
            status_color = colors.HexColor('#10b981')
            status_text = '✓ VERIFIED'
        elif status == 'inaccurate':
            status_color = colors.HexColor('#f59e0b')
            status_text = '⚠ INACCURATE'
        else:
            status_color = colors.HexColor('#ef4444')
            status_text = '✗ FALSE'
        
        claim_style = ParagraphStyle(
            'ClaimStyle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=6
        )
        
        story.append(Paragraph(f"<b>Claim #{idx + 1}</b>", claim_style))
        
        claim_data = [
            ['Status', status_text],
            ['Type', result.get('type', 'N/A').upper()],
            ['Confidence', result.get('confidence', 'N/A').upper()],
        ]
        
        claim_table = Table(claim_data, colWidths=[1.5*inch, 4.5*inch])
        claim_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (1, 0), (1, 0), status_color),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        story.append(claim_table)
        story.append(Spacer(1, 0.1*inch))
        
        story.append(Paragraph(f"<b>Claim:</b> <i>{result.get('claim', 'N/A')}</i>", styles['Normal']))
        story.append(Spacer(1, 0.05*inch))
        
        story.append(Paragraph(f"<b>Explanation:</b> {result.get('explanation', 'N/A')}", styles['Normal']))
        
        if result.get('correct_info'):
            story.append(Spacer(1, 0.05*inch))
            story.append(Paragraph(f"<b>Correct Information:</b> {result.get('correct_info')}", styles['Normal']))
        
        if result.get('sources'):
            story.append(Spacer(1, 0.05*inch))
            sources_text = "<b>Sources:</b><br/>" + "<br/>".join([f"• {s[:80]}..." if len(s) > 80 else f"• {s}" for s in result.get('sources', [])[:3]])
            story.append(Paragraph(sources_text, styles['Normal']))
        
        story.append(Spacer(1, 0.2*inch))
        
        if (idx + 1) % 3 == 0 and idx < len(results) - 1:
            story.append(PageBreak())
    
    doc.build(story)
    buffer.seek(0)
    return buffer

def process_single_pdf(uploaded_file, groq_client, tavily_client):
    with st.spinner("📄 Extracting text from PDF..."):
        text = extract_text_from_pdf(uploaded_file)
    
    with st.spinner("🔎 Extracting claims..."):
        claims = extract_claims(text, groq_client)
    
    if not claims:
        return None, None
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    results = []
    for idx, claim in enumerate(claims):
        status_text.text(f"Verifying claim {idx + 1}/{len(claims)}: {claim['claim'][:60]}...")
        
        search_results = search_claim(claim['claim'], claim['context'], tavily_client)
        verification = verify_claim(claim, search_results, groq_client)
        
        results.append({**claim, **verification})
        progress_bar.progress((idx + 1) / len(claims))
    
    status_text.empty()
    progress_bar.empty()
    
    return text, results

def display_results(results, filename):
    st.header("📊 Verification Results")
    
    verified = sum(1 for r in results if r.get('status') == 'verified')
    inaccurate = sum(1 for r in results if r.get('status') == 'inaccurate')
    false = sum(1 for r in results if r.get('status') == 'false')
    
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
        status = result.get('status', 'unknown')
        
        if status == 'verified':
            emoji = "🟢"
            color = "green"
        elif status == 'inaccurate':
            emoji = "🟡"
            color = "orange"
        else:
            emoji = "🔴"
            color = "red"
        
        with st.container():
            st.markdown(f"### {emoji} Claim #{idx + 1}: {status.upper()}")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown(f"**Claim:** _{result.get('claim', 'N/A')}_")
                st.markdown(f"**Type:** `{result.get('type', 'N/A')}` | **Confidence:** `{result.get('confidence', 'N/A').upper()}`")
                st.markdown(f"**Explanation:** {result.get('explanation', 'N/A')}")
                
                if result.get('correct_info'):
                    st.markdown(f"**✓ Correct Information:** {result.get('correct_info')}")
            
            with col2:
                if result.get('sources'):
                    st.markdown("**Sources:**")
                    for source in result.get('sources', [])[:3]:
                        st.markdown(f"- [{source[:50]}...]({source})")
            
            st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.download_button(
            label="📥 Download JSON Report",
            data=json.dumps(results, indent=2),
            file_name=f"fact_check_{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )
    
    with col2:
        pdf_buffer = create_pdf_report(results, filename)
        st.download_button(
            label="📄 Download PDF Report",
            data=pdf_buffer,
            file_name=f"fact_check_{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mime="application/pdf"
        )

def main():
    st.title("🔍 Fact-Checking Web App")
    st.markdown("Upload PDF(s) to automatically verify claims against live web data")
    
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
    
    uploaded_files = st.file_uploader("Upload PDF Document(s)", type=['pdf'], accept_multiple_files=True)
    
    if uploaded_files:
        groq_client, tavily_client = get_clients()
        
        if len(uploaded_files) == 1:
            uploaded_file = uploaded_files[0]
            st.success(f"✅ Loaded: {uploaded_file.name}")
            
            with st.expander("📖 Document Preview"):
                preview_text = extract_text_from_pdf(uploaded_file)
                st.text(preview_text[:1000] + "..." if len(preview_text) > 1000 else preview_text)
            
            if st.button("🚀 Start Fact-Checking", type="primary"):
                text, results = process_single_pdf(uploaded_file, groq_client, tavily_client)
                
                if results:
                    st.session_state['results'] = results
                    st.session_state['filename'] = uploaded_file.name.replace('.pdf', '')
        else:
            st.success(f"✅ Loaded {len(uploaded_files)} files")
            
            if st.button("🚀 Start Batch Fact-Checking", type="primary"):
                all_results = {}
                
                for file_idx, uploaded_file in enumerate(uploaded_files):
                    st.subheader(f"Processing {file_idx + 1}/{len(uploaded_files)}: {uploaded_file.name}")
                    
                    text, results = process_single_pdf(uploaded_file, groq_client, tavily_client)
                    
                    if results:
                        all_results[uploaded_file.name] = results
                        
                        verified = sum(1 for r in results if r.get('status') == 'verified')
                        inaccurate = sum(1 for r in results if r.get('status') == 'inaccurate')
                        false = sum(1 for r in results if r.get('status') == 'false')
                        
                        st.success(f"✅ Completed: {len(results)} claims | 🟢 {verified} | 🟡 {inaccurate} | 🔴 {false}")
                    
                    st.markdown("---")
                
                st.session_state['batch_results'] = all_results
        
        if 'results' in st.session_state:
            display_results(st.session_state['results'], st.session_state['filename'])
        
        if 'batch_results' in st.session_state:
            st.header("📊 Batch Processing Results")
            
            for filename, results in st.session_state['batch_results'].items():
                with st.expander(f"📄 {filename}"):
                    display_results(results, filename.replace('.pdf', ''))

if __name__ == "__main__":

    main()
