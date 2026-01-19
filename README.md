# 🔍 Fact-Checking Web App

An AI-powered web application that automatically extracts claims from PDF documents and verifies them against live web data to detect misinformation, outdated statistics, and false claims.

![Status](https://img.shields.io/badge/status-active-success.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 🎯 Overview

This tool acts as a "Fact Checker" that sits between drafts and the publish button. It ingests PDF documents, cross-references claims against real-time web data, and flags what's accurate and what needs review.

### Key Features

- **Automatic Claim Extraction**: Identifies verifiable claims (statistics, dates, financial figures, technical specs)
- **Live Web Verification**: Searches current web data using Tavily API
- **Smart Classification**: Flags claims as Verified ✅, Inaccurate ⚠️, or False ❌
- **Confidence Scoring**: Shows verification confidence levels (high/medium/low)
- **PDF Reports**: Generate professional PDF reports with findings
- **Beautiful UI**: Modern, responsive interface with drag-and-drop upload

## 🚀 Live Demo

**Try it here**: fact-checker-aayushsikka.streamlit.app

## 📸 Screenshots

### Upload Interface
Large, intuitive drag-and-drop area for PDF uploads

### Verification Results
Color-coded claims with detailed explanations and sources

### PDF Report Export
Professional formatted reports ready to share

## 🛠️ Tech Stack

- **Frontend**: Streamlit
- **AI Model**: Groq (Llama 3.3 70B)
- **Web Search**: Tavily API
- **PDF Processing**: PyPDF2
- **Report Generation**: ReportLab
- **Deployment**: Streamlit Cloud

## 📋 How It Works

1. **Extract**: Upload a PDF → AI extracts all verifiable factual claims
2. **Search**: Each claim is searched against live web data (Tavily API)
3. **Verify**: AI analyzes search results and categorizes each claim:
   - ✅ **Verified**: Matches current data
   - ⚠️ **Inaccurate**: Outdated or partially wrong
   - ❌ **False**: No evidence found or contradicted
4. **Report**: View results in-app or download PDF report

## 🎯 Claim Types Detected

- **Statistics & Percentages**: "GDP grew by 2.5%", "Unemployment at 3.7%"
- **Financial Figures**: Stock prices, revenue, market cap, valuations
- **Dates & Timeframes**: "In Q4 2024", "Released in March 2023"
- **Technical Specifications**: Speeds, capacities, dimensions
- **Market Data**: Rankings, comparisons, growth rates

## 🚦 Status Definitions

### ✅ Verified
- Claim matches current authoritative sources
- Numbers align within reasonable margin (±2%)
- Recent and accurate data

### ⚠️ Inaccurate
- Claim was true historically but now outdated
- Numbers have changed since publication
- Partially correct but needs updating

### ❌ False
- Claim was never accurate
- Fabricated or contradicted by all sources
- No credible evidence found

## 📦 Installation & Setup

### Prerequisites

- Python 3.8+
- Groq API key ([Get it here](https://console.groq.com/))
- Tavily API key ([Get it here](https://tavily.com/))

### Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/fact-checker-app.git
cd fact-checker-app

# Install dependencies
pip install -r requirements.txt

# Create secrets file
mkdir .streamlit
cat > .streamlit/secrets.toml << EOF
GROQ_API_KEY = "your-groq-key-here"
TAVILY_API_KEY = "your-tavily-key-here"
EOF

# Run the app
streamlit run app.py
```

The app will open at `http://localhost:8501`

## 🌐 Deployment

### Deploy to Streamlit Cloud

1. Fork/clone this repository
2. Go to [share.streamlit.io](https://share.streamlit.io/)
3. Sign in with GitHub
4. Click "New app"
5. Select your repository and `app.py`
6. Add secrets in Advanced settings:
   ```toml
   GROQ_API_KEY = "your-key"
   TAVILY_API_KEY = "your-key"
   ```
7. Click "Deploy!"

Your app will be live at `https://your-app-name.streamlit.app`

## 📁 Project Structure

```
fact-checker-app/
├── app.py                 # Main application
├── requirements.txt       # Python dependencies
├── README.md             # This file
└── .streamlit/
    └── secrets.toml      # API keys (not committed)
```

## 🔧 Configuration

### API Keys

Get your free API keys:
- **Groq**: Free tier includes generous credits
- **Tavily**: 1,000 free searches/month

### Customization

Edit `app.py` to customize:
- Claim extraction prompts
- Verification logic
- UI styling
- Report formatting

## 📊 Example Use Cases

- **Journalism**: Verify articles before publication
- **Research**: Check academic papers for accuracy
- **Marketing**: Validate press releases and marketing materials
- **Business**: Audit reports for outdated statistics
- **Legal**: Verify factual claims in documents

## 🎯 Accuracy & Performance

### What It Catches:

✅ Outdated stock prices and market caps  
✅ Fabricated statistics and false claims  
✅ Incorrect dates and timeframes  
✅ Wrong financial figures  
✅ Unverified technical specifications  

### Performance:

- **Processing Time**: ~15-20 seconds per claim
- **Accuracy Rate**: High accuracy on factual, verifiable claims
- **Best For**: Documents with specific, verifiable data

### Limitations:

- Works best with text-based PDFs (not scanned images)
- Requires claims to be verifiable against public web sources
- Cannot verify opinions or predictions
- Limited to publicly available information

## 🔒 Privacy & Security

- PDFs are processed in memory (not stored)
- API calls use secure HTTPS connections
- No data is permanently stored
- API keys are kept secret in Streamlit Cloud

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 🐛 Known Issues & Troubleshooting

### "No claims found"
- Document may be image-based (requires OCR)
- PDF might contain only opinions, not factual claims

### "API keys not configured"
- Ensure secrets are added in Streamlit Cloud settings
- Check key format matches TOML syntax

### Slow processing
- Normal for documents with many claims
- Each claim requires web search + AI analysis
- Consider smaller PDFs for testing

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Groq** for fast, free LLM inference
- **Tavily** for reliable web search API
- **Streamlit** for the amazing web framework
- **Anthropic** for Claude AI guidance

## 📧 Contact

For questions, issues, or suggestions:
- Open an issue on GitHub
- Email: aayushsikka27@gmail.com

## 🔮 Future Enhancements

- [ ] Batch processing (multiple PDFs)
- [ ] Historical claim tracking
- [ ] Browser extension
- [ ] API endpoint for automation
- [ ] Support for more document formats (Word, TXT)
- [ ] OCR for scanned PDFs
- [ ] Multilingual support
- [ ] Email report delivery

## ⭐ Star History

If you find this project useful, please consider giving it a star!

---

**Built with ❤️ for accurate information**

Last Updated: January 2025
