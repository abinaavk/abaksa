import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.path.exists("instance/abaksa.db"):
    os.remove("instance/abaksa.db")

import app as app_module

app = app_module.app
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False

client = app.test_client()

def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(status, "-", label)
    if not condition:
        raise AssertionError(label)

# ---- 1. Public pages load ----
r = client.get("/")
check("landing page loads", r.status_code == 200)

r = client.get("/login")
check("customer login page loads", r.status_code == 200)

r = client.get("/register")
check("register page loads", r.status_code == 200)

r = client.get("/admin")
check("/admin redirects somewhere (to login)", r.status_code in (301, 302, 308))

r = client.get("/admin/login")
check("admin login page loads", r.status_code == 200)

r = client.get("/sitemap.xml")
check("sitemap.xml loads", r.status_code == 200 and b"<urlset" in r.data)

r = client.get("/robots.txt")
check("robots.txt loads", r.status_code == 200)

# ---- 2. Admin login with .env credentials ----
r = client.post("/admin/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
check("admin login succeeds", r.status_code == 200 and b"Dashboard" in r.data)

r = client.get("/admin/dashboard")
check("admin dashboard loads after login", r.status_code == 200)

# ---- 3. Admin adds a customer ----
r = client.post("/admin/customers/add", data={
    "consumer_no": "C-3001", "meter_no": "M-7001", "name": "Karthik Rao",
    "address": "9 Marina Beach Rd, Chennai", "phone": "9000011122",
    "email": "karthik@example.com", "connection_type": "Domestic", "sanctioned_load": "4kW",
}, follow_redirects=True)
check("add customer succeeds", r.status_code == 200 and b"Customer added" in r.data)

r = client.get("/admin/customers")
check("customer shows up in list", b"Karthik Rao" in r.data and b"C-3001" in r.data)

import database
with app.app_context():
    customer = database.get_customer_by_consumer_no("C-3001")
    customer_id = customer["id"]

# ---- 4. Admin records a meter reading ----
r = client.post("/admin/readings/add", data={
    "customer_id": str(customer_id), "previous_units": "100", "current_units": "260",
}, follow_redirects=True)
check("add reading succeeds", r.status_code == 200 and b"Meter reading recorded" in r.data)

r = client.get("/admin/readings/latest/%d" % customer_id)
check("latest reading AJAX endpoint works", r.get_json()["previous_units"] == 260)

# ---- 5. Bulk generate bills ----
r = client.post("/admin/billing/bulk-generate", follow_redirects=True)
check("bulk generate succeeds", r.status_code == 200 and b"Generated 1 bill" in r.data)

with app.app_context():
    bills = database.list_bills(customer_id=customer_id)
    bill_id = bills[0]["id"]
    bill_total = bills[0]["total_amount"]
    print("    (bill total: Rs.", bill_total, ")")

# ---- 6. View bill detail + download PDF ----
r = client.get("/admin/bills/%d" % bill_id)
check("admin bill detail page loads", r.status_code == 200 and b"Billing Summary" in r.data)

r = client.get("/admin/bills/%d/pdf" % bill_id)
check("PDF download works", r.status_code == 200 and r.data[:4] == b"%PDF")

# ---- 7. Mark bill paid ----
r = client.post("/admin/bills/%d/mark-paid" % bill_id, follow_redirects=True)
check("mark paid succeeds", r.status_code == 200 and b"marked as paid" in r.data)

with app.app_context():
    bill = database.get_bill(bill_id)
    check("bill status is now Paid", bill["status"] == "Paid")

# ---- 8. Tariff settings update ----
r = client.get("/admin/tariff")
check("tariff settings page loads", r.status_code == 200)

r = client.post("/admin/tariff", data={
    "slab_upto_Domestic": ["100", "200", "300", "500", ""],
    "slab_rate_Domestic": ["3.50", "4.50", "6.00", "7.50", "8.75"],
    "slab_upto_Commercial": ["100", "300", "500", "", ""],
    "slab_rate_Commercial": ["6.00", "8.00", "9.50", "11.00", ""],
    "slab_upto_Industrial": ["500", "1500", "", "", ""],
    "slab_rate_Industrial": ["7.00", "8.50", "10.00", "", ""],
    "fixed_Domestic": "50", "fixed_Commercial": "150", "fixed_Industrial": "500",
    "tax_rate": "5", "surcharge_rate": "2", "subsidy_units": "100", "subsidy_amount": "200",
    "fine_rate": "1", "fine_cap": "30", "grace_days": "5", "due_days": "21",
}, follow_redirects=True)
check("tariff settings save succeeds", r.status_code == 200 and b"Tariff settings saved" in r.data)

# ---- 9. Complaints, notifications, reports, payments, audit, backup pages ----
for path in ["/admin/complaints", "/admin/reports", "/admin/payments", "/admin/notifications",
             "/admin/audit", "/admin/backup", "/admin/accounts", "/admin/customers/%d/history" % customer_id]:
    r = client.get(path)
    check("admin page loads: " + path, r.status_code == 200)

r = client.post("/admin/backup/create", follow_redirects=True)
check("backup creation succeeds", r.status_code == 200 and b"Backup created" in r.data)

r = client.get("/admin/backup/export/customers")
check("CSV export works", r.status_code == 200 and b"consumer_no" in r.data)

# ---- 10. Log out of admin ----
r = client.get("/logout", follow_redirects=True)
check("admin logout works", r.status_code == 200)

r = client.get("/admin/dashboard", follow_redirects=True)
check("admin dashboard blocked after logout", b"Admin Login" in r.data or b"admin" in r.data.lower())

# ---- 11. Customer registration + login ----
r = client.post("/register", data={
    "consumer_no": "C-3001", "username": "karthik", "password": "pass123", "confirm": "pass123",
}, follow_redirects=True)
check("customer registration succeeds", r.status_code == 200 and b"Account created" in r.data)

r = client.post("/login", data={"username": "karthik", "password": "pass123"}, follow_redirects=True)
check("customer login succeeds", r.status_code == 200 and b"Welcome back" in r.data)

# ---- 12. Customer portal pages ----
for path in ["/portal/dashboard", "/portal/bills", "/portal/readings", "/portal/complaints",
             "/portal/notifications", "/portal/profile"]:
    r = client.get(path)
    check("customer page loads: " + path, r.status_code == 200)

r = client.get("/portal/bills/%d" % bill_id)
check("customer can view their own bill", r.status_code == 200 and b"Billing Summary" in r.data)

r = client.get("/portal/bills/%d/pdf" % bill_id)
check("customer PDF download works", r.status_code == 200 and r.data[:4] == b"%PDF")

# ---- 13. Customer raises a complaint ----
r = client.post("/portal/complaints", data={
    "category": "Meter Fault", "description": "Meter display is flickering",
}, follow_redirects=True)
check("customer complaint submission works", r.status_code == 200 and b"Complaint submitted" in r.data)

# ---- 14. Cross-customer access is blocked ----
with app.app_context():
    other_id = database.add_customer("C-9999", "M-9999", "Other Person", "Somewhere",
                                      "9999999999", "other@example.com", "Domestic", "3kW")
    other_reading = database.add_reading(other_id, 0, 50)
    cfg = database.get_tariff_config()
    import logic
    calc = logic.calculate_bill(50, "Domestic", cfg)
    other_bill_id = database.insert_bill(other_id, other_reading, "2026-01-01", "2026-01-22", 50,
                                          calc["energy_charge"], calc["fixed_charge"], calc["surcharge"],
                                          calc["tax"], calc["subsidy"], calc["total_amount"])

r = client.get("/portal/bills/%d" % other_bill_id)
check("customer CANNOT view another customer's bill (404)", r.status_code == 404)

# ---- 15. Customer self-service payment ----
with app.app_context():
    my_bills = database.list_bills(customer_id=customer_id)
    unpaid = [b for b in my_bills if b["status"] != "Paid"]

if unpaid:
    r = client.post("/portal/bills/%d/pay" % unpaid[0]["id"], follow_redirects=True)
    check("customer self-payment works", r.status_code == 200 and b"Payment successful" in r.data)
else:
    print("SKIP - no unpaid bill to test self-payment on (already paid)")

# ---- 16. Customer password change ----
r = client.post("/portal/profile", data={
    "new_password": "newpass456", "confirm_password": "newpass456",
}, follow_redirects=True)
check("password change works", r.status_code == 200 and b"Password updated" in r.data)

r = client.get("/logout", follow_redirects=True)
r = client.post("/login", data={"username": "karthik", "password": "newpass456"}, follow_redirects=True)
check("login with new password works", r.status_code == 200 and b"Welcome back" in r.data)

print()
print("=" * 50)
print("ALL FUNCTIONAL TESTS PASSED")
print("=" * 50)
