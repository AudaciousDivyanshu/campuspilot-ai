# CampusPilot AI: Implementation Roadmap

This roadmap breaks down the development of CampusPilot AI into sequential, bite-sized phases. Each phase emphasizes working functionality, clear separation of concerns, and verifiable outcomes before proceeding.

---

## 🗺️ Phases Overview

```
Phase 1: Foundation & Setup (Current)
   │
   ▼
Phase 2: Database Layer (SQLite)
   │
   ▼
Phase 3: Campus Deterministic Tools
   │
   ▼
Phase 4: LangChain Agent & Gemini Reasoning Loop
   │
   ▼
Phase 5: Rule-Based Baseline Engine
   │
   ▼
Phase 6: FastAPI Backend Services & Audit Logging
   │
   ▼
Phase 7: Streamlit Frontend (Human-in-the-Loop Interaction)
   │
   ▼
Phase 8: Evaluation & Comparative Analysis
```

---

## 📌 Phase 1: Foundation & Structure (Current)
- [x] Establish modular repository layout.
- [x] Create dependency list (`requirements.txt`) without bloat.
- [x] Configure `.gitignore` and `.env.example`.
- [x] Define documentation and project roadmap.
- [ ] User review and verification.

---

## 📌 Phase 2: SQLite Campus Database
- **Objective:** Create a lightweight, transparent SQLite database representing realistic campus state.
- **Schema Design:**
  - `students`: Student ID, name, department, semester.
  - `lab_slots`: Lab name, date, time slot, capacity, booked count.
  - `lab_bookings`: Booking ID, student ID, slot ID, status, timestamp.
  - `complaints`: Complaint ID, student ID, category, description, status, filed_at.
  - `attendance`: Student ID, course code, course name, classes attended, total classes.
  - `leave_requests`: Request ID, student ID, reason, start date, end date, status.
  - `library_books`: Book ID, title, author, total copies, available copies.
  - `library_reservations`: Reservation ID, student ID, book ID, reserved_at, status.
- **Deliverables:**
  - `app/database/connection.py`: SQLite connection utility.
  - `app/database/schema.sql` or setup script.
  - `app/database/seed_data.py`: Pre-populates realistic records with both available and conflicting states to test agent edge cases.

---

## 📌 Phase 3: Core Campus Service Tools
- **Objective:** Write clean, deterministic Python functions executing actual SQL queries.
- **Tool Modules (`app/tools/`):**
  1. `lab_tools.py`:
     - `check_lab_availability(lab_name, date)`
     - `book_lab_slot(student_id, lab_name, date, time_slot)`
  2. `maintenance_tools.py`:
     - `register_complaint(student_id, category, description)`
     - `get_complaint_status(complaint_id)`
  3. `academic_tools.py`:
     - `check_attendance(student_id, course_code)`
     - `submit_leave_application(student_id, reason, start_date, end_date)`
  4. `library_tools.py`:
     - `search_books(query)`
     - `reserve_book(student_id, book_id)`
- **Key Principle:** Zero LLM dependencies here. Pure, testable database operations returning structured dictionaries.

---

## 📌 Phase 4: LangChain Agent & Gemini Reasoning Loop
- **Objective:** Bind campus tools to LangChain and configure Gemini to execute agentic workflows.
- **Agentic Workflow Capabilities:**
  - **Tool Selection:** Expose Phase 3 tools with clear docstrings as LangChain Structured Tools.
  - **ReAct Loop:** Step-by-step thinking, acting, and observing.
  - **Failure Detection & Re-planning:** If a lab slot is full or attendance is below minimum, the agent must catch the tool error/result and suggest alternative slots or actions.
  - **Sensitive Action Gate (Approval Mechanism):** Mark state-changing actions (e.g., formal leave request submission, slot cancellation) as requiring user approval before execution.
  - **Execution Logging:** Capture reasoning traces (`thoughts`, `actions`, `observations`, `retries`).

---

## 📌 Phase 5: Rule-Based Baseline Engine
- **Objective:** Implement a straightforward, deterministic rule/keyword-based script for the same workflows.
- **Purpose:** Serve as a benchmark to quantitatively evaluate the agent against standard rule-based chatbots.
- **Metrics to Compare:**
  - Multi-step execution success rate.
  - Handling of unexpected/slot-full conditions.
  - Natural language flexibility and recovery rate.

---

## 📌 Phase 6: FastAPI Backend Services
- **Objective:** Expose clean REST endpoints connecting the agent, baseline, and database.
- **Endpoints:**
  - `POST /api/chat`: Accepts student messages, returns agent response, steps taken, and approval requests if needed.
  - `POST /api/approve`: Approves or denies a pending sensitive action.
  - `POST /api/baseline`: Runs the query through the rule-based baseline for direct comparison.
  - `GET /api/logs`: Retrieves trace logs.

---

## 📌 Phase 7: Functional Streamlit Frontend
- **Objective:** Build an intuitive, simple interface focused on usability and transparent agent reasoning.
- **UI Components:**
  - Simple chat window for student interaction.
  - "Agent Thoughts & Tool Trace" expandable sidebar to observe the reasoning process.
  - Approval prompt modal/button when the agent requests permission for sensitive actions.
  - Dual-mode toggle / comparison pane: Run query on Agent vs. Baseline.

---

## 📌 Phase 8: Testing & Evaluation
- Test with standard scenarios:
  1. Happy path: Book available lab slot.
  2. Conflict path: Requested slot is fully booked -> agent identifies conflict, queries alternative times, and offers choices.
  3. Conditional multi-step: Check attendance first, then apply for leave only if criteria permit.
  4. Sensitive action rejection: User rejects the proposed leave draft -> agent cancels gracefully.
- Generate comparative summary report between Agent and Rule-Based Baseline.

