CAR ACCESSORIES PROFESSIONAL MANAGER

1. Open Command Prompt in this folder.
2. Install packages:
   py -m pip install -r requirements.txt
3. Start:
   py app.py
4. Open:
   http://127.0.0.1:5000/

Pages:
- New Entry
- Dashboard
- Customer Details
- Image Import (OCR in browser; internet is required the first time for CDN scripts)
- Import Excel with preview
- Products
- Analytics
- Download Excel

Data is stored in data/products.xlsx and data/website_data.json.
Do not delete the data folder if you want to keep saved records.


UPDATED PRODUCT MANAGEMENT FEATURES
- On the Products page, use Rename beside a category to correct its spelling.
- Use Edit name beside a product to correct product spelling.
- Use Move to select a destination category by its displayed number and confirm.
- Category renames, product renames, and product moves rebuild the Excel columns and remap saved quantities while preserving customer details, dates, vehicle, and total amount when the workbook is readable.
- Duplicate category/product names are rejected to avoid accidental overwrites.
- Make a copy of the data folder before deploying any update.

IMPORTANT DATA NOTE
The products.xlsx included in the uploaded ZIP has ZIP/CRC corruption, and products_working.xlsx is an empty workbook. Keep a separate backup of your live data and repair/restore the workbook before using catalogue changes on the live site. The updated code does not repair that corrupted workbook automatically.
