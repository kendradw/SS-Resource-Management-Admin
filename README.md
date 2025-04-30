# Smartsheet + Resource Management Automation

This project automates project and time management workflows by integrating Smartsheet and Resource Management (RM). It creates DCT Planning Grids for RM project creation, syncs project metadata, updates HH2 time entries, and updates project assignments. 


## Project Structure

```
├── main.py               # GUI interface for chosing updates
├── auto_main.py          # Command-line runner for full automation (for DO deployment)
├── auto_rm.py            # DCT SS grid & RM project creation and field syncing
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

## Classes & Features 

### Admin Functions (`SS_RM_admin.py`)
- Fetches and posts RM time entries.
- Reconciles time entry discrepancies from HH2 export.
- Updates archived projects.
- Handles Sage ID to user matching.

#### How it Works
- run_proj_metadata_update()
  - Runs full update on metadata
- run_assignment_updates()
  - Runs assignment updates in RM linked to users and projects
- run_all()
  - runs all updates

### Project Creation Automation (`auto_rm.py`)
- Creates DCT Planning Grids from a template.
- Initializes RM projects.
- Populates Smartsheet intake sheets with URLs, IDs, and flags.
- Pulls enumerator data from DCT PL and identifies projects not on DCT RM Intake sheet.
- Syncs custom and standard RM Project fields

#### How it Works
"DCT RM Intake" smartsheet is main hub for actions

-  update_projects()
   - Runs full update process
- fetch_new_enums()
  - Fethces enums present on the "DCT PL" Mirror that meet criteria and are not present on "DCT RM Intake" sheet
- add_new_rows()
  - Adds the missing/new enums to the "DCT RM Intake" sheet 
- fetch_intake()
  - Fetches the "DCT RM Intake" sheet data, which holds DCT Grid sheet & RM Project Status per project
  - Adds projects to the self.todo_list if Grid/RM Project creation is needed
- _todo_handler()
  - Handles to do items for creating Grid & RM Project

### SmartsheetBot (`smartsheet_bot.py`)
- Uses Selenium to:
  - Log into Smartsheet.
  - Navigate to project sheets.
  - Enable workload tracking (RM).

#### How it works:
- sb = SmartsheetBot(username, password)
- auto_login()
  - Logs in to Smarthseet with username/password for automation@dowbuilt.com (MFA not required)
- track_workload(sheet_url)
  - Simulates clicking the "Track Workload" button for the given sheet_url

### GUI (`main.py`)
User interface for selecting specific update tasks.
- Live logging viewer.
- Buttons for:
  - Update Projects (DCT + RM)
  - Update Time Entries
  - Update Assignments
  - Run All Updates
  - Exit

### Automated Main (`auto_main.py`)
- Automates the full process for deployment to Digital Oceans & Cron Job


# Notes

## Assumptions
- The `auto_rm.py` script assumes a `<PROJECT NAME> Template` exists in the DCT planning workspace.
- All tokens and constant variables are located in configs/config.json


## Setup Instructions

### 1. Install Python requirements
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
### Config Requirements

```
    "smartsheet_token": "",
    "rm_token": "",
    "hh2_data_sheetid": ,
    "hris_data_sheetid": ,
    "proj_workspace_id": ,
    "proj_list_sheetid": ,
    "rm_to_ss_status_ids": {
        "550725": "Planned",
        "550729": "Active",
        "550726": "Potential",
        "550730": "Completed",
        "684245": "Check-in",
        "684246": "Not Completed",
        "698235": "Blocked"
    },
    "rm_leave_type_ids":{
        "Vacation":, 
        "Sick":, 
        "Parental Leave":
    },
    
    "DCT_RM_INTAKE_SHEET_ID": ,
    "DCT_PL_MIRROR_SHEET_ID": ,
    "PL_3_SHEET_ID": ,
    "DCT_PLANNING_WORKSPACE_ID": ,
    
    "rm_token_key": "",
    "rm_token_token": "",
    
    "ss_auto_token_key": "",
    "ss_auto_token_token": "",
    
    "ss_username": "automation@dowbuilt.com",
    "ss_auto_password_key": "",
    "ss_auto_password_token": "",
  ```
