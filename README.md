# CampusPilot AI: Agentic AI Assistant for Multi-Step Campus Service Workflows

CampusPilot AI is a functional college project demonstrating an agentic AI assistant capable of handling multi-step student service workflows autonomously and reliably.

---

## 🎯 Project Overview & Objective

Traditional college portals require students to navigate disjointed forms and separate portals for routine tasks. CampusPilot AI uses an LLM-powered agent to:
1. Parse high-level natural language user intentions.
2. Break multi-step tasks into actionable tool executions.
3. Observe real database/API outcomes and handle execution failures.
4. Request explicit user approval prior to executing sensitive actions (e.g., leave submissions, slot cancellations).
5. Maintain detailed execution audit trails.
6. Benchmark agent decision-making against a baseline rule-based workflow.

---

## 🛠 Tech Stack

- **Language:** Python 3.10+
- **LLM / Reasoning Engine:** Google Gemini API
- **Agent Framework:** LangChain (ReAct / Tool-calling Agent)
- **Backend API:** FastAPI & Uvicorn
- **Database:** SQLite (local relational store for campus records)
- **Frontend UI:** Streamlit (clean, functional UI)

---

## 🏛 Core Campus Workflows

1. **Lab Slot Booking:** Check lab schedule availability, reserve benches/PCs, and resolve booking conflicts.
2. **Maintenance Complaint Registration:** File tickets for campus infrastructure issues (hostel, lab, classrooms) and query status.
3. **Attendance & Leave Management:** Check course attendance percentages, verify minimum attendance rules, and submit formal leave applications.
4. **Library Resource Management:** Search book catalogue availability and reserve copies.

---

## 🤖 Agentic Capabilities

- **Goal Decomposition:** Breaks compound queries (e.g., *"Check if I have enough attendance in Math, and if so, book Lab 2 for Friday"*) into sequential steps.
- **Tool Selection & Execution:** Selects deterministic tools bound directly to SQLite queries.
- **Observation & Error Recovery:** Observes tool output; re-plans if a slot is booked or if criteria are not met.
- **Human-in-the-Loop Approval:** Pauses for user confirmation before executing state-changing/sensitive actions.
- **Traceability:** Logs step-by-step reasoning steps (`Thought`, `Action`, `Observation`).
- **Baseline Comparison:** Compares task success rate, execution time, and recovery flexibility against hardcoded rule-based scripts.

---

## 📂 Project Architecture

```text
campuspilot-ai/
├── app/
│   ├── agent/         # LangChain agent configuration, prompts, and reasoning loop
│   ├── api/           # FastAPI routers and request/response models
│   ├── baseline/      # Rule-based workflow engine for baseline comparison
│   ├── database/      # SQLite connection, schema definition, and seed data
│   └── tools/         # Campus tool definitions (Lab, Maintenance, Attendance, Library)
├── data/              # SQLite database storage (campus.db)
├── docs/              # Project documentation and roadmap
├── frontend/          # Streamlit user interface
├── .env.example       # Template for environment configuration
├── .gitignore         # Git ignore rules
├── README.md          # Project guide and documentation
└── requirements.txt   # Core Python dependencies
```

---

## 🚀 Setup & Verification Instructions

### 1. Create and Activate Virtual Environment
```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and supply your Gemini API Key:
```bash
cp .env.example .env
```
Update `.env`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
```

### 4. Run the Application
Start the FastAPI backend:
```bash
uvicorn app.main:app --port 8000 --reload
```

Start the Streamlit frontend:
```bash
streamlit run frontend/streamlit_app.py
```

---

## 📜 Next Steps

See [docs/roadmap.md](file:///c:/Users/Lenovo/Desktop/campuspilot-ai/docs/roadmap.md) for the phased implementation plan.

