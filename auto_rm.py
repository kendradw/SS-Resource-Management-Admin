"""# All Projects on RM: Automating Projects
Script: new project-> new RM GRID

     make new Auxiliary Process sheet (RM Intake) every project gets a sheet
     - ALL Projects
     - building or might build = every project
     - completed = add asterisk to end of title
     
    
    RM Grid: auto select rm share thingy (python) - This needs to get turned on in ss (RM turn on tracking thing) - might not be ab option honestly

    Confirm: Works moving forwards and covers backwards

        Every project on the project list has an RM sheet
        
    From the Slack Space
    * Automation new project→ new RM GRID - 
    * New template SAME but f(x) for DCT Status - from DCT mirror PL - this is done?
    * Editing DCT Status (PYTHON) 
        - whut
        - 
    * Add column to PL in appropropriate place (regional sheets)
    * Two Custom Fields: Estimates (PROJECT VALUES) // Estimated Presented (New column in PL)     = vlookup column 4 from PL3.0V3
    """
"""
 √ DCT: 
1. √ get projects from dct intake
2. √ check if dct grid exists
3. √ make dct grid if it doesn't exist
    a. √ add enumerator to dct grid
    b. √ add dct grid url to dct intake sheet
    c. √ add dct grid id to dct intake sheet
 RM:
4. make RM project if it doesn't exist 
    √: automation@dowbuilt.com needs to be an rm resouce admin to workload track
    a. √ add custom fields to RM project - edit the existing script to update the estimate and projected estimate.
5. √ (test) Confirm the rm project was made - grab project ID

5. √ Update Intake sheet
    a. √ check off dct grid and RM project checkboxes
    b. √ add dct grid url to intake sheet
    c. √ add RM project url to intake sheet


"""

from dataclasses import dataclass 
import os
import smartsheet
import json
import requests
from typing import List
import pandas as pd

pd.set_option('future.no_silent_downcasting', True) #downcasting .fillna 

# Local imports
from smartsheet_bot import SmartsheetBot # for automating smartsheet workload tracking
from configs.setup_logger import setup_logger # for logging
from clients.smartsheet_grid import grid # for getting data from smartsheet grid
import configs.crypter as crypter
import sys

#to delete
import json
import pickle
import pandas as pd


def get_resource_path(relative_path):
    """Resolves path to bundled or script-relative resource"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_writable_path(relative_path):
    # Use %APPDATA% or local working dir
    base = os.getenv("APPDATA") or os.path.abspath(".")
    return os.path.join(base, relative_path)


@dataclass
class Project:
    #Project data fields --------------
    name: str                           # project name
    #RM Custom fields ----------------
    enum: str
    dct_status: str                     # referenced in DCT RM Intake sheet from DCT PL Mirror
    architect: str                      # Not a reference value, static
    estimate: str                       # Column ~5 in DCT mirror - referenced in DCT RM Intake sheet
    estimate_presented: str             # New column added specifically to DCT Mirror PL sheet - referenced in intake sheet
    project_code: str                   # RM standard field - job number
    client:str                          #RM standard field - region
    #Tracking fields -----------------
    row_id: int                         # row ID in DCT RM Intake sheet for later update
    rm_project_bool: bool               #rm project exists indicator
    dct_grid_bool: bool                 #DCT planning grid exists indicator
    #Functional fields --------------
    rm_project_id: int = None           #RM Project ID
    dct_grid_url: str = ""              #URL to DCT Planning Sheet
    dct_enum_field_id: int = None       #DCT Planning ENUMERATOR field ID to update with enumerator
    dct_enum_field_set: bool = False    #DCT Planning ENUMERATOR field set indicator
    archived: bool = False              #Bool indicator if project was archived in RM, also adds * to dct sheet
    error: str = ""                     #Error message for posting to smartsheet.

class AutoRM():

    def __init__(self):
        self.log = setup_logger(__name__)
        self.log.info("Initializing RMManager...")
        
        #load config
        config_path = get_resource_path("configs/config.json")
        with open(config_path, "r") as inf:
            self.config = json.load(inf)

        #tokens 
        self.rm_token = crypter.decrypt_from_config("rm_token")
        self.ss_token = crypter.decrypt_from_config("ss_auto_token")
        self.ss_username = self.config.get("ss_username")
        self.ss_password = crypter.decrypt_from_config("ss_auto_password")
        #grid token
        grid.token=self.ss_token

        #endpoints
        self.smart = smartsheet.Smartsheet(access_token=self.ss_token)
        self.smart_base_url = "https://api.smartsheet.com/2.0"
        self.rm_base_url = "https://api.rm.smartsheet.com"

        #const variables, loaded from config
        self.DCT_PL_MIRROR_SHEET_ID = self.config.get("DCT_PL_MIRROR_SHEET_ID")
        self.DCT_PLANNING_WORKSPACE_ID = self.config.get("DCT_PLANNING_WORKSPACE_ID")

        # #class variables
        # self.log.debug(f"Initiazling class variables")
        # self.rm_projects_map = self._fetch_rm_map() # map {} of RM projects as name: id
        # self.template_sheet_id = self._fetch_template() #template grid in SS with the correct formulas. Will find sheet starting with "<PROJECT NAME> TEMPLATE"
        # self.existing_dct_sheets = self._get_existing_dct_sheets() #dictionary of existing DCT sheets for reference
        # self.dct_pl_df = self.fetch_dct() # dataframe of the entire DCT PL Mirror
        # self.active_projects = self.get_active_projects() #list of Project objects of active DCT projects based on DCT Status
        # self.closed_projects = self.get_closed_projects() #list of Project objects of Closed or Completed DCT Status
        # self.dct_pl_cols = self._get_column_map(self.DCT_PL_MIRROR_SHEET_ID) # get column mapping for posting updates
        # self.save_local_data()
        self.load_local_data()

    def save_local_data(self, folder="local_data"):
        import os
        os.makedirs(folder, exist_ok=True)

        # Save JSON-serializable data
        with open(f"{folder}/project_state.json", "w") as f:
            json.dump({
                "rm_projects_map": self.rm_projects_map,
                "template_sheet_id": self.template_sheet_id,
                "existing_dct_sheets": self.existing_dct_sheets,
                "dct_pl_cols": self.dct_pl_cols,
            }, f, indent=4)

        # Save DataFrame
        self.dct_pl_df.to_pickle(f"{folder}/dct_pl_df.pkl")

        # Save Project object lists (via pickle)
        with open(f"{folder}/active_projects.pkl", "wb") as f:
            pickle.dump(self.active_projects, f)
        with open(f"{folder}/closed_projects.pkl", "wb") as f:
            pickle.dump(self.closed_projects, f)

        self.log.info("✅ Local data saved.")

    def load_local_data(self, folder="local_data"):
        import os
        try:
            with open(f"{folder}/project_state.json", "r") as f:
                state = json.load(f)
                self.rm_projects_map = state["rm_projects_map"]
                self.template_sheet_id = state["template_sheet_id"]
                self.existing_dct_sheets = state["existing_dct_sheets"]
                self.dct_pl_cols = state["dct_pl_cols"]

            self.dct_pl_df = pd.read_pickle(f"{folder}/dct_pl_df.pkl")

            with open(f"{folder}/active_projects.pkl", "rb") as f:
                self.active_projects = pickle.load(f)
            with open(f"{folder}/closed_projects.pkl", "rb") as f:
                self.closed_projects = pickle.load(f)

            self.log.info("✅ Local data loaded.")
        except Exception as e:
            self.log.error(f"❌ Failed to load local data: {e}")
            raise



    #region Main Functions -----------------------------------------------------------
    def sync_projects(self):
        """Handles list of todo items by sending them to DCT Grid maker then RM Project maker, 
        then posts updates to smartsheet. Archives orojects marked completed or closed."""
        #get/update all active DCT Projects
        self.log.info("Syncing active projects..")
        self.update_active_projects() # this will create the initial list
        
        #get/update closed/completed projects (Archive in RM + * in DCT sheet name)
        self.log.info("Syncing Closed/Completed projects..")
        self.update_closed_projects()
        self.log.info("COMPLETE: Project sync finished")

    def update_active_projects(self):
        """Creates DCT Sheet if needed. Creates RM project. Syncs Custom & Standard Fields"""
        #create all dct sheets first, then create RM sheets, then update all
        active_projects = self.active_projects[0:2] #remove this is for testing
        for project in active_projects:
            #check if needs dct sheet
            if project.dct_grid_bool == False or project.rm_project_bool == False:
                project = self._existing_grid_handling(project) #check if there's an existing sheet
                if project.dct_grid_bool == False: #check again if it needs one
                    self.log.info(f"Creating new DCT sheets for {project.name}")
                    project = self.create_dct_grid(project) # then create
        
        self.update_dct_ss(active_projects) # all dct sheets have been created - update smartsheet
        #Create RM Projects
        self.log.info("Syncing RM Projects...")
        active_projects = self.create_rm_projects(active_projects)
        self.log.info("Logging new RM projects to DCT PL...")
        self.update_dct_ss(active_projects) # all RM Projects have been created/updated - update smartsheet

    def update_closed_projects(self):
        self.log.info(f"Found {len(self.closed_projects)} closed/completed projects")
        closed_projects = self.closed_projects
        for project in closed_projects:
            if project.rm_project_id is None and project.archived is False:
                project = self._existing_grid_handling(project) #check if there's an existing sheet
            #Has RM ID and not yet archived
            if project.rm_project_id and not project.archived: #needs to be archived
                if self._archive_rm(project) and self._archive_grid_name(project):
                    self.log.info(f"ARCHIVED: {project.name} {project.enum}")
            self.update_dct_ss(closed_projects) # all RM Projects have been created/updated - update smartsheet

        #logging archive to DCT PL sheet
        self.log.info(F"Updating DCT PL with Archive")
        self.update_dct_ss(self.closed_projects) # mark off the archived projects to the ss
    #endregion

    #region Smartsheet ---------------------------------------------------------------
        #region Fetching and Updating Projects --------------------------------------
    def fetch_dct(self):
        """Fetches the DCT PL Mirror sheet as dataframe.
        Returns:
            Full DCT PL Mirror as datafram"""
        self.log.info(f"Fetching DCT PL sheet info...")
        # access DCT RM Intake sheet
        dct_pl = grid(self.DCT_PL_MIRROR_SHEET_ID)
        dct_pl.fetch_content()
        self.log.info(f"Retrieved DCT PL sheet info...")
        return dct_pl.df

    def update_dct_ss(self, project_list:list[Project]):
        """ Updates the DCT PL Mirror with new project data. Updates columns: DCT Planning Grid, RM Project, DCT Grid URL, RM Project ID, 
        Parameters:
            project_list: Project objects / rows to update. 
        """
        #compare against original to only post changes #add originals from original dataframe
        originals= self.get_active_projects()
        originals.extend(self.get_closed_projects()) #add the closed/completed projies
        # create a list of rows to update   
        updated_rows = []
        updated_projects = []
        for project in project_list:
            #skip non-changed projects
            if project in originals:
                continue
            # Create row object
            row = smartsheet.models.Row()
            row.id = project.row_id
            #create cells to update
            cell1 = self._create_ss_cell(self.dct_pl_cols["DCT Planning Grid"], project.dct_grid_bool)
            cell2 = self._create_ss_cell(self.dct_pl_cols["RM Project"], project.rm_project_bool)
            cell3 = self._create_ss_cell(self.dct_pl_cols["DCT Grid URL"], project.dct_grid_url)
            cell4 = self._create_ss_cell(self.dct_pl_cols["RM Project ID"], project.rm_project_id)
            cell5 = self._create_ss_cell(self.dct_pl_cols["RM Archived"], project.archived)
            cell6 = self._create_ss_cell(self.dct_pl_cols["Error"], project.error)
            for cell in [cell1, cell2, cell3, cell4, cell5, cell6]:
                if cell: #append only non null values, otherwise error
                    row.cells.append(cell)
            updated_rows.append(row)
            updated_projects.append(f"{project.enum} {project.name}")

        # Submit update to Smartsheet
        if updated_rows:
            self.log.info(f"Posting {len(updated_rows)} to SS...")
            response = self.smart.Sheets.update_rows(self.DCT_PL_MIRROR_SHEET_ID, updated_rows)
            if response.message == "SUCCESS":
                self.log.info(f"Updated {len(updated_rows)} rows in DCT RM Intake sheet: Projects: {updated_projects}")
            else:
                self.log.error(f"Failed to update rows in DCT RM Intake sheet: {response.message}: {project_list}")

    def get_active_projects(self):
        """Fetches active projects and returns list of Project objects. 
        Active Projects are wheere DCT Status != "Closed" "Complete" or "Inactive". All other statuses are considered active.
        """
        #DCT Status is not inactive, complete, or closed and not None
        active = self.dct_pl_df[~self.dct_pl_df["DCT Status"].isin(["Inactive", "Complete", "Closed"])]
        active = active[active["DCT Status"].notna()]
        active_projects = self._df_to_proj_obj(active) # convert df to list of Project objects
        return active_projects
    
    def get_closed_projects(self):
        """Fetches closed or completed projects and returns a list of Project objects."""
        #DCT Status is complete, or closed 
        closed = self.dct_pl_df[self.dct_pl_df["DCT Status"].isin(["Complete", "Closed"])]
        closed_projects = self._df_to_proj_obj(closed)
        return closed_projects

    def _df_to_proj_obj(self, dataframe):
        """Takes projects from a dataframe and converts them to Project object. Returns list of Projects"""
        projects = []
        for _, row in dataframe.iterrows():
            project = Project(
                row_id=row["id"],
                name=row["NAME"],
                enum=row["ENUMERATOR"],
                architect=row["ARCHITECT"],
                estimate=row["ESTIMATE"],
                dct_status=row["DCT Status"],
                estimate_presented=row["Estimate Presented"],
                project_code=row["JOB NUMBER"],
                client=row["REGION"],
                dct_grid_bool=bool(row["DCT Planning Grid"]),
                rm_project_bool=bool(row["RM Project"]), 
                dct_grid_url=row["DCT Grid URL"],
                rm_project_id=row["RM Project ID"],
                archived = bool(row["RM Archived"])
            )
            projects.append(project)
        return projects
        #endregion

        #region SS Utility Functions ------------------------------------------------
    def _create_ss_cell(self, column_id: int, value):
        if value is not None:
            cell = smartsheet.models.Cell()
            cell.column_id = column_id
            cell.value = value
            return cell
        return None

    def _get_column_map(self, sheet_id: int) -> dict:
        """
        Fetches all columns for a given sheet and returns a dict mapping column names to IDs.
        Params:
        sheet_id: ID of the sheet to fetch columns from.
        Returns:
        A dictionary mapping column titles to their IDs.
        """
        sheet = self.smart.Sheets.get_sheet(sheet_id)
        return {col.title: col.id for col in sheet.columns}

    def _get_existing_dct_sheets(self):
        """Gets a list of Existing DCT sheet projects 
        Returns: dictionary of projects as enum:name
        sheets without enum are saved under dct_sheets["None"].append(sheet.name)
        duplicate sheets are saved as dct_sheets["Duplicates"].append({enum:sheet.name})
        """
        self.log.info("Fetching existing DCT Planning sheets....")
        workspace = self.smart.Workspaces.get_workspace(self.DCT_PLANNING_WORKSPACE_ID)
        dct_sheets = {}
        dct_sheets["None"] = [] #list to hold sheets with name, but no enum
        dct_sheets["Duplicates"] = {} #list to hold duplicate found enum values
        for sheet in workspace.sheets:
            #skip utility sheets
            if str(sheet.name).startswith("_"):
                continue
            enum = self._get_summary_field_value(sheet) #get the enum
            if enum == None: # if there's not one (Manual input)
                dct_sheets["None"].append(sheet.name) # put the unclaimed names into a list
            elif enum in dct_sheets:  
                #duplicates
                dct_sheets["Duplicates"][sheet.name] = {"enum":enum, "url": sheet.permalink}
                dct_sheets["Duplicates"][dct_sheets[enum].get("name")] = {"enum":enum, "url": dct_sheets[enum].get("url")}
                del dct_sheets[enum]
            else:
                dct_sheets[enum] = {"name":sheet.name, "url":sheet.permalink, "id": sheet.id}
        self.log.info(f"{len(dct_sheets)} existing dct sheets fetched")
        self.existing_dct_sheets = dct_sheets
        #Print to file TODO remove
        with open("data/dct.json", "w") as of:
            json.dump(dct_sheets, of, indent=2)
        return dct_sheets
    
    def _get_summary_field_value(self, sheet, sf_title = "Enumerator"):
        """Helper function to retrieve summary field ID, default set to ENUMERATOR
        Returns: summary field value
        Params: Sheet - SS sheet object to get get summary field from"""
        response = self.smart.Sheets.get_sheet_summary_fields(
            sheet.id,    # sheet_id
            exclude='displayValue, image, imageAltText',
        )
        try:
            if response.request_response.status_code == 200:
                fields = response.data
                for field in fields:
                    if sf_title in field.title: # some have "Project Enumerator [MANUAL ENTRY]" soem do not.
                        try:
                            if field.object_value.value: 
                                return field.object_value.value
                        except Exception as e:
                            return None
                self.log.error(f"ERROR: Sheet {sheet.name} does not have ENUMERATOR field.")
            else:
                self.log.error(f"ERROR: Summary fields not returned: {response.message}")
        except Exception as e:
            self.log.error(f"EXCEPTION: {e}")
        
    def _existing_grid_handling(self, project:Project):
        """Checks for existing DCT grid and RM project. Will link existing grid to project or will produce error message that posts to smartsheet."""
        if project.dct_grid_bool is False:
            if project.enum in self.existing_dct_sheets:
                self.log.info(f"Logging existing dct sheet for project {project.name}")
        if project.rm_project_bool is False:
            if project.name in self.rm_projects_map:
                project.rm_project_bool = True
                project.rm_project_id = self.rm_projects_map[project.name]
                self.log.info(f"Logging existing RM project for {project.name}")
        return project
        #endregion
        
        #region DCT Smartsheet Grid Creation -----------------------------------------
    def create_dct_grid(self, project: Project)-> Project:
        """
        Creates a new SS DCT Grid sheet in the "DCT Planning" workspace using the workspace-saved template.
        Parameters:
            project (Project): A Project object with all required (non-optional) fields populated.
        Returns:
            Project: The same Project object with the following optional fields updated:
                    - project.dct_grid_bool
                    - project.dct_sheet_id
                    - project.dct_grid_url
        """
        # Necessity checking & logging
        if project.dct_grid_bool == True:
            self.log.info(f"Existing sheet for {project.name}")
            return
        else:
            self.log.info(f"Creating DCT grid sheet for {project.name}...")

        # Request
        url = f"https://api.smartsheet.com/2.0/workspaces/{self.DCT_PLANNING_WORKSPACE_ID}/sheets?include=data,attachments,cellLinks,discussions,filters,forms,ruleRecipients,rules"
        headers = {
            "Authorization": f"Bearer {self.ss_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": project.name,
            "fromId": self.template_sheet_id,
        }
        self.log.info("Creating DCT Grid...")
        response = requests.post(url, json=payload, headers=headers)

        # Response handling
        if response.status_code == 200:
            data = response.json()
            project.dct_grid_bool = True 
            project.dct_sheet_id = data['result']['id'] 
            project.dct_grid_url = data['result']['permalink']
            self.log.info(f"SUCCESS: Grid created: {project.name} (ID: {project.dct_sheet_id})")
            project = self._add_dct_grid_enum(project) #Adds project enumerator to sheet summary fields
            return project
        else:
            self.log.error(f"FAIL: Grid creation failed for {project.name}. Response: {response.text}")

    def _fetch_template(self):
        """Assigns the class variable "TEMPLATE_SHEET_ID" to the sheet ID of the working template GRID sheet in DCT Planning Workspace"""
        # Get all sheets in the workspace
        workspace = self.smart.Workspaces.get_workspace(self.DCT_PLANNING_WORKSPACE_ID)
        # Find the sheet starts with "_GRID TEMPLATE"
        template_sheet_id = None
        for template in workspace.templates:
            if template.name.startswith("<PROJECT NAME> Template"):
                template_sheet_id = template.id
                break
        if template_sheet_id == None:
            self.log.error("FAILED to get template sheet. Sheet in DCT workspace beginning with '<PROJECT NAME> Template' not found.")
            exit()

        return template_sheet_id

    def _add_dct_grid_enum(self, project: Project, sf_name = "Project Enumerator"):
        """Updates the ENUMERATOR summary field to contain the project enumerator and removes [MANUAL ENTRY] from name, which will populate other summary fields.
        Returns: Updated Project object with "dct_enum_field_set" = True or False if error
        Params: Project object with valid "dct_enum_field_id" value"""
        sf = smartsheet.models.SummaryField()
        sf.id_ = self._get_summary_field_id(project)
        sf.title = sf_name
        sf.object_value = project.enum

        response = self.smart.Sheets.update_sheet_summary_fields(
            project.dct_sheet_id,    # sheet_id
            [sf],
            False    # rename_if_conflict
        )

        if response.message == "SUCCESS":
            project.dct_enum_field_set = True
            return project
        else:
            self.log.error(f"ERROR: sheet {project.name} {project.dct_sheet_id} failed to update enum summary field {response.message}")
            return project
        
    def _get_summary_field_id(self, project: Project, sf_title = "Enumerator"):
        """Helper function to retrieve summary field ID by title, default set to ENUMERATOR. 
        Returns: summary field ID
        Params: Project object with valid "dct_sheet_id" value """
        response = self.smart.Sheets.get_sheet_summary_fields(
            project.dct_sheet_id,    # sheet_id
            exclude='displayValue, image, imageAltText',
        )

        if response.request_response.status_code == 200:
            fields = response.data
            for field in fields:
                if sf_title in field.title: #check if ENUMERATOR in titile ("Manual Entry" part is removed after automated entry)
                    return field.id
            self.log.error(f"ERROR: Sheet {project.name} {project.dct_sheet_id} does not have ENUMERATOR field.")
        else:
            self.log.error(f"ERROR: Summary fields not returned: {response.message}") 
        #endregion 
    #endregion

    #region RM -----------------------------------------------------------------------
        #region Create RM Project
    def create_rm_projects(self, projects:list[Project]):
        """Creates new RM projects for each project in the todo list that does not already have a RM project.
        Uses the RM API to create the project. Does not add custom fields yet.
        Updates the project object with the RM project ID and name, and sets the rm_project_bool to True.
        This function is called after the DCT grid has been created for the project.
        Calls _verify_rm_creation to verify that the RM projects were created successfully.
        Params: None
        Returns: True if project was created, False if project already exists or failed to create.
        """
        if any(project.rm_project_bool is not True for project in projects):
            #Initialize SS bot
            self.log.info("auto_rm Initializing Smartsheet Bot for RM...") 
            #TODO: Headless = true
            smartbot = SmartsheetBot(self.ss_username, self.ss_password, headless=False)

            smartbot.auto_login() #no user input log-in method
            self.log.info(f"Logged in to {self.ss_username} Smartsheet account for RM bot...")

            for project in projects: # loop through sync list
                if project.rm_project_bool is True: #skip created one
                    continue
                # Create new RM project
                if project.dct_grid_url > '' and project.rm_project_bool == False:
                    self.log.info(f"Creating RM Project: {project.name}...")
                    if  not smartbot.track_workload(project.dct_grid_url): #track_workload returns bool
                        self.log.error(f"Failed to create RM project: {project.name}")
                        project.rm_project_bool = False
                        project.error = f"Failed to create RM project: {project.name}"
                
            smartbot.close() # Close the bot session
        # verify that RM projects were created & update summary fields
        projects = self.verify_sync_rm_project(projects) #verify if a project was created and mark project.rm_project_bool true, updates custom fields
        return projects #send em back!
    
    def check_existing_rm(self, project:Project):
        """Double checks if there is an existing RM project for this project.
        Returns:
            existing:bool if the project exists
            project: Project the project object with updates if true"""
        if project.name in self.rm_projects_map:
            project.rm_project_bool = True
            project.rm_project_id =self.rm_projects_map[project.name]
            return project
        return False, project
    
    def verify_sync_rm_project(self, projects:list[Project]):
        """Verifies that the RM projects were created by comparing the RM projects to the todo list.
        Compares by name.
        Params: None   
        """
        #verify that RM projects were created
        self.log.info("Syncing RM project data...")
        rm_projects = self._fetch_rm_map()
        for project in projects: 
            if project.name in rm_projects: #if the project exists in RM its either seasoned, or newly arrived
                if project.rm_project_id == None: #if its fresh, add the RM ID and set the bool
                    project.rm_project_id = rm_projects[project.name]
                    project.rm_project_bool = True
                #Check if summary fields need updates
                self.log.info(f"Found RM Project '{project.name}' for enum {project.enum}. Updating summary fields...")
                project = self.rm_field_updates(project)
            else: #if its not in the RM list, a project didn't get created :(
                self.log.error(f"ERROR: '{project.name}' Not found in RM list...")
                project.error(f"(verify_sync_rm_project) RM Creation error")
                project.rm_project_bool = False
        return projects #Send em back
        #endregion
    
        #region Fetch RM Data -------------------------------------------------------
    def _fetch_rm_map(self):
        """Gets a list of RM project names, enums, and IDs 
        Returns: dictionary of projects as name: {enum, id}
        Example: {"cool Project" : {enum: 02600, id: 1234567890}}
        """
        self.log.info(f"Retrieving RM Projects...")
        endpoint = "/api/v1/projects"
        self.rm_header = {
            "auth": self.rm_token,
            "Content-Type": "application/json",
            "per_page": "1000",
        }
        rm_projects_map = {}
        data = self.paginated_rm_getrequest(endpoint, self.rm_header)
        #TODO: Delete print for debugging
        with open("data/rm_projects.json", "w") as of:
            json.dump(data, of, indent=2)
        for project in data: # loop through projects
            name = str(project["name"])
            rm_projects_map[name] = project["id"] #assign project ID to name for map reference
        with open("data/rm_dict.json", "w") as of:
            json.dump(rm_projects_map, of, indent=2)
        self.log.info(f"Total RM Projects: {len(rm_projects_map)}")
        return rm_projects_map
    
    def paginated_rm_getrequest(self, endpoint, header, params=None,):
        """
        Fetches data from an API endpoint. Handles both single item and paginated responses.

        :param endpoint: The specific endpoint to fetch data from.
        :param headers: Dictionary containing request headers.
        :param params: Dictionary containing any query parameters for the GET request.
        :return: A single item or a list of items aggregated from all pages.
        """
        url = f"{self.rm_base_url}{endpoint}"
        items = []
        while url:
            response = requests.get(url, headers=header, params=params)
            if response.status_code == 200:
                response_json = response.json()
                # Check if response is paginated
                if 'data' in response_json:
                    items.extend(response_json.get('data', []))
                    next_page = response_json.get('paging', {}).get('next')
                    url = f"{self.rm_base_url}{next_page}" if next_page and not next_page.startswith('http') else next_page
                else:
                    return response_json  # Return a single item
            else:
                self.log.error(f"Failed to fetch data: {response.status_code} - {response.reason}")
                break  # Exit loop on failure
        return items if items else []
          
    def _get_rm_fields(self, rm_id: int, standard = False):
        """Gets the RM project fields for the given project from the RM API. 
        Default to custom fields, if standard = True will return standard fields.
        Params: rm_id - RM project ID
        Returns: RM project custom fields as a list of dictionaries or None if not found"""
        url = f"{self.rm_base_url}/api/v1/projects/{rm_id}/custom_field_values"
        if standard == True:
            url = f"{self.rm_base_url}/api/v1/projects/{rm_id}"
        self.rm_headers = {
            "auth": self.rm_token,
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=self.rm_headers)
        if response.status_code == 200:
            data = response.json()
            if standard == False:
                return data.get("data")
            else:
                return data
        else:
            self.log.error(f"ERROR: Failed to get RM project {rm_id} fields from {url}: ERROR MESSAGE: {response.text}")

        #endregion
        #region Post Updates -----------------------------------------------------
    def rm_field_updates(self, project:Project):
        """Checks and updates Standard and Custom fields for a project. If there are no differences it will not post the update to RM.
        Calls _get_rm_fields() to get custom and standard field id's and values
        Checks for differences in the values
        Sends updates if necessary """
        #validity checking
        if project.rm_project_id == None:
            self.log.info(f"{project.name} does not have an RM sheet...")
            return
        cu_fields = self._get_rm_fields(project.rm_project_id)
        # Get all the fieds that need to be updated
        update_custom = {}  #dict of field_id:value for custom fields needing update
        for field in cu_fields:
            field_name, value, rm_id = field["custom_field_name"], field["value"], field.get("id")
            if field_name == "DCT Status":
                if value != project.dct_status:
                    update_custom[rm_id] = project.dct_status
            elif field_name == "Project Enumerator":
                if value != project.enum:
                    update_custom[rm_id] = project.enum
            elif field_name == "Architect":
                if value != project.architect:
                    update_custom[rm_id] = project.architect
            elif field_name == "Estimate":
                if value != project.estimate:
                    update_custom[rm_id] = project.estimate
            elif field_name == "Estimate Presented?":
                if value != project.estimate_presented:
                    if project.estimate_presented: #this can be null for the initial "no"?
                        update_custom[rm_id] = project.estimate_presented
        #send all the updates to get posted
        for id, value in update_custom.items():
            if value:#make sure something exists, idk
                project = self._post_custom_field(id, value, project)

        #now, we check the standard fields. there's only really two to worry about I guess
        st_fields = self._get_rm_fields(project.rm_project_id, standard=True)
        if st_fields.get("ciient") != project.client or st_fields.get("project_code") != project.project_code:
            self.log.info(f"Updating standard fields for project {project}")
            project = self._post_standard_field(project)
        return project #send it back
   
    def _archive_rm(self, project:Project):
        """Marks Arhvive attribute on RM project"""
        data={
            'id':project.rm_project_id,
            'project_code':" ", #remove project code to not interfere with time & expense posting
            }
        data2={
            'id':project.rm_project_id,
            'archived':'true'
            }
        response = requests.put(f"https://api.rm.smartsheet.com/api/v1/projects/{project.rm_project_id}", headers=self.rm_header, data=json.dumps(data))
        response2 = requests.put(f"https://api.rm.smartsheet.com/api/v1/projects/{project.rm_project_id}", headers=self.rm_header, data=json.dumps(data2))
        if response.status_code and response2.status_code == 200:
            self.log.info(f"{project.name} correctly archived in RM")
            project.archived = True
            return True
        else:
            self.log.error(f"Error with archive update: {response.json()}")
            return False

#endregion
        
        #region Post RM Data --------------------------------------------------------
    def _post_custom_field(self, field_id, value, project: Project):
        """Calls the post method on a singular custom field to update the value
        Params:
            field_id: field_id of the custom field to update
            value: Value to be set to the custom field
            project: Project object associated to the fields
        Returns:
            The project object with unchanged, or with added error message attribute.
        """

        url = self.rm_base_url + f"/api/v1/projects/{project.rm_project_id}/custom_field_values/{field_id}"
        response = requests.put(url, headers=self.rm_headers, data=json.dumps({'value':value}))
        
        if response.status_code == 200:
            self.log.info(f"Updated Custom field to value {value} for project {project.name}")
        else:
            self.log.error(f"Error updating custom field: {field_id} : {value} for project {project.name} \n {response.status_code} {response.content}")
            project.error += f"Error updating custom field: {field_id} : {value} Error:{response.status_code} {response.content}"
        return project
        
    def _post_standard_field(self, project:Project):
        """Updates the Standard fields in RM Project. IF error, error messasge will be stored in Project object variable to be posted to smartsheet. 
        Params:
            project: The Project object with updates
        Returns:
            project: The project object with added error message, if any
            """
        data =  {
            'id':project.rm_project_id,
            'project_code':project.project_code,
            'client':project.client
        }
        response = requests.put(f"https://api.rm.smartsheet.com/api/v1/projects/{project.rm_project_id}", headers=self.rm_header, data=json.dumps(data))
        if response.status_code == 200:
            self.log.info(f"Updated {project.name}'s standard field data")
        
        else:
            self.log.error(f"ERROR: Failed to update standard fields for project {project.name} {project.rm_project_id} MESSAGE: {response.text}")
            project.error += f"ERROR: Failed to update one of Project Code {project.project_code} AND/OR Client {project.client} MESSAGE: {response.text}"
        return project
    #endregion
        
    #endregion

# def main():
#     rmm = AutoRM()
#     rmm._get_existing_dct_sheets()
    
#     # #rmm.fetch_new_dct_projects()
#     # p= Project(name='_TEST IT 2.7*', enum='01151', dct_status='status', estimate='estimate', estimate_presented='ep', dct_sheet_id=4834941121548164, rm_project_bool=True, dct_grid_bool='', dct_grid_url='https://app.smartsheet.com/sheets/jphh9fwHW267hcvRq5m25PgwVpGVc34FXcvHFFv1', dct_enum_field_id=6231669148176260)
#     # # p = Project(name= "_Test Formula2", enum="01151", dct_status='status', estimate='estimate', estimate_presented='ep', dct_sheet_id=2687330368311172)
#     # # #rmm.create_DCT_grid(p)
#     # # # # print(p)
#     # # # p = rmm._add_dct_grid_enum(p)
#     # # print(p)
#     # #rmm._fetch_template()
#     # rmm._add_dct_grid_enum(project=p)

    
#     # #compare existing pl to dct planning
#     # rmm.retroactive_DCT_grid()
#     #endregion ------------------------------------------

#     # # Selenium
#     # rmm.initialize_selenium()

#     # # RM handling
#     #rmm.fetch_rm_projects()
#     # print(rmm.get_rm_custom_fields(9038651))

#     # p = Project(name='_TEST Auto_RM', enum='01244', dct_status='Closed', estimate='$7,050,000', estimate_presented=None, row_id=8478043445661572, rm_project_bool=False, dct_grid_bool=True, rm_project_id=None, dct_sheet_id=7554767950663556, dct_grid_url='https://app.smartsheet.com/sheets/w7gPJ6vpWxRhXh4JGC75m7f4V6PrPCwwr3fJrpv1', dct_enum_field_id=None, dct_enum_field_set=True)
#     # rmm.todo_list = [p]
#     # # rmm.create_rm_projects()

#     # #update intake sheet
#     # rmm.update_intake_rows()

#     #standard fields
#     # fields = rmm._get_rm_fields(10441467, standard=True)
#     # print(fields)

#     #checking update/post to SS
#     # rmm.fetch_intake() #get the intak elist
#     # rmm.update_rm_project_data()
#     # rmm.update_intake_rows() 

#     #Main flow ------------------------------------------
#     # rmm.fetch_new_dct_projects() # fetch new projects from DCT RM Intake sheet
#     # rmm.todo_handler() # handle todo list








## RM Project Custom Fields

# All RM projects have two new custom fields. Automates for new, and covers existing projects.

    # Two Custom Fields: Estimates (PROJECT VALUES) // Estimated Presented (New column in PL)

        # Two custom fields: RM tool gets 2 new custom fields in all projects.

            # Confirm: Works moving forwards and covers backwards

    # RM API: Use API to update fields:

        # Estimates: mapped to new RM custom field from PL (Aggregate) ESTIMATE 

        # Estimate Presented: mapped to new RM custom field from DCT mirror ESTIMATE PRESENTED



# RM API: Use API to update fields:
# Estimates: mapped to new RM custom field from PL (Aggregate) ESTIMATE 
#get enumerator for project from RM field
# go to PL 3.0 
# get the data
# get the data from row ENUM for column Estimate
# Create new custome field for this rm project
# call it estimate
# Fill in the value that was just retrieved from SS
# Estimate Presented: mapped to new RM custom field from DCT mirror ESTIMATE PRESENTED
# get enumerator for project from RM field
# go to DCT Mirror sheet
# get the data
# get the data from row ENUM for column ESTIMATE PRESENTED
# Create new custome field for this rm project
# call it estimate
# Fill in the value that was just retrieved from SS


# RM API: Update fields with data from PL and DCT Mirror

