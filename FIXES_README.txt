UPDATED PROJECT NOTES
- Move Product refreshes the live category list every time and accepts either a category number or the category name typed manually.
- New Entry accepts typed or pasted product names. Saved names are assigned to their existing category. Known aliases are automatically categorized; unknown names ask for a category and are saved to the catalogue for next time.
- PDF Import is included in the sidebar. It extracts selectable PDF text page-by-page and uses OCR for scanned pages. Detected text can be copied/edited; product lines can be pasted/edited. Known products use their catalogue category; unknown products ask for a category and are saved before the bill page is saved.
- PDF page saves now use the actual listed products and quantities, not a dummy “PDF Imported Entry” product.
- Existing data/website_data.json and Excel files from the source project are preserved in this ZIP. Keep a backup before replacing a live hosted copy.
- Install dependencies with: python -m pip install -r requirements.txt
- Run on Windows with run.bat or: python app.py


Latest requested fixes (October 2026):
- Excel preview import now saves selected rows into month sheets and skips exact duplicates.
- PDF info/page API routes are included; install dependencies using pip install -r requirements.txt.
- Product buttons list all saved products in the selected category.
- Category colours are applied to Excel category headers and matching product subheaders.
- Dashboard month clicks load daily sales/customer graph and minimum daily amount/customer count.
- Analytics lists all products sold plus catalogue products never sold.

Reliability pass (October 11, 2026):
- Category dropdown resets the product search so all products in the chosen category are visible; product lookup handles category keys without case-sensitive mismatches.
- Product catalogue panel has more room and scrolls through the full list.
- Excel preview reports clear errors and import progress instead of failing silently.
- Excel import recognizes both the app's horizontal product-column workbook and standard row-based files with Date / Customer / Product / Quantity / Amount headers.
- Excel parsing locates the actual Total Amount column instead of assuming it is always the last formatted column.
- Analytics keeps identical product names in different categories separate and labels sold / unsold products with their category.
- Validation completed: Python syntax, JavaScript syntax, ZIP integrity, and parser tests for both supported Excel layouts. A live browser / PythonAnywhere integration test is not possible from this packaging environment; please use the preview screen before importing your real file.

Critical product-save fix (October 27, 2026):
- Existing month sheets are synchronized with the current product catalogue before a customer record is appended. This prevents newly added products from being written into stale column positions and displayed as unrelated products (for example, an Engine Mat or cut mat).
- Existing month-sheet product quantities and Total Amount values are preserved when product columns are rebuilt.
- Bulk-entry parser check: the 11-line example is parsed as 11 products, and the nine supplied prices sum to ₹17,040. The two lines without a supplied price are excluded from that total.
- Validation run on this package: Python syntax check, JavaScript syntax check, parser quantity/amount test, workbook column synchronization test, and ZIP integrity test. A full browser/server test could not be run in this environment because Flask is not installed here; run the project in its normal Python environment to verify the UI.
