#region ---- Imports ----
from dataclasses import dataclass 
import os
import smartsheet
import json
import requests
import logging
import pandas as pd
pd.set_option('future.no_silent_downcasting', True) #downcasting .fillna 

# Local imports
from smartsheet_bot import SmartsheetBot # for automating smartsheet workload tracking
from clients.smartsheet_grid import grid # for getting data from smartsheet grid
import configs.crypter as crypter
import sys
#endregion

def get_resource_path(relative_path):
    """Resolves path to script-relative resource for .exe use"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

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

    def __init__(self, logger: logging.Logger):
        self.log = logger
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
        self.rm_header = {"auth": self.rm_token, "Content-Type": "application/json", "per_page": "1000",}

        #const variables, loaded from config
        self.DCT_PL_MIRROR_SHEET_ID = self.config.get("DCT_PL_MIRROR_SHEET_ID")
        self.DCT_PLANNING_WORKSPACE_ID = self.config.get("DCT_PLANNING_WORKSPACE_ID")

        #class variables
        self.log.debug(f"Initiazling class variables")
        self._fetch_rm_map() # map {} of RM projects as name: id
        self.template_sheet_id = self._fetch_template() #template grid in SS with the correct formulas. Will find sheet starting with "<PROJECT NAME> TEMPLATE"
        self.existing_dct_sheets = self._get_existing_dct_sheets() #dictionary of existing DCT sheets for reference
        self.dct_pl_df = self.fetch_dct() # dataframe of the entire DCT PL Mirror
        self.active_projects = self.fetch_active_projects() #list of Project objects of active DCT projects based on DCT Status
        self.closed_projects = self.fetch_closed_projects() #list of Project objects of Closed or Completed DCT Status
        self.dct_pl_cols = self._get_column_map(self.DCT_PL_MIRROR_SHEET_ID) # get column mapping for posting updates
        self.created_grids = [] #list of newly created projects to link fetch RM ID to link to DCT PL
        self.need_rm = [] # list of projects to be sent to selenium to "track workload"

    #region Main Functions -----------------------------------------------------------
    def sync_projects(self):
        """Main method to sync all projects by sending them to DCT Grid maker then RM Project maker, 
        then posts updates to smartsheet. Updates summary fields in RM and Archives orojects marked completed or closed."""
        #get/update all active DCT Projects
        self.log.info("Syncing active projects..")
        self.handle_active_projects() # this will create the initial list
        
        #get/update closed/completed projects (Archive in RM + * in DCT sheet name)
        self.log.info("Syncing Closed/Completed projects..")
        self.update_closed_projects()
        self.log.info("---- COMPLETE: Project sync finished ----")

    def handle_active_projects(self):
        """Creates DCT Sheet if needed. Creates RM project. Syncs Custom & Standard Fields"""
        #create all dct sheets first, then create RM sheets, then update all
        active_projects = self.active_projects
        for project in active_projects: # create grid loop
            #check if needs dct sheet
            if project.dct_grid_bool is False:
                project = self._check_existing_grid(project) #check if there's an existing sheet that didn't get linked
                if project.dct_grid_bool is False: # now check again if it needs one
                    project = self.create_dct_grid(project) # then create
                    if project is None:
                        continue
            if project.dct_grid_url and project.rm_project_id is None: #there's a grid but no RM
                project = self._check_existing_rm(project) #check if there's an existing project that got lost
                if project.rm_project_id is None: # if it still needs an RM project
                    self.need_rm.append(project)
        self.post_to_dct_pl(active_projects) # all dct sheets have been created - update smartsheet
        #Create all RM projects that need one
        if self.need_rm:
            self.log.info(f"Creating {len(self.need_rm)} RM Projects...")
            created = self.create_rm_project(self.need_rm) #creates but does not fetch ID
            created = self.instantiate_rm_projects(created) # fetches ID and sets summary fields
            self.log.info("Logging new RM project ID's to DCT PL...")
            self.post_to_dct_pl(active_projects) # all RM Projects have been created/updated - update smartsheet

        for project in active_projects: #sync all fields for connected projects
            if project.dct_grid_url and project.rm_project_id:
                self.sync_rm_fields(project)
        self.log.info(f"---- ACTIVE PROJECT SYNC COMPLETE ----")


    def update_closed_projects(self):
        self.log.info(f"Found {len(self.closed_projects)} closed/completed projects")
        closed_projects = self.closed_projects
        for project in closed_projects:
            #this was to catch projects that were created manually in RM and not tracked on DCT PL - leaving off for now. 
            # if self.rm_archived_map.get(project.name):
            #     self.log.info(f"Logging existing archived RM project for {project.name}")
            #     project.rm_archived = True
            #     project.rm_project_id = self.rm_archived_map.get(project.name)
            # if project.dct_status != "Closed" and project.dct_status != "Complete":
            #     self.log.error(f"ERROR: PROJECT IS NOT TO BE ARCHIVED {project.enum} {project.name} - {project.dct_status}")
            # if project.rm_project_id is None and project.archived is False:
            #     project = self._check_existing(project) #check if there's an existing sheet
            # #Has RM ID and not yet archived
            if project.rm_project_id and not project.archived: #needs to be archived
                if project.rm_project_id in self.rm_archived_list:
                    project.archived = True
                # project = self._archive_rm(project)
                project = self._archive_grid_name(project)
        
        #logging archive to DCT PL sheet
        self.log.info(F"Updating DCT PL with Archive Status for")
        self.post_to_dct_pl(self.closed_projects) # mark off the archived projects to the ss
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
        if dct_pl.df.empty:
            self.log.error(f"ERROR: Fetching DCT PL ... Closing program")
            exit(-1)
        self.log.info(f"Retrieved DCT PL sheet info...")
        return dct_pl.df

    def post_to_dct_pl(self, project_list:list[Project]):
        """ Updates the DCT PL Mirror with new project data. Updates columns: DCT Planning Grid, RM Project, DCT Grid URL, RM Project ID, 
        Parameters:
            project_list: Project objects / rows to update. 
        """
        #compare against original to only post changes #add originals from original dataframe
        originals= self.fetch_active_projects()
        originals.extend(self.fetch_closed_projects()) #add the closed/completed projies
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
            cell4 = self._create_ss_cell(int(self.dct_pl_cols["RM Project ID"]), project.rm_project_id)
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
    
    def _archive_grid_name(self, project:Project):
        """Adds * to archive project name"""
        grid_name = self.existing_dct_sheets.get(project.enum, {}).get("name", None)
        sheet_id = self.existing_dct_sheets.get(project.enum, {}).get("id", None)
        if grid_name is None or sheet_id is None:
            project.error += "No DCT sheet found"
            return project
        #necessity checking
        if grid_name[-1] == "*":
            return project
        
        new_name=grid_name+"*"
        try:
            updated_sheet = self.smart.Sheets.update_sheet(
            # sheet id
            int(sheet_id), 
            # new name
            smartsheet.models.Sheet({
                'name': new_name}))
        except Exception as e:
            self.log.error(f"Error updating archived sheet name: {grid_name} - {e}")
            project.error += f"Error updating sheet name: {e}"
        return project
    
    def fetch_active_projects(self):
        """Fetches active projects and returns list of Project objects. 
        Active Projects are wheere DCT Status != "Closed" "Complete" or "Inactive". All other statuses are considered active.
        """
        #DCT Status is not inactive, complete, or closed and not None
        active = self.dct_pl_df[~self.dct_pl_df["DCT Status"].isin(["Inactive", "Complete", "Closed"])]
        active = active[active["DCT Status"].notna()]
        active_projects = self._df_to_proj_obj(active) # convert df to list of Project objects
        self.log.info(f"Retrieved {len(active_projects)} from DCT PL")
        return active_projects
    
    def fetch_closed_projects(self):
        """Fetches closed or completed projects and returns a list of Project objects."""
        #DCT Status is complete, or closed 
        closed = self.dct_pl_df[self.dct_pl_df["DCT Status"].isin(["Complete", "Closed"])]
        closed_projects = self._df_to_proj_obj(closed)
        self.log.info(f"Retrieved {len(closed)} from DCT PL")
        return closed_projects

    def _df_to_proj_obj(self, dataframe):
        """Takes projects from a dataframe and converts them to Project object. Returns list of Projects"""
        projects = []
        for _, row in dataframe.iterrows():
            project = Project(
                row_id=row["id"],
                name=row["NAME"],
                enum=row["ENUMERATOR"], #has no leading 0
                architect=row["ARCHITECT"],
                estimate=row["ESTIMATE"],
                dct_status=row["DCT Status"],
                estimate_presented=row["Estimate Presented"],
                project_code=row["JOB NUMBER FIXED"],
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
        dct_sheets["None"] = [] #list to hold sheets with name, but no 
        dct_sheets["Duplicates"] = {} #list to hold duplicate found enum values
        for sheet in workspace.sheets:
            #skip utility sheets
            if str(sheet.name).startswith("_"):
                continue
            enum = self._get_summary_field_value(sheet)#get the enum
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
        
    def _check_existing_grid(self, project:Project):
        """Checks for existing DCT grid and RM project. Will link existing grid to project or will produce error message that posts to smartsheet."""
        if project.dct_grid_bool is False:
            if project.enum in self.existing_dct_sheets:
                project.dct_grid_bool = True
                project.dct_grid_url =self.existing_dct_sheets.get(project.enum).get("url")
                self.log.info(f"Logging existing dct sheet for project {project.enum} '{project.name}'")
        return project
    
    def _check_existing_rm(self, project:Project):
        """Helps find lost RM projects. If an RM project was created but not properly linked to the DCT PL project."""
        if project.rm_project_bool is False:
            sheet_name = self.existing_dct_sheets.get(project.enum, {}).get("name", None)
            if sheet_name is None:
                return project
            if sheet_name in self.rm_projects_map: #there's a matching sheet name
                rm_enum = self._get_rm_enum(self.rm_projects_map[sheet_name]) #validate enumerator is matches or is empty (newly instantiated project)
                if  rm_enum == project.enum or rm_enum is None:
                    self.log.info(f"Found lost RM project for. Linking existing RM project for {project.name} {project.enum} to RM ID: {self.rm_projects_map[sheet_name]}")
                    project.rm_project_bool = True
                    project.rm_project_id = self.rm_projects_map[sheet_name]
                    
            # ---- Backtracking logic -----
            # if sheet_name.endswith("*"): #for backtracking, may cause errors moving forward?
            #     sheet_name = sheet_name.rstrip("*")
            # elif project.name in self.rm_archived_map: #backtracking - may cause future errors?
            #     project.archived = True 
            #     project.rm_project_id = self.rm_archived_map[project.name] 
            #     project.rm_project_bool = True
            
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
        if project.dct_grid_url:
            self.log.info(f"Existing sheet for {project.name}: {project.dct_grid_url}")
            return
        else:
            self.log.info(f"Creating DCT grid sheet for {project.enum} {project.name}...")

        # Request
        url = f"https://api.smartsheet.com/2.0/workspaces/{self.DCT_PLANNING_WORKSPACE_ID}/sheets?include=data,attachments,discussions"
        headers = {
            "Authorization": f"Bearer {self.ss_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "name": f"{project.name}_{project.enum}", #create with enum for unique matching, this can be removed later on. 
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
    def create_rm_project(self, projects:list[Project]):
        """Creates new RM projects for each project in the list using selenium.
        Params: projects: list of projects to create RM Project for.
        Returns: updated projects list
        """
        if any(project.rm_project_bool is not True for project in projects): #make sure atleast one needs it and it was not an error
            #Initialize SS bot
            self.log.info("auto_rm Initializing Smartsheet Bot for RM...") 
            #TODO: Headless = False for viewing
            smartbot = SmartsheetBot(self.ss_username, self.ss_password, logger= self.log, headless=True)

            smartbot.auto_login() #no user input log-in method
            self.log.info(f"Logged in to {self.ss_username} Smartsheet account for RM bot...")

            for project in projects: # loop through sync list
                if project.dct_grid_url and project.rm_project_bool == False:
                    self.log.info(f"Creating RM Project: {project.name}...")
                    if  not smartbot.track_workload(project.dct_grid_url): #track_workload returns bool
                        self.log.error(f"Failed to create RM project: {project.name}")
                        project.rm_project_bool = False
                        project.error = f"Failed to create RM project: {project.name}"
                    else:
                        # If workload was tracked, add to list of newly created projects. 
                        self.created_grids.append(project)
            smartbot.close() # Close the bot session
        return projects #send em back!
        
    def verify_sync_rm_project(self, projects:list[Project]):
        """Verifies that the RM projects were created by searching repulling all RM projects and searching for the newly added name.
        Compares by name.
        Params: None   
        """
        #verify that RM projects were created
        self.log.info("Syncing RM project data...")
        self._fetch_rm_map()
        for project in projects: 
            if project.rm_project_bool == False:
                project = self._check_existing(project)
                #Check if summary fields need updates
            if project.rm_project_bool == True:
                self.log.info(f"Checking summary fields for {project.enum} '{project.name}'")
                project = self.sync_rm_fields(project)
            else: #if its not in the RM list, a project didn't get created :(
                self.log.error(f"ERROR: '{project.name}' Not found in RM list...")
                project.error += f"ERROR: Verify Sync - RM Creation error"
                project.rm_project_bool = False
        return projects #Send em back
    
    def instantiate_rm_projects(self, created_projects:list[Project]):
        """Refetches the list of RM projects to search for projects in self.created_projects(). Instantiates the RM project summary fields"""
        self._fetch_rm_map() #grab updated data. saves to self.rm_projects_map and self.rm_archived_map
        #match to enumerator added RM project name
        for project in created_projects:
            name_enum = f"{project.name}_{project.enum}"
            if name_enum in self.rm_projects_map: #these should be unique, matched by enum appended to end of name
                project.rm_project_bool = True
                project.rm_project_id = self.rm_projects_map[name_enum] #store the rm id
                # set initial summary fields
                self.sync_rm_fields(project)
            else:
                error = f"Newly created project grid {project.name} {project.dct_grid_url} not found in RM." 
                self.log.error(error) # log to log
                project.error += error # log to ss
        return created_projects
        #endregion
    
        #region Fetch RM Data -------------------------------------------------------
    def _fetch_rm_map(self):
        """Gets a list of RM project names, enums, and IDs 
        Returns: None, sets self.rm_projects_map
        Example: {"cool Project" : {enum: 02600, id: 1234567890}}
        """
        self.log.info(f"Fetching RM Projects...")
        endpoint = "/api/v1/projects?with_archived=true"
        self.rm_projects_map = {}
        self.rm_archived_list = []
        data = self.paginated_rm_getrequest(endpoint, self.rm_header)
        for project in data: # loop through projects
            name = str(project["name"])
            if project["archived"] == True:
                self.rm_archived_list.append(project["id"])
            else:
                self.rm_projects_map[name] = project["id"] #assign project ID to name for map reference
        self.log.info(f"Total RM Projects: {len(self.rm_projects_map)+len(self.rm_archived_list)}")
        self.log.debug(f"ACTIVE: {self.rm_projects_map}")
        self.log.debug(f"ARCHIVED: {self.rm_archived_list}")
        
    
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
        Returns: EITHER custom fields as a list of dictionaries [{"custom_field_name": field name, "value": field value, "id":field uid}, {...}].
        OR With standard = true, standard fields return as dictionary {"client":, "project_code":}"""
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
            return f"ERROR: Failed to get RM project {rm_id} fields from {url}: ERROR MESSAGE: {response.text}"
        
    def _get_rm_enum(self, rm_id):
        """Retrieves enumerator from RM project. Returns -1 if field not found"""
        cfields = self._get_rm_fields(rm_id)
        for field in cfields:
            field_name, value = field["custom_field_name"], field["value"]
            if field_name == "Project Enumerator":
                return value
        self.log.error(F"ERROR: custom field 'Project Enumerator' not found for RM project {rm_id}")
        return -1
        #endregion
        #region Post Updates -----------------------------------------------------
    def sync_rm_fields(self, project:Project):
        """Checks and updates Standard and Custom fields for a project. If there are no differences it will not post the update to RM.
        Will only change enumerator and job code if fields are blank in RM. Fields should be static and updates should not be made once set."""
        #validity checking
        if project.rm_project_id is None:
            self.log.info(f"{project.name} does not have an RM sheet...")
            return
        cu_fields = self._get_rm_fields(project.rm_project_id)
        if isinstance(cu_fields, str): #returns error string 
            project.error += cu_fields
            return project
        # Get all the fieds that need to be updated
        update_custom = {}  #dict of field_id:value for custom fields needing update
        for field in cu_fields:
            field_name, value, rm_id = field["custom_field_name"], field["value"], field.get("id")
            if field_name == "DCT Status":
                if value != project.dct_status:
                    update_custom[rm_id] = project.dct_status
            elif field_name == "Project Enumerator":
                if value is None and project.enum: # should only update once
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

        #now, we check the standard fields.
        st_fields = self._get_rm_fields(project.rm_project_id, standard=True)
        if isinstance(st_fields, str):
            project.error += st_fields
            return project
        if st_fields.get("client") != project.client :
            project = self._post_standard_field(project, "client", project.client)
        if st_fields.get("project_code") is None and project.project_code:
            project = self._post_standard_field(project, "project_code", project.project_code)
        
        return project 
   
    def _archive_rm(self, project:Project):
        """Marks Arhvive attribute on RM project"""
        self.log.info(f"Archiving {project.name}")
        data2={
            'id':project.rm_project_id,
            'archived':'true'
            }
        response2 = requests.put(f"https://api.rm.smartsheet.com/api/v1/projects/{project.rm_project_id}", headers=self.rm_header, data=json.dumps(data2))
        if  response2.status_code == 200:
            self.log.info(f"{project.enum} {project.name} with DCT Status {project.dct_status} archived in RM {project.rm_project_id}")
            project.archived = True
        else:
            self.log.error(f"Error with archive update: {response2.json()}")
            project.error += f"Error with archive update: {response2.json()}"
        return project

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
        
    def _post_standard_field(self, project:Project, key:str, value:str):
        """Updates the Standard fields in RM Project. IF error, error messasge will be stored in Project object variable to be posted to smartsheet. 
        Params:
            project: The Project object with updates
        Returns:
            project: The project object with added error message, if any
            """
        data =  {
            key:value
        }
        response = requests.put(f"https://api.rm.smartsheet.com/api/v1/projects/{project.rm_project_id}", headers=self.rm_header, data=json.dumps(data))
        if response.status_code == 200:
            self.log.info(f"Updated {project.enum} {project.name} (RM ID: {project.rm_project_id}) standard field {key} to {value}")
        
        else:
            error = f"ERROR: Failed to update standard field {key} to {value} for project {project.enum} {project.name} {project.rm_project_id} MESSAGE: {response.text}"
            self.log.error(error)
            project.error += error
        return project
    #endregion
        
    #endregion



