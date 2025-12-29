# **Leave Planner CLI**

## **Purpose**

The **Leave Planner** is a Python CLI tool designed to help users plan their annual leave effectively. It combines:

*   **Public holidays** from `.ics` files
*   **User-planned leave** from `holidays.csv`
*   **Leave entitlements** from `leave.csv`

The program generates an **HTML calendar** highlighting:

*   **Green**: Working days
*   **Purple**: Public holidays
*   **Red**: Planned leave
*   **Blue**: Public holiday + Planned leave

It also calculates:

*   **Annual leave used** (working days taken off, excluding public holidays)
*   **Annual leave left** for the current and next year based on entitlements.

***

## **Features**

*   Reads all `public-holidays-sg-<year>.ics` files in `public-holidays/` folder.
*   Reads `holidays.csv` for planned leave ranges (e.g., `20260426-20260502`).
*   Reads `leave.csv` for entitlements:
        leave-package,leave-to-carry-over,misc-leave
    Example: `18,9,1,18` → Current year: 9 days; Next year: 18+9+1 = 28 days. With a max carry-over of 18
*   Generates an HTML calendar with color-coded days.
*   Displays **annual leave used** and **annual leave left** in both HTML and CLI output.

***

## **Usage**

### **Folder Structure**

    project/
    ├─ public-holidays/
    │  ├─ public-holidays-sg-2025.ics
    │  └─ public-holidays-sg-2026.ics
    ├─ holidays.csv
    ├─ leave.csv
    └─ leave_planner.py

### **Run the Program**

```bash
# Basic usage
python3 leave_planner.py > leave_plan.html

# With custom options
python3 leave_planner.py \
  --public-dir public-holidays \
  --csv holidays.csv \
  --leave-csv leave.csv \
  --working-days 1111100 \
  --out leave_plan.html \
  --title "My Leave Plan"
  --show-years next
```

### **Arguments**

*   `--public-dir`: Directory with public holiday ICS files (default: `public-holidays`)
*   `--csv`: File with planned leave ranges (default: `holidays.csv`)
*   `--leave-csv`: File with leave entitlements (default: `leave.csv`)
*   `--working-days`: 7-character string for Mon–Sun (e.g., `1111100`)
*   `--out`: Output HTML file (default: `leave_plan.html`)
*   `--title`: HTML page title
*   `--show-years`: Which years to show in HTML (default: `both`)

***

## **Output**

*   **HTML file** with:
    *   Color-coded calendar
    *   Summary of annual leave used
    *   Annual leave left per year
*   **CLI (stderr)**:
        Annual leave used: 8 day(s)
        Annual leave left (2025): 4 day(s)
        Annual leave left (2026): 25 day(s)

***