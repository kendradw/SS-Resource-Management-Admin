# Smartsheet + Resource Management Automation

This project automates project and time management workflows by integrating Smartsheet and Resource Management (RM). It creates DCT Planning Grids, syncs project metadata, tracks workload, manages time entries, and ensures data consistency across systems.


## Project Structure

```
├── main.py               # GUI interface for chosing updates
├── auto_main.py          # Command-line runner for full automation (for DO deployment)
├── auto_rm.py            # DCT & RM project creation and field syncing
├── SS_RM_admin.py        # Time tracking, assignments, and project archiving
├── smartsheet_bot.py     # Selenium automation for enabling RM workload tracking
├── configs/
│   ├── config.json       # API tokens, sheet/workspace IDs 
│   ├── crypter.py        # Utility to encrypt/decrypt credentials
│   └── setup_logger.py   # Centralized logging utility
├── clients/
│   └── smartsheet_grid.py # Smartsheet sheet and summary wrappers
└── data/
    └── *.json            # Cached or temporary JSON exports
```


## Features

### Project Automation (`auto_rm.py`)
- Creates DCT Planning Grids from a template.
- Initializes RM projects.
- Populates Smartsheet intake sheets with URLs, IDs, and flags.
- Pulls enumerator data and identifies new projects.
- Syncs custom and standard RM Project fields

### Admin Functions (`SS_RM_admin.py`)
- Fetches and posts RM time entries.
- Reconciles time entry discrepancies from HH2 export.
- Updates archived projects.
- Handles Sage ID to user matching.

### GUI (`main.py`)
- Live logging viewer.
- Buttons for:
  - Update Projects (DCT + RM)
  - Update Time Entries
  - Update Assignments
  - Run All Updates
  - Exit

### SmartsheetBot (`smartsheet_bot.py`)
- Uses Selenium to:
  - Log into Smartsheet.
  - Navigate to project sheets.
  - Enable workload tracking (RM).


## Setup Instructions

### 1. Install Python requirements

Includes:
- pandas
- smartsheet-python-sdk
- selenium
- requests

You will also need Chrome and the ChromeDriver that matches your version.

### 3. Run the app

**GUI mode:**

```
python main.py
```

**Automation mode:**

```
python auto_main.py
```


## Logging

All logs are written to:

```
configs/log.log
```

## Maintenance Notes
- The script assumes a `<PROJECT NAME> Template` exists in the planning workspace.

---

# AutoRM: Smartsheet + Resource Management (RM) Project Automation

This script automates the creation and management of DCT Planning Grids and RM Projects for Dowbuilt’s internal project workflow. It synchronizes project metadata, creates and links planning sheets, and enables workload tracking through Smartsheet and Resource Management APIs.


## Usage
### Initialize the automation class
rm_automation = AutoRM()

### Run the full update pipeline:
rm_automation.update_projects()
- Add new projects to the RM intake sheet
- Create DCT Planning Grids if missing
- Create and link RM Projects
- Update Smartsheet intake with links, IDs, flags

## What It Does

### Automatically:
- Fetches new projects from the Smartsheet DCT Planning List (PL Mirror).
- Adds new rows to an auxiliary RM Intake sheet.
- Creates Smartsheet DCT Planning Grids from a standardized template.
- Creates corresponding RM projects and activates workload tracking via Selenium.
- Updates custom and standard fields in RM using project metadata.
- Pushes created URLs and project IDs back to the RM Intake sheet.
- Ensures every project has a complete and connected planning sheet and RM profile.


## How It Works

1. **`fetch_new_enums()`**
   - Compares enumerators in the PL Mirror with those in the RM Intake sheet.
   - Returns new enumerators not yet added to the intake sheet.

2. **`add_new_rows()`**
   - Adds new rows to the RM Intake sheet for any new enumerators.

3. **`fetch_intake()`**
   - Gathers all intake rows missing a DCT Grid or RM Project.
   - Converts those rows into `Project` objects.

4. **`todo_handler()`**
   - Processes all pending projects:
     - Creates DCT Planning Grid sheets from a template.
     - Fills out ENUMERATOR in summary fields.
     - Uses Selenium to enable workload tracking in RM.
     - Verifies RM project creation and updates metadata.
     - Updates the RM Intake sheet with IDs, URLs, and completion flags.

5. **`create_dct_grid()`**
   - Copies a template sheet in the DCT Planning workspace.
   - Inserts ENUMERATOR to auto-populate formulas via summary fields.

6. **`create_rm_projects()`**
   - Uses a Selenium bot to enable RM workload tracking on the new sheet.
   - Verifies RM project creation and pushes metadata using the RM API.

7. **`update_intake_rows()`**
   - Updates checkboxes, URLs, and project IDs in the RM Intake sheet.

8. **`update_rm_project_data()` + `rm_field_updates()`**
   - Syncs custom and standard fields like:
     - DCT Status
     - Project Enumerator
     - Architect
     - Estimate
     - Estimate Presented
     - Client
     - Job Number

---

# SmartsheetBot: Automated Workload Tracking via Selenium

This module automates the process of enabling Resource Management (RM) workload tracking on Smartsheet project sheets. It uses Selenium to simulate user interaction with the Smartsheet web interface and programmatically activates project tracking features.


## What It Does

- Logs into Smartsheet using Microsoft SSO or manual login.
- Navigates to specified Smartsheet sheet URLs.
- Clicks through the Resource Management tab.
- Activates "Track Workload" and "Connect Project" buttons.
- Logs all activity to `configs/log.log`.


## How It Works

### 1. Authentication Options

- `user_login_auto()`  
  Uses encrypted credentials to sign in through Microsoft SSO flow. Requires user MFA validation.

- `user_login_manual()`  
  Launches browser and waits for manual user login.

- `login()`  
  Standard email/password login via UI form fields. For automation.

### 2. Workload Tracking

- `track_workload(sheet_url)`  
  Opens a given Smartsheet project, clicks through RM tabs, and activates workload tracking and project connection.

### 3. Cleanup

- `close()`  
  Closes the active Selenium Chrome session.


## Requirements

- Python 3.10+
- Chrome browser installed
- Matching version of ChromeDriver
- `configs/config.json` file with:
  ```
  user=<encrypted_email>
  pass=<encrypted_password>
  ```
- Encrypted with `configs/crypter.py`


## Logging

All bot activity is logged to:

```
configs/log.log
```

Includes login status, success/failure for each sheet, and tracking confirmation.


## Limitations

- Requires GUI Chrome for manual login or debugging.
- Designed specifically for Smartsheet layout as of April 2025 — may need to change if Smartsheet updates its interface.
- Microsoft user login may intermittently timeout or require re-authentication.

---

# SS-Resource-Management-Admin
To help DCT Manage their integration between main SS and Resource Management SS

SmartsheetRmAdmin is a Python automation tool built to support DCT's integration between Smartsheet and Smartsheet Resource Management (RM). It handles syncing of time entries and assignments between the two systems, as well as archiving projects.

## Features

### Time & Expense Automation
- Fetches timesheet (HH2) data from a Smartsheet source.
- Validates structure and aggregates entries by user/project/date.
- Compares entries against Resource Management records.
- Posts new entries or updates discrepancies via RM API.
- Writes back a log of actions to Smartsheet.

### Project Metadata Sync 
- Renames archived RM projects to avoid naming collisions and posting errors.

### User Management
- Audits RM users for missing employee numbers (Sage ID).
- Looks up and populates missing Sage IDs using an HRIS sheet in Smartsheet.

### Assignment Syncing
- Compares project task status between Smartsheet and RM.
- Updates task status in Smartsheet where RM shows differences.


## Usage

Initialize the admin object with a config dictionary and call the desired routine.

```python
from smartsheet_rm_admin import SmartsheetRmAdmin

config = {
    # your configuration values here
}

sra = SmartsheetRmAdmin(config)

