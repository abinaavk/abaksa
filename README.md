# ABAKSA - Electricity Billing Management System (Web Edition)

A full web version of the ABAKSA billing system, rebuilt from the ground up with
**Flask + SQLite3**, a Jinja2 templated frontend, and vanilla JS - no frontend
framework, no build step. Dark/light theme, mobile-responsive layout, Google
sign-in, and a separate admin panel gated behind `/admin`.

---

## 1. Quick Start

```bash
pip install -r requirements.txt
python3 app.py
```

Then open **http://localhost:5000** in your browser.

A `.env` file is already included with working defaults so the app runs
immediately - but **change `ADMIN_PASSWORD` before putting this anywhere
public.** See section 3 below for every setting.

The SQLite database (`instance/abaksa.db`) and the default admin account are
created automatically the first time you run the app. Nothing needs to be set
up by hand.

| | |
|---|---|
| **Customer portal** | http://localhost:5000/login |
| **Admin panel** | http://localhost:5000/admin |
| **Default admin login** | username `admin`, password whatever is set as `ADMIN_PASSWORD` in `.env` (ships as `admin123`) |

---

## 2. Project Structure

```
abaksa_web/
├── app.py                   # Entry point - run this. Flask app factory.
├── config.py                # Reads .env, holds tariff defaults & branding
├── database.py               # All SQL - schema, seeding, every query
├── auth.py                    # Flask-Login setup, admin/customer decorators
├── oauth.py                    # Google OAuth (Authlib) registration
├── logic.py                     # Tariff calc, late fines, anomaly detection
├── pdf_gen.py                    # PDF bill generation (reportlab + QR code)
├── email_utils.py                 # SMTP email sending
├── routes/
│   ├── public.py                    # Landing, login, register, Google OAuth
│   ├── customer.py                   # Customer portal (blueprint: portal)
│   └── admin.py                       # Admin panel (blueprint: admin)
├── templates/
│   ├── partials/                        # head, sidebars, topbar, icons, toasts
│   ├── public/                           # landing, login, register
│   ├── admin/                             # 12 admin pages + admin login
│   ├── customer/                           # 6 customer pages + link-account
│   └── errors/                              # 403 / 404 / 500
├── static/
│   ├── css/style.css                          # entire design system, ~1000 lines
│   └── js/                                      # theme.js, app.js, charts.js, chart.min.js
├── instance/                                      # abaksa.db lives here (gitignored)
├── bills/ backups/ exports/                        # generated files land here
├── tests/test_functional.py                          # end-to-end route tests
├── requirements.txt
├── .env.example                                        # copy to .env and fill in
└── .env                                                  # ready-to-run dev defaults
```

---

## 3. Every Setting in `.env`

| Variable | Required? | What it does |
|---|---|---|
| `SECRET_KEY` | Yes | Signs login session cookies. Already set to a random value. |
| `FLASK_HOST` / `FLASK_PORT` / `FLASK_DEBUG` | No | Dev server settings. |
| `BASE_URL` | Yes for Google login | Used to build the Google OAuth redirect URL. |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Yes | The one built-in admin account. **The password is re-applied from `.env` every time the app restarts** - so whoever controls this file controls the master login. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | No | Leave blank to disable Google sign-in (the button just shows disabled). See section 5. |
| `MAIL_SERVER` / `MAIL_PORT` / `MAIL_USE_TLS` / `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_FROM_NAME` | No | Leave blank to disable emailing bills - everything else still works, "Email Bill" just shows a warning toast instead. |

---

## 4. How the Admin Panel Works

Visiting **`/admin`** always takes you to the admin login screen (or straight
to the dashboard if you're already logged in as an admin) - it's a
completely separate area from the customer portal, with its own sidebar,
its own visual style, and its own session.

The **one built-in admin account** is controlled entirely by `.env`:
`ADMIN_USERNAME` and `ADMIN_PASSWORD`. Every time the app starts, that
account's password in the database is overwritten to match whatever is
currently in `.env` - so rotating the admin password is just an `.env` edit
and a restart, no database surgery needed.

Once logged in, that admin can create **additional** admin accounts from
**Admin Accounts** in the sidebar - those extra accounts are normal database
rows and are *not* tied to `.env`.

---

## 5. Setting Up Google Sign-In (optional)

1. Go to the [Google Cloud Console credentials page](https://console.cloud.google.com/apis/credentials).
2. Create an **OAuth 2.0 Client ID** (application type: Web application).
3. Add this as an **authorized redirect URI**: `http://localhost:5000/auth/google/callback`
   (swap in your real domain once deployed).
4. Copy the Client ID and Client Secret into `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`.
5. Restart the app. The "Sign in with Google" button on the login/register
   pages will now work.

New Google sign-ins land on a **"link your account"** screen where they enter
their consumer number to connect to an existing customer record (an admin
must have added that consumer number first) - Google sign-in creates a
*login*, not a brand-new customer record, same as the regular registration
flow.

---

## 6. Setting Up Outgoing Email (optional)

Fill in `MAIL_SERVER`, `MAIL_USERNAME`, and `MAIL_PASSWORD` in `.env`. For
Gmail, use an [App Password](https://support.google.com/accounts/answer/185833),
not your normal password. Leave these blank and the "Email Bill" buttons
will show a friendly "not configured" message instead of failing silently.

---

## 7. Feature Checklist

**Public**
- Landing page, customer login/register, Google sign-in, sitemap.xml, robots.txt

**Customer Portal** (`/portal/...`)
- Dashboard with stats + consumption chart, bill list & detail with PDF
  download, email-me-a-copy, simulated "Pay Now (UPI)", consumption history,
  complaint ticketing, notifications, profile & password change

**Admin Panel** (`/admin/...`)
- Dashboard (live stats + 2 charts), customer CRUD with search/filter,
  meter readings with AJAX auto-fill, billing with one-click bulk generation
  and late-fine recalculation, payments log, complaint management, reports
  with per-customer trend + anomaly list, notification broadcast, live
  tariff editor (nothing hardcoded), admin account management, full audit
  log, database backup + CSV export per table

**Design**
- Dark/light theme (persisted, respects OS preference on first visit),
  fully responsive (off-canvas sidebar drawer + hamburger on mobile),
  self-contained (Chart.js bundled locally, hand-written SVG icon set -
  zero external CDN dependencies), toast notifications, modal dialogs

---

## 8. Running the Tests

```bash
python3 tests/test_functional.py
```

This spins up the app in-process (via Flask's test client, no server needed)
and walks through the entire real user journey - admin login, customer CRUD,
meter readings, bulk bill generation, PDF downloads, tariff editing, customer
registration and login, cross-customer access is correctly blocked, complaint
submission, self-service payment, and password changes. It deletes and
recreates `instance/abaksa.db` each time it runs, so don't run it against a
database you care about.

---

## 9. Known Limitations (worth knowing before a real launch)

- The UPI QR code on PDF bills encodes a standard `upi://pay` deep link but
  isn't wired to a real payment gateway - the customer portal's "Pay Now"
  button similarly just *simulates* a successful payment for demo purposes.
- This ships with Flask's built-in development server (`app.run()`). For a
  real deployment, put it behind a production WSGI server (gunicorn, uwsgi)
  and a reverse proxy (nginx) with HTTPS.
- SQLite is file-based and great for this scale, but isn't built for heavy
  concurrent write traffic - fine for a utility with hundreds to low
  thousands of customers, not designed for a nationwide grid operator.
- There's no CSRF token on forms yet (Flask-WTF was intentionally left out
  to keep the stack minimal) - add `Flask-WTF` if this goes to production
  with untrusted users.
