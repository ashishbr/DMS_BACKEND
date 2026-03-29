"""
Vendor PO PDF Generator
-----------------------
Generates a professional purchase order PDF using ReportLab.

Layout:
  1. Header  — company name + PO number + issue date
  2. Vendor  — vendor contact block
  3. Items   — line-item table (Description | Qty | Unit Price | Total)
  4. Summary — Subtotal / Tax / Discount / Total Amount
  5. Footer  — Notes + payment terms + authorized signature line
"""
import os
from datetime import datetime
from typing import List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BRAND_DARK = colors.HexColor("#1E293B")   # slate-800
BRAND_MID = colors.HexColor("#334155")    # slate-700
BRAND_ACCENT = colors.HexColor("#3B82F6") # blue-500
BRAND_LIGHT = colors.HexColor("#F1F5F9")  # slate-100
TEXT_MUTED = colors.HexColor("#64748B")   # slate-500
WHITE = colors.white
BLACK = colors.black

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
BASE_STYLES = getSampleStyleSheet()

STYLE_H1 = ParagraphStyle(
    "H1",
    parent=BASE_STYLES["Normal"],
    fontSize=22,
    textColor=WHITE,
    fontName="Helvetica-Bold",
    alignment=TA_LEFT,
    spaceAfter=2,
)
STYLE_H1_SUB = ParagraphStyle(
    "H1Sub",
    parent=BASE_STYLES["Normal"],
    fontSize=10,
    textColor=colors.HexColor("#CBD5E1"),
    fontName="Helvetica",
    alignment=TA_LEFT,
)
STYLE_SECTION_TITLE = ParagraphStyle(
    "SectionTitle",
    parent=BASE_STYLES["Normal"],
    fontSize=9,
    textColor=TEXT_MUTED,
    fontName="Helvetica-Bold",
    spaceBefore=6,
    spaceAfter=2,
    textTransform="uppercase",
)
STYLE_BODY = ParagraphStyle(
    "Body",
    parent=BASE_STYLES["Normal"],
    fontSize=9,
    textColor=BRAND_DARK,
    fontName="Helvetica",
    leading=13,
)
STYLE_BODY_BOLD = ParagraphStyle(
    "BodyBold",
    parent=BASE_STYLES["Normal"],
    fontSize=9,
    textColor=BRAND_DARK,
    fontName="Helvetica-Bold",
)
STYLE_SMALL = ParagraphStyle(
    "Small",
    parent=BASE_STYLES["Normal"],
    fontSize=8,
    textColor=TEXT_MUTED,
    fontName="Helvetica",
    leading=11,
)
STYLE_TOTAL_LABEL = ParagraphStyle(
    "TotalLabel",
    parent=BASE_STYLES["Normal"],
    fontSize=9,
    textColor=BRAND_DARK,
    fontName="Helvetica",
    alignment=TA_RIGHT,
)
STYLE_TOTAL_VALUE = ParagraphStyle(
    "TotalValue",
    parent=BASE_STYLES["Normal"],
    fontSize=9,
    textColor=BRAND_DARK,
    fontName="Helvetica",
    alignment=TA_RIGHT,
)
STYLE_GRAND_TOTAL_LABEL = ParagraphStyle(
    "GrandTotalLabel",
    parent=BASE_STYLES["Normal"],
    fontSize=11,
    textColor=WHITE,
    fontName="Helvetica-Bold",
    alignment=TA_RIGHT,
)
STYLE_GRAND_TOTAL_VALUE = ParagraphStyle(
    "GrandTotalValue",
    parent=BASE_STYLES["Normal"],
    fontSize=11,
    textColor=WHITE,
    fontName="Helvetica-Bold",
    alignment=TA_RIGHT,
)
STYLE_FOOTER = ParagraphStyle(
    "Footer",
    parent=BASE_STYLES["Normal"],
    fontSize=8,
    textColor=TEXT_MUTED,
    fontName="Helvetica",
    alignment=TA_CENTER,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_currency(value: float, currency: str = "USD") -> str:
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}
    sym = symbols.get(currency.upper(), currency + " ")
    return f"{sym}{value:,.2f}"


def _fmt_date(dt: Optional[datetime]) -> str:
    if not dt:
        return "—"
    return dt.strftime("%B %d, %Y")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_vendor_po_pdf(
    *,
    output_path: str,
    po_number: str,
    vendor_name: str,
    vendor_address: Optional[str],
    vendor_email: Optional[str],
    vendor_phone: Optional[str],
    issue_date: Optional[datetime],
    delivery_date: Optional[datetime],
    payment_terms: Optional[str],
    line_items: List[dict],   # each: {description, quantity, unit_price, total_price}
    subtotal: float,
    tax: float,
    discount: float,
    total_amount: float,
    notes: Optional[str],
    currency: str = "USD",
    company_name: str = "EMB Global",
) -> str:
    """
    Render a Vendor PO PDF to *output_path* and return the path.

    ``line_items`` each dict must have keys:
        description, quantity, unit_price, total_price
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=10 * mm,
        bottomMargin=15 * mm,
    )

    page_w = A4[0] - 30 * mm  # usable width
    story = []

    # -----------------------------------------------------------------------
    # 1. HEADER BAND
    # -----------------------------------------------------------------------
    header_data = [[
        Paragraph(company_name, STYLE_H1),
        Paragraph(
            f"<b>PURCHASE ORDER</b><br/><font size='10' color='#CBD5E1'>#{po_number}</font>",
            ParagraphStyle("PONum", fontSize=14, textColor=WHITE,
                           fontName="Helvetica-Bold", alignment=TA_RIGHT),
        ),
    ]]
    header_table = Table(header_data, colWidths=[page_w * 0.6, page_w * 0.4])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (0, -1), 10),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 10),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # -----------------------------------------------------------------------
    # 2. META ROW — Issue Date / Delivery Date / Payment Terms
    # -----------------------------------------------------------------------
    meta_data = [[
        Paragraph("Issue Date", STYLE_SECTION_TITLE),
        Paragraph("Delivery Date", STYLE_SECTION_TITLE),
        Paragraph("Payment Terms", STYLE_SECTION_TITLE),
    ], [
        Paragraph(_fmt_date(issue_date), STYLE_BODY),
        Paragraph(_fmt_date(delivery_date), STYLE_BODY),
        Paragraph(payment_terms or "—", STYLE_BODY),
    ]]
    meta_table = Table(meta_data, colWidths=[page_w / 3] * 3)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 5 * mm))

    # -----------------------------------------------------------------------
    # 3. VENDOR DETAILS
    # -----------------------------------------------------------------------
    story.append(Paragraph("Vendor Details", STYLE_SECTION_TITLE))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
    story.append(Spacer(1, 2 * mm))

    vendor_lines = [f"<b>{vendor_name}</b>"]
    if vendor_address:
        for line in vendor_address.splitlines():
            if line.strip():
                vendor_lines.append(line.strip())
    if vendor_email:
        vendor_lines.append(f"Email: {vendor_email}")
    if vendor_phone:
        vendor_lines.append(f"Phone: {vendor_phone}")

    story.append(Paragraph("<br/>".join(vendor_lines), STYLE_BODY))
    story.append(Spacer(1, 5 * mm))

    # -----------------------------------------------------------------------
    # 4. LINE ITEMS TABLE
    # -----------------------------------------------------------------------
    story.append(Paragraph("Items", STYLE_SECTION_TITLE))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
    story.append(Spacer(1, 2 * mm))

    col_desc = page_w * 0.48
    col_qty = page_w * 0.12
    col_unit = page_w * 0.20
    col_total = page_w * 0.20

    th_style = ParagraphStyle("TH", fontSize=8, fontName="Helvetica-Bold",
                               textColor=WHITE, alignment=TA_CENTER)
    td_style = ParagraphStyle("TD", fontSize=9, fontName="Helvetica",
                               textColor=BRAND_DARK, alignment=TA_LEFT)
    td_right = ParagraphStyle("TDR", fontSize=9, fontName="Helvetica",
                               textColor=BRAND_DARK, alignment=TA_RIGHT)

    items_data = [[
        Paragraph("Description", th_style),
        Paragraph("Qty", th_style),
        Paragraph("Unit Price", th_style),
        Paragraph("Total", th_style),
    ]]
    for item in line_items:
        items_data.append([
            Paragraph(str(item.get("description", "")), td_style),
            Paragraph(str(item.get("quantity", 0)), td_right),
            Paragraph(_fmt_currency(item.get("unit_price", 0), currency), td_right),
            Paragraph(_fmt_currency(item.get("total_price", 0), currency), td_right),
        ])

    items_table = Table(
        items_data,
        colWidths=[col_desc, col_qty, col_unit, col_total],
        repeatRows=1,
    )
    row_count = len(items_data)
    items_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_ACCENT),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        # Data rows — alternating
        *[
            ("BACKGROUND", (0, r), (-1, r), BRAND_LIGHT if r % 2 == 0 else WHITE)
            for r in range(1, row_count)
        ],
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 5 * mm))

    # -----------------------------------------------------------------------
    # 5. FINANCIAL SUMMARY (right-aligned)
    # -----------------------------------------------------------------------
    summary_label_w = page_w * 0.72
    summary_value_w = page_w * 0.28

    summary_rows = [
        [Paragraph("Subtotal", STYLE_TOTAL_LABEL),
         Paragraph(_fmt_currency(subtotal, currency), STYLE_TOTAL_VALUE)],
        [Paragraph("Tax", STYLE_TOTAL_LABEL),
         Paragraph(_fmt_currency(tax, currency), STYLE_TOTAL_VALUE)],
        [Paragraph("Discount", STYLE_TOTAL_LABEL),
         Paragraph(f"(−{_fmt_currency(discount, currency)})", STYLE_TOTAL_VALUE)],
        # Grand total row
        [Paragraph("Total Amount", STYLE_GRAND_TOTAL_LABEL),
         Paragraph(_fmt_currency(total_amount, currency), STYLE_GRAND_TOTAL_VALUE)],
    ]
    summary_table = Table(summary_rows, colWidths=[summary_label_w, summary_value_w])
    summary_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 8),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, -1), (-1, -1), BRAND_DARK),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 6 * mm))

    # -----------------------------------------------------------------------
    # 6. FOOTER — Notes + Terms + Signature
    # -----------------------------------------------------------------------
    if notes:
        story.append(Paragraph("Notes", STYLE_SECTION_TITLE))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(notes, STYLE_BODY))
        story.append(Spacer(1, 4 * mm))

    if payment_terms:
        story.append(Paragraph("Terms & Conditions", STYLE_SECTION_TITLE))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(payment_terms, STYLE_SMALL))
        story.append(Spacer(1, 6 * mm))

    # Signature line
    sig_data = [[
        Paragraph("Authorized Signature", STYLE_SMALL),
        Paragraph("Date", STYLE_SMALL),
    ], [
        Paragraph("_" * 40, STYLE_SMALL),
        Paragraph("_" * 20, STYLE_SMALL),
    ]]
    sig_table = Table(sig_data, colWidths=[page_w * 0.55, page_w * 0.45])
    sig_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 8 * mm))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1")))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated by {company_name} · {datetime.now().strftime('%B %d, %Y')}",
        STYLE_FOOTER,
    ))

    doc.build(story)
    return output_path
