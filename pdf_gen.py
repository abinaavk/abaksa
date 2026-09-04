# pdf_gen.py
# Turns a bill (which is just a row from the database) into an actual
# PDF invoice that looks like something you'd get from a real electricity
# board, complete with a scannable UPI QR code for paying it.
# Uses the reportlab library to draw the PDF page by page, and the
# qrcode library to make the QR code image.

import os
import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

import qrcode

import config
import logic


def _pdf_currency(amount):
    # the default font reportlab uses (Helvetica) does not have the ₹
    # symbol in it - it just shows up as a black box if we try to print
    # it. So for PDFs specifically we print "Rs." instead. The GUI screens
    # still use the real ₹ symbol from logic.format_currency().
    return "Rs. " + format(amount, ",.2f")


def _upi_uri(payee_vpa, payee_name, amount, note):
    # this builds the standard "upi://pay?..." link that most UPI apps
    # in India understand - scanning the QR code we generate from this
    # link opens the payment screen with everything pre-filled
    name_for_url = payee_name.replace(" ", "%20")
    note_for_url = note.replace(" ", "%20")
    amount_str = format(amount, ".2f")
    return "upi://pay?pa=" + payee_vpa + "&pn=" + name_for_url + "&am=" + amount_str + "&cu=INR&tn=" + note_for_url


def _make_qr_image(data):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def generate_bill_pdf(bill_row, customer_row, calc_breakdown=None, output_path=None):
    # bill_row and customer_row are just rows fetched from the database
    # (see db.py) - we read fields out of them like a dictionary
    if output_path is None:
        output_path = os.path.join(config.BILLS_DIR, bill_row["bill_no"] + ".pdf")

    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    margin = 18 * mm
    y = height - margin

    # ---- Header -----------------------------------------------------
    c.setFillColor(colors.HexColor("#123A78"))
    c.rect(0, height - 30 * mm, width, 30 * mm, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, height - 14 * mm, config.UTILITY_NAME)
    c.setFont("Helvetica", 9)
    c.drawString(margin, height - 20 * mm, config.UTILITY_ADDRESS)
    c.drawString(margin, height - 25 * mm, f"Ph: {config.UTILITY_PHONE}  |  Email: {config.UTILITY_EMAIL}  |  GSTIN: {config.UTILITY_GSTIN}")

    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - margin, height - 14 * mm, "ELECTRICITY BILL")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - margin, height - 20 * mm, f"Bill No: {bill_row['bill_no']}")
    c.drawRightString(width - margin, height - 25 * mm, f"Bill Date: {bill_row['bill_date']}")

    y = height - 38 * mm

    # ---- Customer info box -------------------------------------------
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Billed To")
    y -= 6 * mm
    c.setFont("Helvetica", 10)
    info_lines = [
        f"Name: {customer_row['name']}",
        f"Consumer No: {customer_row['consumer_no']}    Meter No: {customer_row['meter_no']}",
        f"Address: {customer_row['address']}",
        f"Connection Type: {customer_row['connection_type']}    Sanctioned Load: {customer_row['sanctioned_load'] or '-'}",
    ]
    for line in info_lines:
        c.drawString(margin, y, line)
        y -= 5.5 * mm

    y -= 3 * mm
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.line(margin, y, width - margin, y)
    y -= 8 * mm

    # ---- Billing summary box ------------------------------------------
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Billing Summary")
    y -= 7 * mm

    box_left = margin
    box_right = width - margin
    row_h = 6.5 * mm

    def row(label, value, bold=False, color=colors.black):
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        c.drawString(box_left + 3 * mm, y, label)
        c.drawRightString(box_right - 3 * mm, y, value)
        y -= row_h

    c.setFillColor(colors.HexColor("#F2F4F8"))
    summary_top = y + row_h
    c.rect(box_left, y - row_h * 6.3, box_right - box_left, row_h * 6.3 + row_h, fill=True, stroke=False)
    c.setFillColor(colors.black)

    row("Units Consumed", f"{bill_row['units_consumed']:.2f} kWh", bold=True)
    row("Energy Charges", _pdf_currency(bill_row['energy_charge']))
    row("Fixed Charges", _pdf_currency(bill_row['fixed_charge']))
    row("Surcharge", _pdf_currency(bill_row['surcharge']))
    row("Tax / Duty", _pdf_currency(bill_row['tax']))
    if bill_row['subsidy']:
        row("Subsidy / Rebate", f"- {_pdf_currency(bill_row['subsidy'])}", color=colors.HexColor("#1B8A3E"))
    if bill_row['late_fine']:
        row("Late Payment Fine", _pdf_currency(bill_row['late_fine']), color=colors.HexColor("#C0392B"))

    y -= 2 * mm
    c.setStrokeColor(colors.HexColor("#999999"))
    c.line(box_left, y + row_h - 1 * mm, box_right, y + row_h - 1 * mm)

    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor("#123A78"))
    c.drawString(box_left + 3 * mm, y - 2 * mm, "TOTAL AMOUNT DUE")
    c.drawRightString(box_right - 3 * mm, y - 2 * mm, _pdf_currency(bill_row['total_amount']))
    y -= 12 * mm

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Due Date: {bill_row['due_date']}")
    status_color = colors.HexColor("#1B8A3E") if bill_row['status'] == "Paid" else colors.HexColor("#C0392B")
    c.setFillColor(status_color)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - margin, y, f"Status: {bill_row['status']}")
    y -= 12 * mm

    # ---- Slab breakdown table (if provided) ---------------------------
    if calc_breakdown:
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margin, y, "Slab-wise Energy Charge Breakdown")
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        c.drawString(margin, y, "Slab (units)")
        c.drawString(margin + 45 * mm, y, "Units Billed")
        c.drawString(margin + 85 * mm, y, "Rate (Rs./unit)")
        c.drawString(margin + 125 * mm, y, "Amount")
        y -= 4.5 * mm
        c.line(margin, y, width - margin, y)
        y -= 5 * mm
        for slab in calc_breakdown:
            c.drawString(margin, y, f"{slab['from']:.0f} - {slab['to']:.0f}")
            c.drawString(margin + 45 * mm, y, f"{slab['units']:.2f}")
            c.drawString(margin + 85 * mm, y, f"{slab['rate']:.2f}")
            c.drawString(margin + 125 * mm, y, f"{slab['amount']:.2f}")
            y -= 5 * mm
        y -= 5 * mm

    # ---- UPI QR code ----------------------------------------------------
    qr_size = 32 * mm
    qr_y = max(y - qr_size, margin + 20 * mm)
    upi_data = _upi_uri(config.UTILITY_UPI_ID, config.UTILITY_NAME, bill_row['total_amount'],
                         f"Bill {bill_row['bill_no']}")
    qr_img = _make_qr_image(upi_data)
    c.drawImage(qr_img, margin, qr_y, width=qr_size, height=qr_size)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + qr_size + 5 * mm, qr_y + qr_size - 5 * mm, "Scan to Pay via UPI")
    c.setFont("Helvetica", 8)
    c.drawString(margin + qr_size + 5 * mm, qr_y + qr_size - 10 * mm, f"UPI ID: {config.UTILITY_UPI_ID}")
    c.drawString(margin + qr_size + 5 * mm, qr_y + qr_size - 14 * mm, f"Amount: {_pdf_currency(bill_row['total_amount'])}")

    # ---- Footer --------------------------------------------------------
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor("#777777"))
    c.drawCentredString(width / 2, margin, "This is a computer-generated bill and does not require a signature.")

    c.showPage()
    c.save()
    return output_path
