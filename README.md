# Vera Challenge Bot

## 👤 Team
- Team Name: VeraFlow
- Member: Sameer

---

## 🧠 Approach

This bot is a **deterministic rule-based assistant** that generates high-quality, context-aware messages using:

- Category context → defines tone and domain rules  
- Merchant context → business metrics, offers, signals  
- Trigger context → reason for sending message  
- Customer context → personalization (for recall flows)

The bot combines all contexts to produce **specific, relevant, and actionable messages**.

---

## 🔄 Supported Flows

The bot handles these trigger types:

### 1. Research Digest
- Uses category research data
- Includes source + numbers (study size, %)
- Anchors to merchant’s customer segment

### 2. Performance Dip
- Detects drop in metrics (calls, CTR)
- Compares with peer benchmarks
- Suggests recovery action

### 3. Review Theme Emerged
- Identifies repeated complaints
- Suggests reply + operational fix

### 4. IPL Match (Event-based)
- Uses real-world event timing
- Suggests promotion strategy

### 5. Curious Ask
- Low-friction engagement question
- Converts response into marketing content

### 6. Customer Recall (On-behalf messaging)
- Personalized using last visit, slots, language
- Includes offer + booking CTA

---

## ⚙️ Design Principles

- **Specificity** → Uses real numbers, dates, sources  
- **Category Fit** → Maintains correct tone (clinical, casual, etc.)  
- **Merchant Fit** → Uses merchant data (CTR, customers, offers)  
- **Trigger Relevance** → Always answers "why now"  
- **Engagement** → One clear, low-effort CTA  

---

## 🚀 Technical Design

- Built using **FastAPI**
- Fully **stateless API + in-memory context store**
- Handles:
  - `/v1/context` → stores context
  - `/v1/tick` → decides actions
  - `/v1/reply` → handles conversation
- Supports:
  - suppression keys (no spam)
  - max 20 actions per tick
  - auto-reply detection
  - multi-turn conversations

---

## ⚖️ Tradeoffs

- Rule-based (no LLM) → predictable, fast, stable  
- Focused on high-quality flows instead of covering all triggers  
- Limited deep reasoning but strong performance on known patterns  

---

## ▶️ Run Locally

```bash
pip install -r requirements.txt
uvicorn bot:app --host 0.0.0.0 --port 8080