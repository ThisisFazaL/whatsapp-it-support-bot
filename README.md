# 🤖 WhatsApp IT Support Chatbot (Python / FastAPI)

Production-ready, automated menu-driven IT Support Chatbot built natively in Python using **FastAPI**, **SQLAlchemy (Async Engine)**, and **Meta WhatsApp Cloud API**.

---

## 🌟 Key System Capabilities

- 🔐 **Employee Identification**: Incoming WhatsApp numbers map directly to employee records (`employees` table). Unregistered numbers receive an access restriction warning.
- 📋 **Dynamic Menu Navigation**: Database-driven multi-step menu: Category ➡️ Subcategory ➡️ Specific Issue ➡️ Description ➡️ Priority.
- 🎟️ **Automatic Ticket Formatting**: Formats tickets as `TKT-YYYYMMDD-XXXXX` and logs them into PostgreSQL / SQLite.
- 👨‍💻 **Admin Assignment & Notifications**: Automatically routes new support tickets to active IT support admins with full context.
- 🛠️ **Admin Command Execution**: Supports admin WhatsApp commands like `resolve TKT-YYYYMMDD-XXXXX` to mark tickets resolved.
- 🔄 **Resolution Confirmation Loop**: Automatically prompts employees upon resolution (`1` = Confirm & Close, `2` = Reopen Ticket).
- 🧹 **Global Reset Keywords**: `hi`, `hello`, `menu`, `reset`, `cancel` reset the conversation state anytime.

---

## 📁 Directory Structure

```text
whatsapp_it_support_bot/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app (Webhook endpoints GET & POST)
│   ├── config.py              # Environment variables & settings configuration
│   ├── database.py            # SQLAlchemy Async models & database connection pool
│   ├── meta_api.py            # Meta WhatsApp Cloud Graph API client wrapper
│   ├── state_manager.py       # Conversation state engine & queries
│   └── handlers/
│       ├── __init__.py
│       ├── admin_handler.py   # Admin commands ('resolve TKT-...')
│       ├── flow_handler.py    # Multi-step ticket creation flow
│       └── resolution_handler.py # Ticket resolution confirmation (Close/Reopen)
├── schema.sql                 # PostgreSQL DDL schema & seed dataset
├── init_db.py                 # DB initializer & seed data runner script
├── test_webhook.py            # Local CLI test suite simulating WhatsApp webhooks
├── requirements.txt           # Python dependencies
├── .env                       # Pre-configured credentials & DB URL
└── README.md                  # System documentation
```

---

## 🚀 Quick Start Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize Database & Seed Data
Run the initializer to create database tables and seed default categories, subcategories, issues, priorities, support admins, and sample employees:
```bash
python init_db.py
```

### 3. Start FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```
- Interactive API Documentation (Swagger UI): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health Endpoint: `GET http://127.0.0.1:8000/health`
- Tickets List: `GET http://127.0.0.1:8000/tickets`

---

## 🧪 Testing Locally (Without WhatsApp / ngrok)

Run the included automated simulation test script:
```bash
python test_webhook.py
```
This script tests:
1. 🚫 Unregistered phone attempt.
2. 📱 Employee ticket creation flow (`John Doe` creating a hardware screen issue ticket).
3. 🛠️ Admin resolution command (`resolve TKT-20260812-00001`).
4. 🏁 Employee confirmation (`1` to confirm & close ticket).

---

## 🌐 Meta WhatsApp Cloud API Setup

To connect to live Meta WhatsApp Cloud API:

1. **Expose Local Server using ngrok**:
   ```bash
   ngrok http 8000
   ```
   Copy your HTTPS forwarding URL (e.g. `https://xxxx.ngrok-free.app`).

2. **Configure Webhook in Meta Developer Dashboard**:
   - Go to [Meta Developers Portal](https://developers.facebook.com/) ➡️ Your App ➡️ WhatsApp ➡️ Configuration.
   - Set **Callback URL**: `https://xxxx.ngrok-free.app/webhook/meta-whatsapp`
   - Set **Verify Token**: `itsupport_meta_secret_123`
   - Click **Verify and Save**.
   - Subscribe to the **`messages`** webhook field.

3. **Environment Credentials Reference** (`.env`):
   ```env
   PHONE_NUMBER_ID=1145527058653682
   META_ACCESS_TOKEN=EAAaI4UFujrkBSO2MlhGj0DO7J5k4Dr0QMZAMMqLd...
   META_GRAPH_VERSION=v19.0
   META_DISPLAY_NUMBER=+1 555-672-9057
   VERIFY_TOKEN=itsupport_meta_secret_123
   DATABASE_URL=sqlite+aiosqlite:///./itsupport.db
   ```

---

## 🛢️ PostgreSQL Production Setup

To switch from SQLite to production PostgreSQL:
1. Execute `schema.sql` on your PostgreSQL server (`supportit` DB).
2. Update `DATABASE_URL` in `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://supportit:password@localhost:5432/supportit
   ```
3. Restart FastAPI application.
