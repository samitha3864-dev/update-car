from flask import Flask, render_template, request, jsonify, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from pathlib import Path
from datetime import datetime, date as date_type
from calendar import month_name
import json
import re
import threading
import difflib
import shutil
import tempfile
import zipfile
import os
import uuid
from io import BytesIO
from docx import Document
from docx.shared import Inches, Pt, RGBColor

try:
    import pypdf
except ImportError:
    pypdf = None

class app(Flask):
    """Concrete application wrapper with the workbook/data setup the project needs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config.setdefault("JSON_SORT_KEYS", False)
        self.config.setdefault("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
        self._ready = False

    def create_app(self):
        """Return the configured application instance."""
        self.config.setdefault("APP_NAME", "Car Accessories Professional")
        return self

    def initialize(self):
        """Ensure the catalog file and Excel workbook exist before handling requests."""
        if self._ready:
            return self
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not DATA_FILE.exists():
            save_data(default_data())
        ensure_excel()
        # Apply category colours to existing monthly sheets once at startup too.
        try:
            wb = _load_workbook_safe()
            changed = False
            for ws in wb.worksheets:
                if ws.max_row >= 2 and clean_name(ws.cell(1, 1).value).casefold() == "date":
                    style_headers(ws, total_amount_column(ws))
                    style_existing_priority_rows(ws)
                    changed = True
            if changed:
                save_workbook_atomic(wb)
            wb.close()
        except Exception as exc:
            print("Could not refresh Excel category colours:", exc)
        self._ready = True
        return self

    def load_data(self):
        """Read the catalog payload using the shared normalizer."""
        return load_data()

    def save_data(self, data):
        """Persist catalog data using the app data directory."""
        save_data(data)

    def ensure_workbook(self):
        """Ensure the working Excel file is readable and ready for use."""
        ensure_excel()
        return EXCEL_FILE


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "website_data.json"
EXCEL_FILE = DATA_DIR / "products.xlsx"
# If the old products.xlsx is corrupted/locked, the app can use this clean
# working workbook instead of repeatedly trying to replace the locked file.
WORKING_EXCEL_FILE = DATA_DIR / "products_working.xlsx"

MONTHS = [month_name[i] for i in range(1, 13)]
_WORKBOOK_SAVE_LOCK = threading.RLock()

app = app(__name__)
app.create_app()

DEFAULT_CATEGORIES = [
    "Seat Cover", "Floor Mat / Mat", "Rubber Coating", "Interior Rubber Coating",
    "Steering Cover", "Sunfilm", "Door Visor", "Wheel Cup", "Mud Flap",
    "Skin / Sponge / Foamcoat", "Anti Chikmat / Perfume", "Horn", "Fog Lamp",
    "Cleaning / Interior-Exterior Service", "Other"
]

DEFAULT_PRODUCTS = {
    "Seat Cover": ["seat cover"],
    "Floor Mat / Mat": ["IXF Mat", "Floor Mat", "Engine Mat", "Noodies Mat"],
    "Rubber Coating": ["Rubber Coating"],
    "Interior Rubber Coating": ["Interior Rubber Coating"],
    "Steering Cover": ["Steering Cover"],
    "Sunfilm": ["Sunfilm", "Side Ceramic Shield", "Front Ceramic Shield"],
    "Door Visor": ["Door Visor"],
    "Wheel Cup": ["Wheel Cup"],
    "Mud Flap": ["Mud Flap", "Mud Flap OE", "Mud Flap Rubbee"],
    "Skin / Sponge / Foamcoat": ["Skin / Sponge / Foamcoat", "Cloth", "Double Side Cloth"],
    "Anti Chikmat / Perfume": ["Anti Chikmat", "Car Perfume"],
    "Horn": ["Roots Horn", "Rev. Horn"],
    "Fog Lamp": ["Fog Lamp", "Fog Lamp Toreto Harmo 120W", "HIL Bulb 180W"],
    "Cleaning / Interior-Exterior Service": [
        "Door Clean", "Interior Cleaning", "Exterior Cleaning", "Rubbing Polish",
        "Teflon Polish", "H/C Doom Polish", "Alignment", "Electrician Labour"
    ],
    "Other": []
}


def clean_name(value):
    return " ".join(str(value or "").strip().split())


def norm(value):
    return clean_name(value).casefold()


# Product names / aliases used for automatic category detection.
PRODUCT_KEYWORDS = {
    "Seat Cover": ["seat cover", "pattern seat cover", "design seat cover", "seat cover clamp"],
    "Floor Mat / Mat": ["ixf mat", "floor mat", "other floor mat", "engine mat", "noodies mat"],
    "Rubber Coating": ["rubber coating"],
    "Interior Rubber Coating": ["interior rubber coating"],
    "Steering Cover": ["steering cover"],
    "Sunfilm": ["sunfilm", "other sunfilm", "ceramic shield", "side ceramic shield", "front ceramic shield"],
    "Door Visor": ["door visor"],
    "Wheel Cup": ["wheel cup"],
    "Mud Flap": ["mud flap", "mud flap oe", "mud flap rubbee"],
    "Skin / Sponge / Foamcoat": ["skin", "sponge", "foamcoat", "double side cloth"],
    "Anti Chikmat / Perfume": ["anti chikmat", "perfume", "car perfume"],
    "Horn": ["roots horn", "rev horn", "other horn", "horn"],
    "Fog Lamp": ["fog lamp", "led fog", "fog light", "hil bulb"],
    "Cleaning / Interior-Exterior Service": [
        "door clean", "interior cleaning", "exterior cleaning", "rubbing polish",
        "teflon polish", "h/c doom polish", "alignment", "electrician labour",
        "labour", "labor", "cleaning", "interior service", "exterior service"
    ],
}


def detect_product_category(product):
    """Find exact saved products first, then a clear keyword match.

    Custom products become automatically recognizable after they are saved in
    the catalogue. If keywords point to more than one category, return None so
    the UI asks the user instead of assigning a potentially wrong category.
    """
    product_key = norm(product)
    if not product_key:
        return None

    data = load_data()
    categories = data.get("categories", [])
    products = data.get("products", {})

    # Exact match in the live catalogue, including custom categories/products.
    for category in categories:
        for saved_product in products.get(category, []):
            if norm(saved_product) == product_key:
                return category

    # Keep only keyword categories that currently exist in the live catalogue.
    category_lookup = {norm(category): category for category in categories}
    matches = []
    matched_lengths = []
    for category_name, keywords in PRODUCT_KEYWORDS.items():
        actual_category = category_lookup.get(norm(category_name))
        if not actual_category:
            continue
        for keyword in keywords:
            key = norm(keyword)
            if not key:
                continue
            # Match complete phrase within the typed product name.
            if product_key == key or key in product_key:
                matches.append(actual_category)
                matched_lengths.append(len(key))

    if not matches:
        return None

    # Prefer the most specific phrase (e.g. "interior rubber coating" over
    # "rubber coating"). If equally specific phrases point to different
    # categories, ask the user to choose instead of guessing.
    longest = max(matched_lengths)
    best = {category for category, length in zip(matches, matched_lengths) if length == longest}
    return next(iter(best)) if len(best) == 1 else None


def default_data():
    return {"categories": DEFAULT_CATEGORIES[:], "products": {k: v[:] for k, v in DEFAULT_PRODUCTS.items()}, "settings": {"priority_color": "#fff2cc", "priority_text_color": "#7f6000"}}


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def normalize_data(data):
    changed = False
    if not isinstance(data, dict):
        data, changed = default_data(), True
    categories = data.get("categories") if isinstance(data.get("categories"), list) else []
    products = data.get("products") if isinstance(data.get("products"), dict) else {}
    if not categories:
        categories = DEFAULT_CATEGORIES[:]
        changed = True
    cleaned_categories, seen_categories = [], set()
    for category in categories:
        category = clean_name(category)
        key = norm(category)
        if not category or key in seen_categories:
            changed = True
            continue
        seen_categories.add(key)
        cleaned_categories.append(category)
    final_products = {}
    for category in cleaned_categories:
        source = None
        if category in products and isinstance(products[category], list):
            source = products[category]
        else:
            for old_category, values in products.items():
                if norm(old_category) == norm(category) and isinstance(values, list):
                    source = values
                    break
        if source is None:
            source = DEFAULT_PRODUCTS.get(category, [])[:]
            changed = True
        if not source and category in DEFAULT_PRODUCTS and DEFAULT_PRODUCTS[category]:
            source = DEFAULT_PRODUCTS[category][:]
            changed = True
        out, seen_products = [], set()
        for product in source:
            product = clean_name(product)
            key = norm(product)
            if not product or key in seen_products:
                changed = True
                continue
            seen_products.add(key)
            out.append(product)
        final_products[category] = out
        if len(out) != len(source):
            changed = True
    if set(products.keys()) != set(final_products.keys()):
        changed = True
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
    priority_color = clean_name(settings.get("priority_color")) or "#fff2cc"
    priority_text_color = clean_name(settings.get("priority_text_color")) or "#7f6000"
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", priority_color):
        priority_color = "#fff2cc"; changed = True
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", priority_text_color):
        priority_text_color = "#7f6000"; changed = True
    result = {"categories": cleaned_categories, "products": final_products, "settings": {"priority_color": priority_color, "priority_text_color": priority_text_color}}
    return result, changed


def load_data():
    if not DATA_FILE.exists():
        data = default_data()
        save_data(data)
        return data
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        raw = default_data()
    data, changed = normalize_data(raw)
    if changed:
        save_data(data)
    return data


def product_headers(data):
    return [(category, product) for category in data["categories"] for product in data["products"].get(category, [])]


def style_headers(ws, total_col):
    # Stable category colours: the same category keeps the same colour in every month sheet.
    palette = [
        ("C2410C", "FFEDD5"), ("047857", "D1FAE5"), ("7C3AED", "EDE9FE"),
        ("0369A1", "E0F2FE"), ("BE123C", "FFE4E6"), ("A16207", "FEF3C7"),
        ("4338CA", "E0E7FF"), ("0F766E", "CCFBF1"), ("9D174D", "FCE7F3"),
        ("4D7C0F", "ECFCCB"), ("6D28D9", "F3E8FF"), ("B45309", "FFEDD5"),
        ("1D4ED8", "DBEAFE"), ("475569", "E2E8F0"), ("334155", "F1F5F9")
    ]
    category_colors = {}
    idx = 0
    for col in range(5, total_col):
        cat = clean_name(ws.cell(1, col).value)
        if cat and cat != "Total Amount":
            if cat not in category_colors:
                category_colors[cat] = palette[idx % len(palette)]
                idx += 1
    thin = Side(style="thin", color="B7B7B7")
    for col in range(1, total_col + 1):
        top = ws.cell(1, col)
        sub = ws.cell(2, col)
        top_cat = clean_name(top.value)
        if col < 5 or top_cat == "Total Amount":
            top.fill = PatternFill("solid", fgColor="1F4E78")
            sub.fill = PatternFill("solid", fgColor="D9EAF7")
            top.font = Font(bold=True, color="FFFFFF")
        else:
            # For merged category cells, the category name lives in the first cell only.
            cat = top_cat
            if not cat:
                for candidate, colors in category_colors.items():
                    if col >= 5 and candidate in category_colors:
                        # Infer category from the nearest preceding category header.
                        pass
            colors = category_colors.get(cat)
            if colors:
                top.fill = PatternFill("solid", fgColor=colors[0])
                top.font = Font(bold=True, color="FFFFFF")
                sub.fill = PatternFill("solid", fgColor=colors[1])
            else:
                sub.fill = PatternFill("solid", fgColor="D9EAF7")
                top.fill = PatternFill("solid", fgColor="1F4E78")
                top.font = Font(bold=True, color="FFFFFF")
        for cell in (top, sub):
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    # Colour product subheaders according to the merged category band above them.
    current_category = ""
    for col in range(5, total_col):
        if clean_name(ws.cell(1, col).value):
            current_category = clean_name(ws.cell(1, col).value)
        colors = category_colors.get(current_category)
        if colors:
            ws.cell(2, col).fill = PatternFill("solid", fgColor=colors[1])
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 48
    for col, width in {1: 14, 2: 24, 3: 18, 4: 20}.items():
        ws.column_dimensions[get_column_letter(col)].width = width
    for col in range(5, total_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22


def make_sheet(wb, sheet_name, data):
    if sheet_name in wb.sheetnames:
        return wb[sheet_name]
    ws = wb.create_sheet(sheet_name)
    fixed = ["Date", "Customer Name", "Mobile Number", "Vehicle Number"]
    headers = product_headers(data)
    total_col = 5 + len(headers)
    for col, title in enumerate(fixed, 1):
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        ws.cell(1, col).value = title
    col = 5
    for category in data["categories"]:
        products = data["products"].get(category, [])
        if not products:
            continue
        start, end = col, col + len(products) - 1
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=end)
        ws.cell(1, start).value = category
        for product in products:
            ws.cell(2, col).value = product
            col += 1
    ws.merge_cells(start_row=1, start_column=total_col, end_row=2, end_column=total_col)
    ws.cell(1, total_col).value = "Total Amount"
    style_headers(ws, total_col)
    ws.freeze_panes = "E3"
    return ws


def make_workbook(data):
    wb = Workbook()
    ws = wb.active
    ws.title = "Customer Entries"
    # Legacy sheet is intentionally kept for old data. New records go to month sheets.
    make_sheet(wb, "Customer Entries", data)
    return wb, ws


def total_amount_column(ws):
    """Return the real Total Amount column, even if formatting left blank columns after it."""
    for col in range(1, ws.max_column + 1):
        if norm(ws.cell(1, col).value) == norm("Total Amount"):
            return col
    return ws.max_column


def excel_product_columns(ws):
    lookup = []
    current_category = ""
    total_col = total_amount_column(ws)
    for col in range(5, total_col):
        category_value = ws.cell(1, col).value
        if category_value not in (None, ""):
            text = clean_name(category_value)
            if norm(text) != norm("Total Amount"):
                current_category = text
        product = clean_name(ws.cell(2, col).value)
        if not product:
            continue
        lookup.append((col, current_category or "Other", product))
    return lookup


def parse_date(value, fallback=None):
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    if isinstance(value, date_type):
        return value.strftime("%d-%m-%Y")
    text = clean_name(value)
    if text:
        for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
            except ValueError:
                pass
    if fallback:
        return fallback
    return ""


def date_obj(value):
    try:
        return datetime.strptime(parse_date(value), "%d-%m-%Y")
    except Exception:
        return datetime.max


def month_for_date(value):
    parsed = parse_date(value)
    try:
        month_number = datetime.strptime(parsed, "%d-%m-%Y").month
        return month_name[month_number]
    except Exception:
        return None


def month_sheet_name(value):
    m = month_for_date(value)
    return m or "Other"


def safe_value(value):
    value = clean_name(value)
    return value if value else "nil"


def numeric_quantity(value):
    if value in (None, "", 0, "0", 0.0):
        return 0
    try:
        return float(value)
    except Exception:
        return 0


def add_missing_catalog_items(items):
    """Add imported product/category names to the website catalogue without deleting anything."""
    data = load_data()
    changed = False
    for category, product in items:
        category = clean_name(category) or "Other"
        product = clean_name(product)
        actual_cat = next((c for c in data["categories"] if norm(c) == norm(category)), None)
        if not actual_cat:
            data["categories"].append(category)
            data["products"][category] = []
            actual_cat = category
            changed = True
        if product and not any(norm(p) == norm(product) for p in data["products"].get(actual_cat, [])):
            data["products"].setdefault(actual_cat, []).append(product)
            changed = True
    if changed:
        save_data(data)
    return data, changed


def read_sheet_rows(ws, sheet_name):
    product_columns = excel_product_columns(ws)
    catalog = load_data()
    catalog_map = {}
    for cat in catalog.get("categories", []):
        for prod in catalog.get("products", {}).get(cat, []):
            catalog_map.setdefault(norm(prod), cat)
    rows = []
    for row in range(3, ws.max_row + 1):
        vals = [ws.cell(row, c).value for c in range(1, min(5, ws.max_column) + 1)]
        if all(v in (None, "") for v in vals):
            continue
        date_value = parse_date(ws.cell(row, 1).value)
        name = ws.cell(row, 2).value or "nil"
        mobile = ws.cell(row, 3).value or "nil"
        vehicle = ws.cell(row, 4).value or "nil"
        products = []
        for col, category, product in product_columns:
            q = numeric_quantity(ws.cell(row, col).value)
            if q:
                category = category or catalog_map.get(norm(product), "Other")
                products.append({"category": category, "product": product, "quantity": q})
        total = ws.cell(row, total_amount_column(ws)).value or 0
        rows.append({
            "excel_row": row,
            "sheet": sheet_name,
            "date": date_value,
            "name": name,
            "mobile": mobile,
            "vehicle": vehicle,
            "total_amount": total,
            "products": products
        })
    return rows


def read_all_rows():
    try:
        ensure_excel()
        wb = _load_workbook_safe()
        rows = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            if ws.max_row < 3 or clean_name(ws.cell(1, 1).value).casefold() != "date":
                continue
            rows.extend(read_sheet_rows(ws, sheet_name))
        wb.close()
        rows.sort(key=lambda x: (date_obj(x.get("date")), x.get("excel_row", 0)))
        return rows
    except Exception as exc:
        print("Excel read error:", exc)
        return []


def read_existing_rows():
    # Backward-compatible name used by older code/workflows.
    return read_all_rows()


def rebuild_excel_preserving_rows(rows=None):
    """Rebuild after catalogue changes, preserving customer rows and remapping product columns."""
    old_rows = rows if rows is not None else read_all_rows()
    data = load_data()
    wb = Workbook()
    wb.remove(wb.active)
    make_sheet(wb, "Customer Entries", data)
    # Preserve monthly sheets for all existing records.
    for record in old_rows:
        target = month_sheet_name(record.get("date"))
        if target == "Other":
            target = "Customer Entries"
        if target not in wb.sheetnames:
            make_sheet(wb, target, data)
        append_record_to_sheet(wb[target], record, data)
    reorder_sheets(wb)
    save_workbook_atomic(wb)


def _fresh_core_properties_xml():
    # Minimal valid Office Open XML core-properties file.
    now = datetime.now().isoformat(timespec="seconds")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:creator>Car Accessories Professional</dc:creator>
<cp:lastModifiedBy>Car Accessories Professional</cp:lastModifiedBy>
<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>""".encode("utf-8")


def _xlsx_is_readable(path):
    try:
        if not path.exists() or path.stat().st_size < 100:
            return False
        wb = load_workbook(path, read_only=True, data_only=True)
        wb.close()
        return True
    except Exception:
        return False


def use_safe_working_excel():
    """Switch this app process to a separate workbook if products.xlsx is damaged.
    This avoids WinError 5 when Windows has the damaged file locked."""
    global EXCEL_FILE

    if _xlsx_is_readable(EXCEL_FILE):
        return EXCEL_FILE

    if _xlsx_is_readable(WORKING_EXCEL_FILE):
        EXCEL_FILE = WORKING_EXCEL_FILE
        print(f"Using safe working workbook: {EXCEL_FILE}")
        return EXCEL_FILE

    # Do not try os.replace()/delete on a possibly locked corrupt workbook.
    # Create a brand-new workbook under a different filename.
    wb, _ = make_workbook(load_data())
    save_path = WORKING_EXCEL_FILE
    temp = DATA_DIR / f".products_working_{uuid.uuid4().hex}.xlsx"
    wb.save(temp)
    wb.close()
    os.replace(temp, save_path)
    EXCEL_FILE = save_path
    print(f"Created safe working workbook: {EXCEL_FILE}")
    return EXCEL_FILE


def repair_corrupt_xlsx():
    """Try to repair an XLSX whose ZIP contains one or more bad CRC entries.

    The workbook is copied to a timestamped backup first. Healthy ZIP entries
    are preserved. A damaged docProps/core.xml is replaced with a fresh valid
    core-properties file. If another entry is unreadable, it is skipped and
    the workbook is still tested with openpyxl before being accepted.
    """
    if not EXCEL_FILE.exists():
        return False, "Excel file does not exist."

    backup = EXCEL_FILE.with_name(
        f"{EXCEL_FILE.stem}_corrupt_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{EXCEL_FILE.suffix}"
    )
    shutil.copy2(EXCEL_FILE, backup)

    temp = EXCEL_FILE.with_name(f".{EXCEL_FILE.stem}_repair_{uuid.uuid4().hex}.xlsx")
    skipped = []

    try:
        with zipfile.ZipFile(EXCEL_FILE, "r") as zin, zipfile.ZipFile(
            temp, "w", compression=zipfile.ZIP_DEFLATED
        ) as zout:
            for info in zin.infolist():
                name = info.filename

                if name == "docProps/core.xml":
                    zout.writestr(info, _fresh_core_properties_xml())
                    continue

                try:
                    data = zin.read(info)
                except (zipfile.BadZipFile, EOFError, OSError, RuntimeError) as exc:
                    skipped.append(f"{name}: {exc}")
                    continue

                # Do not copy stale ZIP compression metadata.
                zout.writestr(name, data)

        # Validate the repaired workbook before replacing the original.
        test_wb = load_workbook(temp, read_only=False, data_only=False)
        test_wb.close()

        # Keep the original corrupt file as a backup and install the repaired one.
        os.replace(temp, EXCEL_FILE)

        msg = f"Excel repaired successfully. Backup: {backup.name}"
        if skipped:
            msg += " Skipped damaged ZIP entries: " + ", ".join(skipped)
        return True, msg

    except Exception as exc:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"Automatic Excel repair failed: {exc}. Backup kept at {backup.name}"


def _load_workbook_safe():
    global EXCEL_FILE
    ensure_excel()
    try:
        return load_workbook(EXCEL_FILE)
    except (zipfile.BadZipFile, OSError, EOFError):
        # The original workbook may be damaged or locked. Do not replace it.
        use_safe_working_excel()
        return load_workbook(EXCEL_FILE)

def save_workbook_atomic(wb):
    """Save atomically; if Windows locks products.xlsx, switch to a safe working workbook."""
    global EXCEL_FILE
    temp = EXCEL_FILE.with_name(f".{EXCEL_FILE.stem}_save_{uuid.uuid4().hex}.xlsx")
    try:
        wb.save(temp)
        check = load_workbook(temp, read_only=True, data_only=False)
        check.close()
        try:
            os.replace(temp, EXCEL_FILE)
        except PermissionError:
            # Windows cannot replace an XLSX currently opened by Excel/another process.
            # Preserve the saved workbook under a separate filename instead of failing the request.
            fallback = WORKING_EXCEL_FILE if WORKING_EXCEL_FILE != EXCEL_FILE else DATA_DIR / f"products_working_saved_{uuid.uuid4().hex[:8]}.xlsx"
            try:
                os.replace(temp, fallback)
            except PermissionError:
                fallback = DATA_DIR / f"products_working_saved_{uuid.uuid4().hex[:8]}.xlsx"
                os.replace(temp, fallback)
            EXCEL_FILE = fallback
            print(f"Workbook file was locked; continuing with safe workbook: {EXCEL_FILE}")
    finally:
        try:
            temp.unlink(missing_ok=True)
        except Exception:
            pass


def ensure_excel():
    global EXCEL_FILE

    if _xlsx_is_readable(EXCEL_FILE):
        return

    # Never attempt to replace/delete a locked corrupt products.xlsx here.
    # Switch to a separate working workbook.
    use_safe_working_excel()


def is_priority_customer(record):
    """Highlight customers who purchased Sunfilm or Seat Cover (same colour)."""
    for item in record.get("products", []):
        category = norm(item.get("category"))
        product = norm(item.get("product"))
        if "sunfilm" in category or "sunfilm" in product or "seat cover" in category or "seat cover" in product:
            try:
                if float(item.get("quantity") or 0) > 0:
                    return True
            except Exception:
                return True
    return False


def apply_priority_row_style(ws, row_number, record):
    if not is_priority_customer(record):
        return
    settings = load_data().get("settings", {})
    fill = PatternFill("solid", fgColor=settings.get("priority_color", "#fff2cc").lstrip("#").upper())
    font = Font(color=settings.get("priority_text_color", "#7f6000").lstrip("#").upper())
    for cell in ws[row_number]:
        cell.fill = fill
        cell.font = font


def style_existing_priority_rows(ws):
    """Apply the same highlight to existing Excel rows containing Seat Cover/Sunfilm."""
    if ws.max_row < 3 or clean_name(ws.cell(1, 1).value).casefold() != "date":
        return
    headers = excel_product_columns(ws)
    for row_num in range(3, ws.max_row + 1):
        products = []
        for col, category, product in headers:
            quantity = ws.cell(row_num, col).value
            try:
                has_quantity = float(quantity or 0) > 0
            except Exception:
                has_quantity = False
            if has_quantity:
                products.append({"category": category, "product": product, "quantity": quantity})
        record = {"products": products}
        if is_priority_customer(record):
            settings = load_data().get("settings", {})
            fill = PatternFill("solid", fgColor=settings.get("priority_color", "#fff2cc").lstrip("#").upper())
            font = Font(color=settings.get("priority_text_color", "#7f6000").lstrip("#").upper())
            for cell in ws[row_num]:
                cell.fill = fill
                cell.font = font


def append_record_to_sheet(ws, record, data):
    headers = product_headers(data)
    lookup = {(norm(c), norm(p)): 5 + i for i, (c, p) in enumerate(headers)}
    row = [record.get("date", ""), record.get("name", "nil"), record.get("mobile", "nil"), record.get("vehicle", "nil")]
    row += [0] * len(headers)
    row += [record.get("total_amount") or 0]
    for item in record.get("products", []):
        key = (norm(item.get("category")), norm(item.get("product")))
        if key in lookup:
            row[lookup[key] - 1] = item.get("quantity", 0)
    ws.append(row)
    for cell in ws[ws.max_row]:
        cell.alignment = Alignment(horizontal="center", vertical="center")
    apply_priority_row_style(ws, ws.max_row, record)
    return ws.max_row


def reorder_sheets(wb):
    order = {"Customer Entries": -1}
    for i, m in enumerate(MONTHS):
        order[m] = i
    wb._sheets.sort(key=lambda ws: order.get(ws.title, 100))


def sync_sheet_to_catalog(ws, data):
    """Rebuild a month sheet's product columns to match the current catalogue.

    Product columns can be added to the catalogue after a month sheet already
    exists. Without this sync, append_record_to_sheet writes new product values
    into old column positions (for example, a new product can appear as Engine
    Mat). Preserve existing rows by mapping values using their old category and
    product headers before rebuilding the columns.
    """
    if ws.max_row < 2 or norm(ws.cell(1, 1).value) != norm("Date"):
        make_sheet(ws.parent, ws.title, data)
        return

    old_product_columns = excel_product_columns(ws)
    old_total_col = total_amount_column(ws)
    old_rows = []
    for row_num in range(3, ws.max_row + 1):
        values = {(norm(category), norm(product)): ws.cell(row_num, col).value
                  for col, category, product in old_product_columns}
        old_rows.append((
            [ws.cell(row_num, col).value for col in range(1, 5)],
            values,
            ws.cell(row_num, old_total_col).value,
        ))

    # Remove merged header ranges before writing a fresh, catalogue-aligned header.
    for merged in list(ws.merged_cells.ranges):
        ws.unmerge_cells(str(merged))
    max_col = max(ws.max_column, old_total_col, 5 + len(product_headers(data)))
    for row_num in range(1, ws.max_row + 1):
        for col in range(1, max_col + 1):
            if row_num <= 2 or col >= 5:
                ws.cell(row_num, col).value = None

    fixed = ["Date", "Customer Name", "Mobile Number", "Vehicle Number"]
    for col, title in enumerate(fixed, 1):
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        ws.cell(1, col).value = title

    col = 5
    for category in data["categories"]:
        products = data["products"].get(category, [])
        if not products:
            continue
        start, end = col, col + len(products) - 1
        if end > start:
            ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=end)
        ws.cell(1, start).value = category
        for product in products:
            ws.cell(2, col).value = product
            col += 1
    total_col = col
    ws.merge_cells(start_row=1, start_column=total_col, end_row=2, end_column=total_col)
    ws.cell(1, total_col).value = "Total Amount"

    current_headers = product_headers(data)
    new_lookup = {(norm(category), norm(product)): 5 + index
                  for index, (category, product) in enumerate(current_headers)}
    for offset, (fixed_values, old_values, total_value) in enumerate(old_rows, start=3):
        for col_num, value in enumerate(fixed_values, 1):
            ws.cell(offset, col_num).value = value
        for key, value in old_values.items():
            if key in new_lookup:
                ws.cell(offset, new_lookup[key]).value = value
        ws.cell(offset, total_col).value = total_value

    style_headers(ws, total_col)
    ws.freeze_panes = "E3"


def ensure_month_sheet(wb, month):
    data = load_data()
    if month not in MONTHS:
        raise ValueError("Invalid month")
    if month not in wb.sheetnames:
        make_sheet(wb, month, data)
    ws = wb[month]
    sync_sheet_to_catalog(ws, data)
    reorder_sheets(wb)
    return wb[month]


def valid_date(value):
    value = clean_name(value) or datetime.now().strftime("%d-%m-%Y")
    parsed = parse_date(value)
    if not parsed:
        raise ValueError("Date must be in DD-MM-YYYY format. Example: 15-09-2026")
    return parsed


def find_record_sheet_row(sheet, row):
    if not EXCEL_FILE.exists():
        return None, None
    wb = _load_workbook_safe()
    if sheet not in wb.sheetnames:
        wb.close(); return None, None
    ws = wb[sheet]
    if row < 3 or row > ws.max_row:
        wb.close(); return None, None
    return wb, ws



@app.route("/image-import")
def image_import():
    return render_template("image_import.html")

@app.route("/excel-import")
def excel_import_page():
    return render_template("excel_import.html")

@app.route("/word-import")
def word_import_page():
    return render_template("word_import.html")

@app.route("/products")
def products_page():
    return render_template("products.html")

@app.route("/settings")
def settings_page():
    return render_template("settings.html")

@app.route("/analytics")
def analytics_page():
    return render_template("analytics.html")


def parse_uploaded_excel(upload):
    """Read both this app's category-column workbook and ordinary row-based Excel files."""
    if not upload or not upload.filename or not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Please select an .xlsx or .xlsm Excel file.")
    raw = upload.read()
    if not raw:
        raise ValueError("The selected Excel file is empty.")
    source = None
    try:
        source = load_workbook(BytesIO(raw), data_only=True, read_only=False)
        imported, catalog_items = [], []
        catalog = load_data()
        catalog_lookup = {norm(product): category for category in catalog.get("categories", [])
                          for product in catalog.get("products", {}).get(category, [])}

        def header_key(value):
            return norm(value).replace("_", " ").replace("-", " ")

        aliases = {
            "date": {"date", "bill date", "entry date", "invoice date"},
            "name": {"customer", "customer name", "name", "client name"},
            "mobile": {"mobile", "mobile number", "phone", "phone number", "contact", "contact number"},
            "vehicle": {"vehicle", "vehicle number", "registration number", "reg number", "car number", "car model"},
            "product": {"product", "product name", "item", "item name", "accessory"},
            "quantity": {"quantity", "qty", "count"},
            "amount": {"total amount", "amount", "bill amount", "total", "sales amount"},
            "category": {"category", "product category", "type"}
        }
        alias_to_field = {header_key(alias): field for field, names in aliases.items() for alias in names}

        for source_name in source.sheetnames:
            ws = source[source_name]
            if ws.max_row < 2 or ws.max_column < 2:
                continue
            # Locate a header row within the first five rows. App-generated files use row 1.
            header_row = None
            mapped = {}
            for candidate_row in range(1, min(5, ws.max_row) + 1):
                found = {}
                for col in range(1, ws.max_column + 1):
                    field = alias_to_field.get(header_key(ws.cell(candidate_row, col).value))
                    if field and field not in found:
                        found[field] = col
                if "date" in found and ("name" in found or "mobile" in found or "vehicle" in found):
                    header_row, mapped = candidate_row, found
                    break
            if not header_row:
                continue

            # Horizontal product-matrix format used by this app: one row per bill,
            # with category names in row 1 and product names in row 2.
            if header_row == 1 and header_key(ws.cell(1, 1).value) == "date" and ws.max_row >= 3 and header_key(ws.cell(1, 2).value) in {"customer name", "customer"}:
                columns = excel_product_columns(ws)
                catalog_items.extend((cat or catalog_lookup.get(norm(prod), "Other"), prod) for _, cat, prod in columns)
                total_col = next((col for col in range(1, ws.max_column + 1)
                                  if header_key(ws.cell(1, col).value) == "total amount"), ws.max_column)
                for row in range(3, ws.max_row + 1):
                    if all(ws.cell(row, c).value in (None, "") for c in range(1, 5)):
                        continue
                    d = parse_date(ws.cell(row, 1).value)
                    if not d:
                        continue
                    products = []
                    for col, cat, prod in columns:
                        q = numeric_quantity(ws.cell(row, col).value)
                        if q:
                            category = cat or catalog_lookup.get(norm(prod), "Other")
                            products.append({"category": category, "product": prod, "quantity": q})
                    try:
                        total = float(ws.cell(row, total_col).value or 0)
                    except (TypeError, ValueError):
                        total = 0.0
                    imported.append({"date": d, "name": safe_value(ws.cell(row, 2).value),
                                     "mobile": safe_value(ws.cell(row, 3).value), "vehicle": safe_value(ws.cell(row, 4).value),
                                     "total_amount": total, "products": products})
                continue

            # Standard row-based workbook: Date, Customer, Mobile, Vehicle, Product, Qty, Amount.
            if "product" in mapped:
                for row in range(header_row + 1, ws.max_row + 1):
                    d = parse_date(ws.cell(row, mapped["date"]).value)
                    if not d:
                        continue
                    product = clean_name(ws.cell(row, mapped["product"]).value)
                    if not product and all(ws.cell(row, c).value in (None, "") for c in mapped.values()):
                        continue
                    category = clean_name(ws.cell(row, mapped["category"]).value) if "category" in mapped else ""
                    category = category or catalog_lookup.get(norm(product), "Other")
                    try:
                        qty = numeric_quantity(ws.cell(row, mapped["quantity"]).value) if "quantity" in mapped else (1 if product else 0)
                    except Exception:
                        qty = 1 if product else 0
                    try:
                        total = float(ws.cell(row, mapped["amount"]).value or 0) if "amount" in mapped else 0.0
                    except (TypeError, ValueError):
                        total = 0.0
                    products = [{"category": category, "product": product, "quantity": qty}] if product and qty else []
                    if product:
                        catalog_items.append((category, product))
                    imported.append({"date": d,
                        "name": safe_value(ws.cell(row, mapped["name"]).value) if "name" in mapped else "nil",
                        "mobile": safe_value(ws.cell(row, mapped["mobile"]).value) if "mobile" in mapped else "nil",
                        "vehicle": safe_value(ws.cell(row, mapped["vehicle"]).value) if "vehicle" in mapped else "nil",
                        "total_amount": total, "products": products})
                continue

            # Fallback for a familiar fixed-header sheet without a Product column.
            if "name" in mapped or "mobile" in mapped or "vehicle" in mapped:
                for row in range(header_row + 1, ws.max_row + 1):
                    d = parse_date(ws.cell(row, mapped["date"]).value)
                    if not d:
                        continue
                    try:
                        total = float(ws.cell(row, mapped["amount"]).value or 0) if "amount" in mapped else 0.0
                    except (TypeError, ValueError):
                        total = 0.0
                    imported.append({"date": d,
                        "name": safe_value(ws.cell(row, mapped["name"]).value) if "name" in mapped else "nil",
                        "mobile": safe_value(ws.cell(row, mapped["mobile"]).value) if "mobile" in mapped else "nil",
                        "vehicle": safe_value(ws.cell(row, mapped["vehicle"]).value) if "vehicle" in mapped else "nil",
                        "total_amount": total, "products": []})
        return imported, catalog_items
    finally:
        if source is not None:
            source.close()

def _word_cell_key(value):
    return re.sub(r"[^a-z0-9]+", "", clean_name(value).casefold())


def _word_product_item(text, data):
    """Resolve a Word product line against the current catalogue and normalize common spelling errors."""
    text = clean_name(text)
    if not text:
        return None
    quantity = 1.0
    match = re.search(r"(?:\bx\s*|\*\s*|\bqty\s*[:=]?\s*)(\d+(?:\.\d+)?)\s*$", text, re.I)
    if match:
        quantity = numeric_quantity(match.group(1)) or 1.0
        text = clean_name(text[:match.start()])
    text = re.sub(r"\s*[-:]\s*\d+(?:\.\d+)?\s*$", "", text).strip()
    if not text:
        return None
    catalog = [(cat, prod) for cat in data.get("categories", []) for prod in data.get("products", {}).get(cat, [])]
    exact = next(((cat, prod) for cat, prod in catalog if norm(prod) == norm(text)), None)
    if exact:
        return {"category": exact[0], "product": exact[1], "quantity": quantity}
    # Fuzzy correction only when the catalogue has one clearly closest match.
    normalized_names = {norm(prod): (cat, prod) for cat, prod in catalog}
    close = difflib.get_close_matches(norm(text), list(normalized_names), n=2, cutoff=0.82)
    if close and (len(close) == 1 or difflib.SequenceMatcher(None, close[0], norm(text)).ratio() - difflib.SequenceMatcher(None, close[1], norm(text)).ratio() >= 0.08):
        cat, product = normalized_names[close[0]]
        return {"category": cat, "product": product, "quantity": quantity}
    category = detect_product_category(text)
    if category:
        return {"category": category, "product": text, "quantity": quantity}
    return {"category": "", "product": text, "quantity": quantity}


def _parse_word_customer_doc(raw):
    try:
        doc = Document(BytesIO(raw))
    except Exception as exc:
        raise ValueError(f"Could not read this Word document: {exc}")
    data = load_data()
    records = []
    aliases = {
        "date": {"date", "entrydate", "billdate"},
        "name": {"customer", "customername", "name", "clientname"},
        "mobile": {"mobile", "mobileno", "phone", "phonenumber", "customernumber", "contact"},
        "vehicle": {"vehicle", "vehiclemodel", "carmodel", "registration", "registrationnumber", "vehiclenumber"},
        "total_amount": {"amount", "total", "totalamount", "billamount", "salesamount"},
        "products": {"products", "productdetails", "items", "accessories", "product"},
    }
    for table in doc.tables:
        if not table.rows:
            continue
        header = [_word_cell_key(cell.text) for cell in table.rows[0].cells]
        columns = {}
        for idx, key in enumerate(header):
            for field, names in aliases.items():
                if key in names and field not in columns:
                    columns[field] = idx
        if "date" not in columns or not any(k in columns for k in ("name", "mobile", "vehicle", "products")):
            continue
        for row in table.rows[1:]:
            cells = [clean_name(cell.text) for cell in row.cells]
            if not any(cells):
                continue
            def get(field, default=""):
                idx = columns.get(field)
                return cells[idx] if idx is not None and idx < len(cells) else default
            date_value = get("date")
            parsed_date = parse_date(date_value)
            if not parsed_date:
                try: parsed_date = valid_date(date_value)
                except Exception: parsed_date = None
            if not parsed_date:
                continue
            products = []
            product_text = get("products")
            if product_text:
                for line in re.split(r"[\n;|,]+", product_text):
                    item = _word_product_item(line, data)
                    if item: products.append(item)
            # Also accept product columns whose headings match a catalogue product.
            for idx, header_text in enumerate(header):
                if idx >= len(cells) or idx in columns.values() or not cells[idx]:
                    continue
                qty = numeric_quantity(cells[idx])
                if not qty:
                    continue
                prod_name = clean_name(table.rows[0].cells[idx].text)
                item = _word_product_item(f"{prod_name} x{qty}", data)
                if item: products.append(item)
            try: total = float(re.sub(r"[^0-9.\-]", "", get("total_amount", "0")) or 0)
            except Exception: total = 0.0
            records.append({"date": parsed_date, "name": safe_value(get("name") or "Nil"),
                            "mobile": safe_value(get("mobile") or "Nil"), "vehicle": safe_value(get("vehicle") or "Nil"),
                            "total_amount": total, "products": products})
    if not records:
        raise ValueError("No customer rows found. Word document needs a table with Date and Customer/Products columns, plus one customer per row.")
    return records


@app.post("/api/preview-word")
def preview_word():
    upload = request.files.get("file")
    if not upload or not upload.filename or not upload.filename.lower().endswith(".docx"):
        return jsonify(success=False, message="Please select a .docx Word document."), 400
    raw = upload.read()
    if not raw:
        return jsonify(success=False, message="The selected Word document is empty."), 400
    try:
        records = _parse_word_customer_doc(raw)
        return jsonify(success=True, records=records, count=len(records), message=f"Found {len(records)} customer record(s). Review before importing.")
    except Exception as exc:
        return jsonify(success=False, message=str(exc)), 400


@app.post("/api/preview-excel")
def preview_excel():
    try:
        records,_=parse_uploaded_excel(request.files.get("file"))
        if not records: return jsonify(success=False,message="No compatible customer rows found."),400
        return jsonify(success=True,records=records)
    except Exception as exc: return jsonify(success=False,message=str(exc)),400

@app.post("/api/import-excel-preview")
def import_excel_preview():
    records = (request.get_json(silent=True) or {}).get("records") or []
    if not records:
        return jsonify(success=False, message="No records selected."), 400
    valid = []
    catalog_items = []
    for record in records:
        try:
            record_date = valid_date(record.get("date"))
        except Exception:
            continue
        products = []
        for item in (record.get("products") or []):
            category = clean_name(item.get("category")) or "Other"
            product = clean_name(item.get("product"))
            quantity = numeric_quantity(item.get("quantity"))
            if product and quantity:
                products.append({"category": category, "product": product, "quantity": quantity})
                catalog_items.append((category, product))
        try:
            total = float(record.get("total_amount") or 0)
        except (TypeError, ValueError):
            total = 0.0
        valid.append({
            "date": record_date,
            "name": safe_value(record.get("name")),
            "mobile": safe_value(record.get("mobile")),
            "vehicle": safe_value(record.get("vehicle")),
            "total_amount": total,
            "products": products
        })
    if not valid:
        return jsonify(success=False, message="No valid customer rows selected. Check the dates in the preview."), 400
    try:
        ensure_excel()
        data, catalog_changed = add_missing_catalog_items(catalog_items)
        if catalog_changed:
            rebuild_excel_preserving_rows()
        wb = _load_workbook_safe()
        existing = read_all_rows()
        def fingerprint(record):
            products = tuple(sorted((norm(i.get("category")), norm(i.get("product")), str(i.get("quantity"))) for i in record.get("products", [])))
            return (record.get("date", ""), norm(record.get("name")), norm(record.get("mobile")), norm(record.get("vehicle")), str(record.get("total_amount") or 0), products)
        seen = {fingerprint(row) for row in existing}
        added = skipped = 0
        for record in valid:
            fp = fingerprint(record)
            if fp in seen:
                skipped += 1
                continue
            month = month_sheet_name(record["date"])
            ws = ensure_month_sheet(wb, month)
            append_record_to_sheet(ws, record, data)
            seen.add(fp)
            added += 1
        reorder_sheets(wb)
        save_workbook_atomic(wb)
        wb.close()
        message = f"Imported {added} customer record(s) successfully."
        if skipped:
            message += f" {skipped} duplicate record(s) skipped."
        return jsonify(success=True, imported=added, skipped=skipped, count=added, message=message)
    except Exception as exc:
        print("Preview import save error:", exc)
        return jsonify(success=False, message=f"Import failed while saving: {exc}"), 400


@app.get("/api/analytics")
def analytics_data():
    rows = read_all_rows()
    customer_counts = {}
    customer_info = {}
    daily_sales = {}
    product_counts = {}
    vehicle_set = set()

    for record in rows:
        name = clean_name(record.get("name")) or "Nil"
        mobile = clean_name(record.get("mobile")) or "Nil"
        if mobile.casefold() not in ("nil", "", "none"):
            customer_key = f"mobile:{norm(mobile)}"
        else:
            customer_key = f"name:{norm(name)}"
        customer_counts[customer_key] = customer_counts.get(customer_key, 0) + 1
        customer_info[customer_key] = {"name": name, "mobile": mobile}

        day = record.get("date") or ""
        try:
            amount = float(record.get("total_amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if day:
            daily_sales[day] = daily_sales.get(day, 0.0) + amount

        vehicle = norm(record.get("vehicle"))
        if vehicle and vehicle != "nil":
            vehicle_set.add(vehicle)

        for item in record.get("products", []):
            product = clean_name(item.get("product"))
            category = clean_name(item.get("category")) or "Other"
            if not product:
                continue
            try:
                quantity = float(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0.0
            key = (norm(category), norm(product))
            if key not in product_counts:
                product_counts[key] = {"name": product, "category": category, "quantity": 0.0}
            product_counts[key]["quantity"] += quantity

    repeat_customers = [
        {"name": customer_info[key]["name"],
         "mobile": customer_info[key]["mobile"], "visits": count}
        for key, count in customer_counts.items() if count > 1
    ]
    repeat_customers.sort(key=lambda item: item["visits"], reverse=True)
    days = sorted(daily_sales, key=date_obj)
    daily_data = [{"date": day, "amount": round(daily_sales[day], 2)} for day in days]
    top_products = sorted(product_counts.values(), key=lambda item: item["quantity"], reverse=True)[:10]

    catalog = load_data()
    all_products = [{"name": product, "category": category}
                    for category in catalog["categories"]
                    for product in catalog["products"].get(category, [])]
    sold_keys = {key for key, item in product_counts.items() if item["quantity"] > 0}
    unsold_products = [item for item in all_products
                       if (norm(item["category"]), norm(item["name"])) not in sold_keys]

    return jsonify({
        "repeat_customers": repeat_customers,
        "repeat_customer_count": len(repeat_customers),
        "one_time_customers": sum(1 for count in customer_counts.values() if count == 1),
        "repeat_products": sum(1 for item in product_counts.values() if item["quantity"] > 1),
        "unique_vehicles": len(vehicle_set),
        "daily_data": daily_data,
        "daily_labels": days,
        "daily_sales": [round(daily_sales[day], 2) for day in days],
        "top_products": [{"name": item["name"], "category": item["category"], "quantity": round(item["quantity"], 2)}
                         for item in top_products],
        "sold_products": [{"name": item["name"], "category": item["category"], "quantity": round(item["quantity"], 2)}
                          for item in sorted(product_counts.values(), key=lambda item: (item["category"].casefold(), item["name"].casefold()))
                          if item["quantity"] > 0],
        "unsold_products": unsold_products
    })

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/customer-details")
def customer_details():
    return render_template("customer_details.html")


@app.post("/api/detect-product-category")
def detect_product_category_api():
    body = request.get_json(silent=True) or {}
    product = clean_name(body.get("product"))
    if not product:
        return jsonify(success=False, message="Enter a product name."), 400

    category = detect_product_category(product)
    data = load_data()
    if category:
        return jsonify(success=True, found=True, product=product, category=category)

    return jsonify(
        success=True,
        found=False,
        needs_category=True,
        product=product,
        categories=data["categories"],
        message="New or unclear product. Please select its category."
    )


@app.get("/api/data")
def api_data():
    return jsonify(load_data())


@app.put("/api/settings")
def update_settings():
    body = request.get_json(silent=True) or {}
    data = load_data()
    settings = data.setdefault("settings", {})
    for key in ("priority_color", "priority_text_color"):
        value = clean_name(body.get(key, settings.get(key, "")))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            return jsonify(success=False, message=f"Invalid colour value for {key.replace('_', ' ')}."), 400
        settings[key] = value.lower()
    save_data(data)
    # Refresh the Excel row fills so the website and downloaded workbook match.
    ensure_excel()
    wb = _load_workbook_safe()
    try:
        for ws in wb.worksheets:
            style_existing_priority_rows(ws)
        temp = EXCEL_FILE.with_name(EXCEL_FILE.stem + "_settings_tmp.xlsx")
        wb.save(temp)
        wb.close()
        os.replace(temp, EXCEL_FILE)
    except Exception as exc:
        try: wb.close()
        except Exception: pass
        return jsonify(success=False, message=f"Settings saved, but Excel colour refresh failed: {exc}"), 500
    return jsonify(success=True, data=data, message="Settings saved. Website and Excel highlight colours updated.")


@app.get("/api/months")
def api_months():
    return jsonify(success=True, months=MONTHS, current=datetime.now().strftime("%B"))


@app.post("/api/category")
def add_category():
    data = load_data(); body = request.get_json(silent=True) or {}; category = clean_name(body.get("category"))
    if not category: return jsonify(success=False, message="Category name is required."), 400
    if any(norm(c) == norm(category) for c in data["categories"]): return jsonify(success=False, message="Category already exists."), 409
    data["categories"].append(category); data["products"][category] = []; save_data(data); rebuild_excel_preserving_rows()
    return jsonify(success=True, data=data, message="Category added successfully.")





@app.delete("/api/category/<path:category>")
def delete_category(category):
    data = load_data()

    actual = next(
        (
            c for c in data.get("categories", [])
            if clean_name(c).casefold() == clean_name(category).casefold()
        ),
        None
    )

    if actual is None:
        return jsonify(
            success=False,
            message="Category not found. Refresh the page and try again."
        ), 404

    # Keep existing customer records before changing the catalogue.
    rows = _catalog_record_rows()

    # Remove only this category and its catalogue product list.
    data["categories"].remove(actual)
    data["products"].pop(actual, None)

    save_data(data)
    rebuild_excel_preserving_rows(rows)

    updated_data = load_data()

    return jsonify(
        success=True,
        data=updated_data,
        message=f'Category "{actual}" and its catalogue products deleted successfully.'
    )


@app.post("/api/product")
def add_product():
    data = load_data()
    body = request.get_json(silent=True) or {}

    category = clean_name(body.get("category"))
    product = clean_name(body.get("product"))

    if not category or not product:
        return jsonify(
            success=False,
            message="Category and product name are required."
        ), 400

    actual = next(
        (c for c in data["categories"] if norm(c) == norm(category)),
        None
    )

    if not actual:
        return jsonify(
            success=False,
            message="Category not found."
        ), 404

    # Check the product name across ALL categories.
    for existing_category in data["categories"]:
        for existing_product in data["products"].get(existing_category, []):
            if norm(existing_product) == norm(product):
                return jsonify(
                    success=False,
                    duplicate=True,
                    existing_product=existing_product,
                    existing_category=existing_category,
                    message=(
                        f'"{existing_product}" already exists in '
                        f'"{existing_category}". Use the existing product '
                        f"instead of adding a duplicate."
                    )
                ), 409

    # Only add when the name is unique across the whole catalogue.
    data["products"].setdefault(actual, []).append(product)
    save_data(data)

    # Rebuild while preserving existing customer rows and quantities.
    rebuild_excel_preserving_rows()

    return jsonify(
        success=True,
        data=load_data(),
        message="New product added successfully."
    ), 201

@app.get("/api/product/duplicates")
def list_duplicate_products():
    data = load_data()
    groups = {}

    for category in data.get("categories", []):
        for product in data.get("products", {}).get(category, []):
            product_name = clean_name(product)
            key = norm(product_name)

            if not key:
                continue

            groups.setdefault(key, []).append({
                "product": product_name,
                "category": category
            })

    duplicates = []

    for key, entries in groups.items():
        if len(entries) > 1:
            duplicates.append({
                "normalized_name": key,
                "entries": entries,
                "categories": sorted({
                    item["category"] for item in entries
                })
            })

    return jsonify(
        success=True,
        duplicate_count=len(duplicates),
        duplicates=duplicates,
        message="Review these duplicates before removing or merging anything."
    )



@app.delete("/api/product")
def delete_product():
    data = load_data(); body = request.get_json(silent=True) or {}; category = clean_name(body.get("category")); product = clean_name(body.get("product"))
    actual = next((c for c in data["categories"] if norm(c) == norm(category)), None)
    if not actual: return jsonify(success=False, message="Category not found."), 404
    products = data["products"].get(actual, []); existing = next((p for p in products if norm(p) == norm(product)), None)
    if not existing: return jsonify(success=False, message="Product not found."), 404
    products.remove(existing); save_data(data); rebuild_excel_preserving_rows()
    return jsonify(success=True, data=data, message="Product deleted successfully.")
def _catalog_record_rows():
    # Read records against the current Excel headers BEFORE changing catalogue names.
    return read_all_rows()


@app.put("/api/category")
def rename_category():
    body = request.get_json(silent=True) or {}
    old_name = clean_name(body.get("old_category"))
    new_name = clean_name(body.get("new_category"))
    data = load_data()
    actual = next((c for c in data["categories"] if norm(c) == norm(old_name)), None)
    if not actual:
        return jsonify(success=False, message="Category not found."), 404
    if not new_name:
        return jsonify(success=False, message="New category name is required."), 400
    if any(c != actual and norm(c) == norm(new_name) for c in data["categories"]):
        return jsonify(success=False, message="A category with that name already exists."), 409

    rows = _catalog_record_rows()
    products = data["products"].pop(actual, [])
    data["categories"] = [new_name if c == actual else c for c in data["categories"]]
    data["products"][new_name] = products
    for row in rows:
        for item in row.get("products", []):
            if norm(item.get("category")) == norm(actual):
                item["category"] = new_name
    save_data(data)
    rebuild_excel_preserving_rows(rows)
    return jsonify(success=True, data=data, message=f'Category renamed to "{new_name}". Excel records updated.')


@app.put("/api/product")
def rename_product():
    body = request.get_json(silent=True) or {}
    category = clean_name(body.get("category"))
    old_name = clean_name(body.get("old_product"))
    new_name = clean_name(body.get("new_product"))
    data = load_data()
    actual = next((c for c in data["categories"] if norm(c) == norm(category)), None)
    if not actual:
        return jsonify(success=False, message="Category not found."), 404
    if not new_name:
        return jsonify(success=False, message="New product name is required."), 400
    products = data["products"].get(actual, [])
    existing = next((p for p in products if norm(p) == norm(old_name)), None)
    if not existing:
        return jsonify(success=False, message="Product not found."), 404
    if any(norm(p) == norm(new_name) and norm(p) != norm(existing) for p in products):
        return jsonify(success=False, message="That product name already exists in this category."), 409

    rows = _catalog_record_rows()
    data["products"][actual] = [new_name if p == existing else p for p in products]
    for row in rows:
        for item in row.get("products", []):
            if norm(item.get("category")) == norm(actual) and norm(item.get("product")) == norm(existing):
                item["product"] = new_name
    save_data(data)
    rebuild_excel_preserving_rows(rows)
    return jsonify(success=True, data=data, message=f'Product renamed to "{new_name}". Excel records updated.')


@app.post("/api/product/move")
def move_product():
    body = request.get_json(silent=True) or {}
    source_name = clean_name(body.get("category"))
    product_name = clean_name(body.get("product"))
    destination_name = clean_name(body.get("target_category"))
    data = load_data()
    source = next((c for c in data["categories"] if norm(c) == norm(source_name)), None)
    destination = next((c for c in data["categories"] if norm(c) == norm(destination_name)), None)
    if not source or not destination:
        return jsonify(success=False, message="Please choose a valid source and destination category."), 404
    if norm(source) == norm(destination):
        return jsonify(success=False, message="Choose a different destination category."), 400
    products = data["products"].get(source, [])
    existing = next((p for p in products if norm(p) == norm(product_name)), None)
    if not existing:
        return jsonify(success=False, message="Product not found in the selected category."), 404
    if any(norm(p) == norm(existing) for p in data["products"].get(destination, [])):
        return jsonify(success=False, message=f'"{existing}" already exists in {destination}. Rename or remove the duplicate first.'), 409

    # Change the row product category before saving the new catalogue, so quantities
    # from the old Excel column are remapped into the destination category column.
    rows = _catalog_record_rows()
    for row in rows:
        for item in row.get("products", []):
            if norm(item.get("category")) == norm(source) and norm(item.get("product")) == norm(existing):
                item["category"] = destination
    data["products"][source] = [p for p in products if norm(p) != norm(existing)]
    data["products"].setdefault(destination, []).append(existing)
    save_data(data)
    rebuild_excel_preserving_rows(rows)
    return jsonify(success=True, data=data, message=f'"{existing}" moved to "{destination}". Website and Excel updated.')



@app.post("/api/remove-duplicates")
def remove_duplicates():
    data = load_data()
    groups = {}

    for category in data.get("categories", []):
        for product in data.get("products", {}).get(category, []):
            product_name = clean_name(product)
            key = norm(product_name)

            if key:
                if key not in groups:
                    groups[key] = {
                        "product": product_name,
                        "categories": []
                    }

                if category not in groups[key]["categories"]:
                    groups[key]["categories"].append(category)

    duplicates = [
        item for item in groups.values()
        if len(item["categories"]) > 1
    ]

    return jsonify(
        success=True,
        categories=data.get("categories", []),
        products=data.get("products", {}),
        duplicates=duplicates,
        message=f"Found {len(duplicates)} duplicate product name(s)."
    )


@app.post("/api/resolve-duplicate")
def resolve_duplicate():
    body = request.get_json(silent=True) or {}
    product = clean_name(body.get("product"))
    remove_category = clean_name(body.get("remove_category"))
    keep_category = clean_name(body.get("keep_category"))

    data = load_data()

    remove_actual = next(
        (c for c in data["categories"] if norm(c) == norm(remove_category)),
        None
    )
    keep_actual = next(
        (c for c in data["categories"] if norm(c) == norm(keep_category)),
        None
    )

    if not product or not remove_actual or not keep_actual:
        return jsonify(success=False, message="Invalid product or category."), 400

    if norm(remove_actual) == norm(keep_actual):
        return jsonify(success=False, message="Choose two different categories."), 400

    remove_products = data["products"].get(remove_actual, [])
    keep_products = data["products"].get(keep_actual, [])

    remove_product = next(
        (p for p in remove_products if norm(p) == norm(product)),
        None
    )
    keep_product = next(
        (p for p in keep_products if norm(p) == norm(product)),
        None
    )

    if not remove_product or not keep_product:
        return jsonify(
            success=False,
            message="That duplicate is no longer present. Refresh and check again."
        ), 409

    # Read existing customer rows BEFORE changing the catalogue.
    rows = _catalog_record_rows()

    # Preserve old customer history by mapping removed-category entries
    # to the category the user chose to keep.
    for row in rows:
        for item in row.get("products", []):
            if (
                norm(item.get("product")) == norm(remove_product)
                and norm(item.get("category")) == norm(remove_actual)
            ):
                item["category"] = keep_actual

    data["products"][remove_actual] = [
        p for p in remove_products if norm(p) != norm(remove_product)
    ]

    save_data(data)
    rebuild_excel_preserving_rows(rows)

    return jsonify(
        success=True,
        data=load_data(),
        message=(
            f'"{remove_product}" removed from "{remove_actual}". '
            f"Existing records mapped to {keep_actual}."
        )
    )


@app.get("/api/customers")
def customers():
    ensure_excel()
    rows = read_all_rows()

    # Count visits for each customer
    # Mobile number is the main identifier.
    # If mobile is Nil/empty, customer name is used.
    customer_counts = {}

    for row in rows:
        name = clean_name(row.get("name")) or "Nil"
        mobile = clean_name(row.get("mobile")) or "Nil"

        if mobile.casefold() not in ("nil", "", "none"):
            key = f"mobile:{norm(mobile)}"
        else:
            key = f"name:{norm(name)}"

        customer_counts[key] = customer_counts.get(key, 0) + 1

    # Add repeat customer information to every row
    for i, row in enumerate(rows, 1):
        name = clean_name(row.get("name")) or "Nil"
        mobile = clean_name(row.get("mobile")) or "Nil"

        if mobile.casefold() not in ("nil", "", "none"):
            key = f"mobile:{norm(mobile)}"
        else:
            key = f"name:{norm(name)}"

        visit_count = customer_counts.get(key, 1)

        row["display_no"] = i
        row["customer_name"] = name
        row["phone_number"] = mobile
        row["visit_count"] = visit_count
        row["is_repeat_customer"] = visit_count > 1

        if visit_count > 1:
            row["repeat_label"] = f"Repeat Customer • {visit_count} visits"
        else:
            row["repeat_label"] = "New / One-time Customer"

    return jsonify(
        success=True,
        customers=rows,
        rows=rows,
        data=rows,
        records=rows,
        count=len(rows)
    )


@app.get("/api/customer-details")
def customer_details_api():
    return customers()


@app.get("/api/customer-details-data")
def customer_details_data():
    ensure_excel()
    rows = read_all_rows()
    return jsonify(success=True, customers=rows, rows=rows, data=rows, count=len(rows))


@app.post("/api/save-customer")
def save_customer():
    body = request.get_json(silent=True) or {}
    customer = body.get("customer") or {}
    selections = body.get("products") or []
    try:
        record_date = valid_date(customer.get("date"))
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    name = safe_value(customer.get("name"))
    mobile = safe_value(customer.get("mobile"))
    vehicle = safe_value(customer.get("vehicle"))
    if not selections:
        return jsonify(success=False, message="Please add at least one product type."), 400
    try:
        total = float(customer.get("total_amount") or 0)
    except (TypeError, ValueError):
        total = 0.0
    record = {"date": record_date, "name": name, "mobile": mobile,
              "vehicle": vehicle, "total_amount": total, "products": selections}
    month = month_sheet_name(record_date)
    wb = None
    try:
        # Serialize customer writes so two quick clicks/requests cannot race the XLSX file.
        with _WORKBOOK_SAVE_LOCK:
            wb = _load_workbook_safe()
            data = load_data()
            ws = ensure_month_sheet(wb, month)
            append_record_to_sheet(ws, record, data)
            reorder_sheets(wb)
            save_workbook_atomic(wb)
        return jsonify(success=True, message=f"Customer entry saved in {month} sheet.")
    except Exception as exc:
        app.logger.exception("Customer save failed")
        return jsonify(success=False, message=f"Customer could not be saved: {exc}"), 500
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


@app.put("/api/customer/<path:sheet>/<int:excel_row>")
def update_customer(sheet, excel_row):
    body = request.get_json(silent=True) or {}; customer = body.get("customer") or {}; selections = body.get("products") or []
    try: date = valid_date(customer.get("date"))
    except ValueError as exc: return jsonify(success=False, message=str(exc)), 400
    if not selections: return jsonify(success=False, message="Please add at least one product type."), 400
    if not EXCEL_FILE.exists(): return jsonify(success=False, message="Excel file not found."), 404
    wb = _load_workbook_safe(); data = load_data()
    if sheet not in wb.sheetnames:
        wb.close(); return jsonify(success=False, message="Customer record not found."), 404
    old_ws = wb[sheet]
    if excel_row < 3 or excel_row > old_ws.max_row:
        wb.close(); return jsonify(success=False, message="Customer record not found."), 404
    record = {"date": date, "name": safe_value(customer.get("name")), "mobile": safe_value(customer.get("mobile")), "vehicle": safe_value(customer.get("vehicle")), "total_amount": float(customer.get("total_amount") or 0), "products": selections}
    target = month_sheet_name(date)
    # Update in place when month is unchanged. If month changes, remove old row and append to new month.
    if target == sheet:
        # Clear product cells but keep headers.
        for col in range(1, old_ws.max_column + 1): old_ws.cell(excel_row, col).value = 0
        old_ws.cell(excel_row, 1).value = record["date"]; old_ws.cell(excel_row, 2).value = record["name"]; old_ws.cell(excel_row, 3).value = record["mobile"]; old_ws.cell(excel_row, 4).value = record["vehicle"]
        lookup = {(norm(c), norm(p)): 5+i for i,(c,p) in enumerate(product_headers(data))}
        for item in selections:
            key=(norm(item.get("category")), norm(item.get("product")))
            if key in lookup: old_ws.cell(excel_row, lookup[key]).value = numeric_quantity(item.get("quantity"))
        old_ws.cell(excel_row, total_amount_column(old_ws)).value = record["total_amount"]
        # Recalculate the Seat Cover/Sunfilm highlight when a customer is edited.
        for cell in old_ws[excel_row]:
            if cell.fill.fgColor.rgb in ("00FFF2CC", "FFFFF2CC"):
                cell.fill = PatternFill(fill_type=None)
                cell.font = Font(name="Arial", size=10, color="000000")
        apply_priority_row_style(old_ws, excel_row, record)
    else:
        old_ws.delete_rows(excel_row, 1)
        target_ws = ensure_month_sheet(wb, target)
        append_record_to_sheet(target_ws, record, data)
    reorder_sheets(wb); save_workbook_atomic(wb); wb.close()
    return jsonify(success=True, message="Customer updated successfully.")


@app.delete("/api/customer/<path:sheet>/<int:excel_row>")
def delete_customer(sheet, excel_row):
    if not EXCEL_FILE.exists(): return jsonify(success=False, message="Excel file not found."), 404
    wb = _load_workbook_safe()
    if sheet not in wb.sheetnames: wb.close(); return jsonify(success=False, message="Customer not found."), 404
    ws = wb[sheet]
    if excel_row < 3 or excel_row > ws.max_row: wb.close(); return jsonify(success=False, message="Customer not found."), 404
    ws.delete_rows(excel_row, 1); save_workbook_atomic(wb); wb.close()
    return jsonify(success=True, message="Customer deleted successfully.")


@app.post("/api/import-excel")
def import_excel():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify(success=False, message="Please select an Excel file."), 400

    if not upload.filename.lower().endswith((".xlsx", ".xlsm")):
        return jsonify(success=False, message="Please select an .xlsx or .xlsm Excel file."), 400

    # Keep the uploaded workbook in memory.
    # Do NOT create/delete a Windows temporary .xlsx here.
    # That was the source of [WinError 32] when the file was still locked.
    raw = upload.read()
    if not raw:
        return jsonify(success=False, message="The selected Excel file is empty."), 400

    source = None
    try:
        source = load_workbook(BytesIO(raw), data_only=True, read_only=False)

        imported = []
        catalog_items = []

        for source_name in source.sheetnames:
            ws = source[source_name]
            if ws.max_row < 3:
                continue

            if clean_name(ws.cell(1, 1).value).casefold() != "date":
                continue

            columns = excel_product_columns(ws)

            for _, cat, prod in columns:
                catalog_items.append((cat or "Other", prod))

            # If a sheet is named as a month, use it only as fallback
            # for rows with a missing year/date. Do not invent a day.
            fallback = source_name if source_name in MONTHS else None

            for row in range(3, ws.max_row + 1):
                if all(ws.cell(row, c).value in (None, "") for c in range(1, 5)):
                    continue

                d = parse_date(ws.cell(row, 1).value)
                if not d and fallback:
                    continue
                if not d:
                    continue

                products = []
                for col, cat, prod in columns:
                    q = numeric_quantity(ws.cell(row, col).value)
                    if q:
                        products.append({
                            "category": cat or "Other",
                            "product": prod,
                            "quantity": q
                        })

                total = ws.cell(row, total_amount_column(ws)).value or 0
                try:
                    total = float(total)
                except Exception:
                    total = 0

                imported.append({
                    "date": d,
                    "name": safe_value(ws.cell(row, 2).value),
                    "mobile": safe_value(ws.cell(row, 3).value),
                    "vehicle": safe_value(ws.cell(row, 4).value),
                    "total_amount": total,
                    "products": products
                })

        if not imported:
            return jsonify(
                success=False,
                message="No compatible customer rows found. Expected Date in column A and product quantities in the same format."
            ), 400

        # Only now access the destination workbook, and use a separate safe
        # workbook if the old products.xlsx is damaged/locked.
        ensure_excel()

        data, catalog_changed = add_missing_catalog_items(catalog_items)

        if catalog_changed:
            rebuild_excel_preserving_rows()

        wb = _load_workbook_safe()
        existing = read_all_rows()

        def fingerprint(record):
            products = tuple(sorted(
                (
                    norm(p.get("category")),
                    norm(p.get("product")),
                    str(p.get("quantity"))
                )
                for p in record.get("products", [])
            ))
            return (
                record.get("date", ""),
                norm(record.get("name")),
                norm(record.get("mobile")),
                norm(record.get("vehicle")),
                str(record.get("total_amount") or 0),
                products
            )

        seen = {fingerprint(r) for r in existing}
        added = 0
        skipped = 0

        for record in imported:
            fp = fingerprint(record)
            if fp in seen:
                skipped += 1
                continue

            month = month_sheet_name(record["date"])
            ws = ensure_month_sheet(wb, month)
            append_record_to_sheet(ws, record, data)
            seen.add(fp)
            added += 1

        reorder_sheets(wb)
        save_workbook_atomic(wb)
        wb.close()

        message = f"Imported {added} customer record(s) successfully. Data added to month-wise sheets."
        if skipped:
            message += f" {skipped} duplicate record(s) skipped."

        return jsonify(
            success=True,
            imported=added,
            skipped=skipped,
            message=message
        )

    except Exception as exc:
        print("Import error:", exc)
        return jsonify(success=False, message=f"Excel import failed: {exc}"), 400

    finally:
        if source is not None:
            try:
                source.close()
            except Exception:
                pass


@app.get("/download-excel")
def download_excel():
    ensure_excel()
    return send_file(EXCEL_FILE, as_attachment=True, download_name="Car_Accessories_Customer_Data.xlsx")


@app.get("/download-catalogue")
def download_catalogue():
    """Download the complete live category and product list as a Word document."""
    data = load_data()
    doc = Document()
    title = doc.add_heading("Car Accessories — Category & Product List", 0)
    title.alignment = 1
    doc.add_paragraph(f"Generated on {datetime.now().strftime('%d-%m-%Y %I:%M %p')}")
    total_products = sum(len(data.get("products", {}).get(cat, [])) for cat in data.get("categories", []))
    doc.add_paragraph(f"Categories: {len(data.get('categories', []))}    |    Products: {total_products}")
    for category in data.get("categories", []):
        doc.add_heading(category, level=1)
        products = data.get("products", {}).get(category, [])
        if products:
            for product in products:
                doc.add_paragraph(product, style="List Bullet")
        else:
            doc.add_paragraph("No products added yet.")
    stream = BytesIO()
    doc.save(stream)
    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name="Car_Accessories_Category_Product_List.docx", mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.post("/api/clear-excel")
def clear_excel():
    # Keep workbook structure and all month sheet headers, but clear customer rows.
    wb = _load_workbook_safe()
    for ws in wb.worksheets:
        if ws.max_row >= 3 and clean_name(ws.cell(1,1).value).casefold() == "date":
            ws.delete_rows(3, ws.max_row - 2)
    save_workbook_atomic(wb); wb.close()
    return jsonify(success=True, message="All Excel customer data cleared. Month sheets and catalogue were kept.")

# =========================
# DASHBOARD
# =========================

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/month-details")
def month_details():
    month = clean_name(request.args.get("month"))
    if month not in MONTHS:
        return jsonify(success=False, message="Choose a valid month."), 400
    rows = [r for r in read_all_rows() if month_for_date(r.get("date")) == month]
    daily = {}
    total_amount = 0.0
    for record in rows:
        day = record.get("date") or ""
        try:
            amount = float(record.get("total_amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        total_amount += amount
        if day not in daily:
            daily[day] = {"date": day, "amount": 0.0, "customers": 0}
        daily[day]["amount"] += amount
        daily[day]["customers"] += 1
    days = sorted(daily.values(), key=lambda item: date_obj(item["date"]))
    for item in days:
        item["amount"] = round(item["amount"], 2)
    min_amount = min(days, key=lambda item: item["amount"]) if days else None
    min_customers = min(days, key=lambda item: item["customers"]) if days else None
    return jsonify(success=True, month=month, total_amount=round(total_amount, 2), total_customers=len(rows), days=days,
                   minimum_daily_amount=min_amount, minimum_daily_customers=min_customers)


@app.get("/api/dashboard")
def dashboard_data():
    rows = read_all_rows()

    total_customers = len(rows)
    total_sales = 0.0

    month_sales = {month: 0.0 for month in MONTHS}
    month_customers = {month: 0 for month in MONTHS}
    product_totals = {}

    for record in rows:
        try:
            amount = float(record.get("total_amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0

        total_sales += amount

        month = month_for_date(record.get("date"))
        if month in month_sales:
            month_sales[month] += amount
            month_customers[month] += 1

        for item in record.get("products", []):
            product = clean_name(item.get("product"))
            category = clean_name(item.get("category")) or "Other"
            if not product:
                continue

            try:
                quantity = float(item.get("quantity") or 0)
            except (TypeError, ValueError):
                quantity = 0.0

            if quantity:
                label = f"{category} — {product}"
                product_totals[label] = product_totals.get(label, 0.0) + quantity

    month_labels = [
        month for month in MONTHS
        if month_customers.get(month, 0) > 0
    ]

    top_products = sorted(
        product_totals.items(),
        key=lambda item: item[1],
        reverse=True
    )[:10]

    return jsonify({
        "total_customers": total_customers,
        "total_sales": round(total_sales, 2),
        "active_months": len(month_labels),
        "products_used": len(product_totals),
        "month_labels": month_labels,
        "month_sales": [
            round(month_sales[month], 2)
            for month in month_labels
        ],
        "month_customers": [
            month_customers[month]
            for month in month_labels
        ],
        "top_products": [
            {
                "name": name,
                "quantity": round(quantity, 2)
            }
            for name, quantity in top_products
        ]
    })


@app.route("/pdf-import")
def pdf_import_page():
    return render_template("pdf_import.html")


@app.post("/api/pdf-info")
def pdf_info():
    if pypdf is None or pypdf.PdfReader is None:
        return jsonify(success=False, message="PDF support is not installed. Run: pip install -r requirements.txt"), 500
    uploaded = request.files.get("pdf")
    if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
        return jsonify(success=False, message="Please select a PDF file."), 400
    try:
        reader = pypdf.PdfReader(uploaded.stream)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return jsonify(success=False, message="This PDF is password protected. Unlock it and upload again."), 400
        return jsonify(success=True, pages=len(reader.pages), filename=uploaded.filename)
    except Exception as exc:
        return jsonify(success=False, message=f"Could not read PDF: {exc}"), 400


@app.post("/api/pdf-page")
def pdf_page():
    if pypdf is None or pypdf.PdfReader is None:
        return jsonify(success=False, message="PDF support is not installed. Run: pip install -r requirements.txt"), 500
    uploaded = request.files.get("pdf")
    try:
        page_no = int(request.form.get("page", "1")) - 1
    except (TypeError, ValueError):
        page_no = 0
    if not uploaded or not uploaded.filename or not uploaded.filename.lower().endswith(".pdf"):
        return jsonify(success=False, message="Please select a PDF file."), 400
    try:
        reader = pypdf.PdfReader(uploaded.stream)
        if page_no < 0 or page_no >= len(reader.pages):
            return jsonify(success=False, message="Invalid PDF page number."), 400
        page = reader.pages[page_no]
        return jsonify(success=True, page=page_no + 1, pages=len(reader.pages), text=(page.extract_text() or ""))
    except Exception as exc:
        return jsonify(success=False, message=f"Could not read PDF page: {exc}"), 400


# Initialize after all file paths, helpers, and routes have been defined.
app.initialize()

# =========================
# START SERVER
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
