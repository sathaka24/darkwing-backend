Here is the updated and finalized **Business Requirements Document (BRD)**, reflecting your excellent architectural decisions (the Vertical Menu layout and the abstract Document Generating Engine). 

You can copy-paste this directly into your project management tool!

---

### 🌟 System Overview
A web-based, internally managed mini-ERP for a machinery parts business. The system manages customers, tracks payments (advances and balances), and utilizes a centralized, frontend-driven **Document Generating Engine** to output highly customized invoices and reports in PDF, XLSX, and DOCS formats.

---

### 1. User & Authentication (Access Control)
*   **Login System:** The system is completely private. Users are greeted by a secure login screen before accessing the system.
*   **Two Users:** The system will have exactly two authorized user accounts (e.g., Thanuja Minol and a second user).
*   **Action Tracking:** The system automatically tracks the active session. Every invoice created records and displays which user generated it (e.g., printed on documents as *"Created by: Thanuja Minol (internal)"*).

### 2. UI Layout & Navigation (The Vertical Menu)
Post-login, the user interfaces with a split-screen layout featuring a **fixed vertical sidebar menu** on the left and dynamic content on the right. The core modules (Tabs) in this menu are:

*   **Dashboard (Default Tab):** Displays business status at a glance.
    *   **Monthly Income:** Total revenue collected in the current month.
    *   **Widgets:** Quick views for Total Issued Invoices, Invoices with Advance Payments (Pending Balance), Fully Paid Invoices, and Cancelled Invoices.
    *   **Export Data:** Triggers the Document Engine to download a complete Monthly Summary (XLSX or PDF).
*   **Customers Tab:** 
    *   Table listing all saved customers.
    *   Form to register new customers (Name, Mobile Number, Email, Notes).
    *   **Auto-Generated ID:** System automatically assigns a unique ID (e.g., CUST-001).
*   **All Invoices Tab:**
    *   Master table of all invoices created.
    *   Filtering options by status (Pending, Paid, Cancelled).
    *   Quick-action buttons per row: "Mark as Fully Paid" and "Download Document".
*   **Create Invoice Tab:**
    *   The dynamic form to build an invoice. Allows searching for existing customers via dropdown or adding a new customer on the spot.

### 3. Invoice Logic & Creation (Core Feature)
Within the "Create Invoice" tab, the system must handle the following logic:
*   **Line Items:** Users input Part Name/Description, Model, Part Number, Brand, Quantity (up to 4 decimal places, e.g., 1.0000), Unit Price, and Discount Percentage.
*   **Calculations (Automated):**
    *   `Item Total = (Qty * Unit Price) - Discount`
    *   `Grand Total = Sum of all Item Totals`
*   **Warranty System:** 
    *   **Item Level:** A checkbox ("Apply Warranty"). If checked, a red star (`★`) flags the item.
    *   **Invoice Level:** A dropdown to select a visual Warranty Stamp (e.g., "None", "3 Months", "6 Months").

### 4. Payment & Status Tracking
*   **Advance Payments (Pre-orders):** Input field for advance payment amounts. System records the exact Date/Time.
*   **Balance Calculation:** Automatically displays `Total Amount To Be Paid` (Grand Total minus Advance Payment).
*   **Full Payment:** Clicking "Mark as Fully Paid" captures the final payment Date/Time and updates the status.
*   **Cancellation:** Ability to manually cancel an invoice if a deal falls through.

### 5. The Document Generating Engine (PDF, XLSX, DOCS)
Instead of hardcoding document generation into specific pages, the system utilizes an abstract, frontend-based **Document Generating Engine**. Any tab in the UI can pass JSON data to this engine and request a specific format.

*   **Zero Backend Load:** The engine runs entirely in the user's browser, pulling data from the Django API and processing the files using local RAM.
*   **Format Handling:**
    *   **PDF:** Generates highly professional, English-only vector PDFs (Invoices).
    *   **XLSX:** Generates formatted Excel spreadsheets (Monthly Summaries).
    *   **DOCS:** Capable of generating native Word documents if required.
*   **Dynamic Visuals (For Invoices):**
    *   Applies custom Image Headers, Footers, a central Watermark (Gear logo), and the authorized user's signature.
    *   Includes a "Discount" column in the table.
    *   If the status is "Fully Paid", a red **"PAID"** stamp image is dynamically positioned on the document with the paid date.
    *   If a warranty is selected, the specific **Warranty Stamp** image is positioned near the bank details.
    *   If at least one item has a warranty star (`★`), the Terms & Conditions section dynamically includes rule #4.

---
