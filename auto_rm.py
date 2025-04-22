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
    TODO: automation@dowbuilt.com needs to be an rm resouce admin to workload track
    a. √ add custom fields to RM project - edit the existing script to update the estimate and projected estimate.
5. √ (test) Confirm the rm project was made - grab project ID

5. √ Update Intake sheet
    a. √ check off dct grid and RM project checkboxes
    b. √ add dct grid url to intake sheet
    c. √ add RM project url to intake sheet

"""

from dataclasses import dataclass 
import os # for loading environment variables
from dotenv import load_dotenv # for loading environment variables
import smartsheet
import json
import requests
from typing import List
import pandas as pd
import time #sleep used in update_projects()
pd.set_option('future.no_silent_downcasting', True) #downcasting .fillna

# Local imports
from smartsheet_bot import SmartsheetBot # for automating smartsheet workload tracking
from configs.setup_logger import setup_logger # for logging
from clients.smartsheet_grid import grid # for getting data from smartsheet grid
import configs.crypter as crypter

@dataclass
class Project:
    #Project data fields ---------------
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
    dct_sheet_id: int =  None           #DCT Planning Sheet ID
    dct_grid_url: str = ""              #URL to DCT Planning Sheet
    dct_enum_field_id: int = None       #DCT Planning ENUMERATOR field ID to update with enumerator
    dct_enum_field_set: bool = False    #DCT Planning ENUMERATOR field set indicator
    
class AutoRM():

    def __init__(self):
        #logger
        self.log = setup_logger(__name__, file_path="configs/log.log")
        self.log.info("Initializing RMManager...")
        
        #load config
        with open("configs/config.json", "r") as inf:
            self.config = json.load(inf)

        #tokens 
        load_dotenv("configs\.env")
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
        self.DCT_RM_INTAKE_SHEET_ID = self.config.get("DCT_RM_INTAKE_SHEET_ID")
        self.DCT_PL_MIRROR_SHEET_ID = self.config.get("DCT_PL_MIRROR_SHEET_ID")
        self.PL_3_SHEET_ID = self.config.get("PL_3_SHEET_ID")
        self.DCT_PLANNING_WORKSPACE_ID = self.config.get("DCT_PLANNING_WORKSPACE_ID")

        #class variables
        self.log.debug(f"Initiazling class variables")
        self.todo_list = [] # list of projects that need either DCT grid or RM Project
        self.rm_projects_dict = {} # list of RM projects as name: id
        self.template_sheet_id = self._fetch_template() #template grid in SS with the correct formulas. Will find sheet starting with "<PROJECT NAME> TEMPLATE"
        self.failed_rm_projects = [] # list of RM projects that failed to create
        self.dct_updates = False # tracking if there dct sheet updates to post to smartsheet
    
    #region Main Functions -----------------------------------------------------------
    def update_projects(self):
        enum_list = self.fetch_new_enums() #get enums to be added
        self.add_new_rows(enum_list) #add the new rows to smartsheet by enum, this will reference the other data
        time.sleep(10) #give it some time to thinky first
        self.fetch_intake() #get that newly updated intake sheet, adds projects to self.todo_list
        self.todo_handler() #now it's time to process that todo_list

    def todo_handler(self):
        """
        Add dct project
        Add rm project
        update smartsheet
        """
        """Handles list of todo items by sending them to DCT Grid maker then RM Project maker"""
        if len(self.todo_list) == 0:
            self.log.info("No todo items...")
            return
        #create DCT grid sheets
        for project in self.todo_list:
                project = self.create_dct_grid(project)
        #update intake sheet with DCT grid creation
        if self.dct_updates:
            self.log.info("Updating DCT Intake with grid sheet links...")
            self.update_intake_rows()
        # create RM projects with selenium for each project in the todo list
        self.log.info("Creating RM Projects...")
        self.create_rm_projects() 
        #update intake sheet with new project data
        self.log.info("Checking off RM projects on DCT Intake sheet... ")
        self.update_intake_rows() 
       
    #endregion

    #region Smartsheet ---------------------------------------------------------------
        #region Fetching and Updating Projects --------------------------------------
    def fetch_intake(self):
        """Fetches new projects on the Project List since last script execution
        - √ Set up RM Intake sheet as auxilliary sheet 
        - √ place a checkmark there for DCT Planning grid and RM Project part
        - that will use the script to check for the connection tho so no human has to checkmark it, they can just check it if needed
        Fetches rows from the "DCT RM Intake | PL 3.0" sheet located in "Auxilliary Intake" folder.
        Adds todo projects to self.todo_list. Todo projects need either or DCT Planning grid or RM Project
        """
        self.log.info(f"Fetching DCT Intake sheet info...")
        # access DCT RM Intake sheet
        intake = grid(self.DCT_RM_INTAKE_SHEET_ID)
        intake.fetch_content()
        #Filter for rows with todo items - DCT Planning grid or RM Project not checked off
        try:
            todo = intake.df[
                (intake.df['DCT Planning Grid'].isna() | (intake.df['DCT Planning Grid'] == False)) |
                (intake.df['RM Project'].isna() | (intake.df['RM Project'] == False))]
        except Exception as e:
            self.log.error(f"ERROR: {e}")
        for _, row in todo.iterrows():
            project = Project(
                row_id=row["id"],
                name=row["NAME"],
                enum=row["ENUMERATOR"],
                architect=["ARCHITECT"],
                estimate=row["ESTIMATE"],
                dct_status=row["DCT Status"],
                estimate_presented=row["Estimate Presented"],
                project_code=row["JOB NUMBER"],
                client=row["REGION"],
                dct_grid_bool=bool(row["DCT Planning Grid"]),
                rm_project_bool=bool(row["RM Project"]), 
                dct_grid_url= row["DCT Grid URL"]
            )
            self.todo_list.append(project)
        if len(self.todo_list) == 0:
            self.log.info("No todo items from DCT RM Intake | PL 3.0")
        else:
            self.log.info(f"Retrieved {len(self.todo_list)} projects from DCT RM Intake | PL 3.0")

    def update_intake_rows(self):
        """ Updates the DCT RM Intake rows that were modified in the todo list.
        calls _create_ss_cell to create the cells to update.
        calls _get_column_map to get the column ID mapping for the DCT RM Intake sheet.
        Params: None"""
        # get columns ID mapping for the DCT RM Intake sheet
        intake_cols = self._get_column_map(self.DCT_RM_INTAKE_SHEET_ID)
        # create a list of rows to update
        updated_rows = []
        for project in self.todo_list:
            # Create row object
            row = smartsheet.models.Row()
            row.id = project.row_id

            #create cells to update
            cell1 = self._create_ss_cell(intake_cols["DCT Planning Grid"], project.dct_grid_bool)
            cell2 = self._create_ss_cell(intake_cols["RM Project"], project.rm_project_bool)
            cell3 = self._create_ss_cell(intake_cols["DCT Grid URL"], project.dct_grid_url)
            cell4 = self._create_ss_cell(intake_cols["RM Project ID"], project.rm_project_id)
            cell5 = self._create_ss_cell(intake_cols["DCT Grid ID"], project.dct_sheet_id)

            for cell in [cell1, cell2, cell3, cell4, cell5]:
                if cell: #append only non null values
                    row.cells.append(cell)
            updated_rows.append(row)
        # Submit update to Smartsheet
        if updated_rows:
            response = self.smart.Sheets.update_rows(self.DCT_RM_INTAKE_SHEET_ID, updated_rows)
            if response.message == "SUCCESS":
                self.log.info(f"Updated {len(updated_rows)} rows in DCT RM Intake sheet")
            else:
                self.log.error(f"Failed to update rows in DCT RM Intake sheet: {response.message} TODO LIST: {self.todo_list}")

    def fetch_new_enums(self):
        """Fetches projects that need to be added to the intake sheet"""
        dct_pl = grid(self.DCT_PL_MIRROR_SHEET_ID)
        dct_intake = grid(self.DCT_RM_INTAKE_SHEET_ID)
        dct_pl.fetch_content()
        dct_intake.fetch_content()

        #filter to relevant columns and clean mising enumerators
        filtered_pl = dct_pl.df[["ENUMERATOR", "NAME", "STATUS"]]
        #status is either active or inactive
        filtered_pl = filtered_pl[
            (filtered_pl["STATUS"].isin(["Active", "Inactive"]))
        ] 
        # reduce to just enumerators
        filtered_intake = dct_intake.df[["ENUMERATOR"]]
        filtered_intake = filtered_intake[filtered_intake["ENUMERATOR"].notna()] #skip any blank rows

        # missing_enums is where pl enumerator is not~ in DCT intake enumerator
        missing_enum_rows = filtered_pl[~filtered_pl["ENUMERATOR"].isin(filtered_intake["ENUMERATOR"])].drop_duplicates()
        #convert to list
        missing_enums = missing_enum_rows["ENUMERATOR"].dropna().unique().tolist()
        return missing_enums     

    def add_new_rows(self, enum_list: list[int]):
        """Adds new rows to the DCT intake sheet by enumerator. The rest of the columns are references based on that"""
        if len(enum_list) < 1: #if there's nothing, go away
            return
        intake_cols = self._get_column_map(self.DCT_RM_INTAKE_SHEET_ID) #get column id's 
        new_rows = []
        for enum in enum_list: #each enum gets a row
            row = smartsheet.models.Row()
            cell = self._create_ss_cell(intake_cols["ENUMERATOR"], enum) #col id and value 
            row.cells.append(cell) #append to row
            new_rows.append(row) #append row to update list
        # send to ss
        self.log.info(f"Sending {len(new_rows)} new rows to DCT Intake sheet...")
        response = self.smart.Sheets.add_rows(self.DCT_RM_INTAKE_SHEET_ID,new_rows)
        if response.message == "SUCCESS":
            self.log.info(f"Updated {len(new_rows)} rows in DCT RM Intake sheet")
        else:
            self.log.error(f"ERROR: Failed to add rows by enum in DCT RM Intake sheet: {response.message} ENUMS: {enum_list}")

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
        #endregion

        #region DCT Smartsheet Grid Creation -----------------------------------------
    def create_dct_grid(self, project: Project):
        """Creates new SS Grid sheet in DCT Planning from template for new project.
        Calls _add_dct_grid_enum to add the enumerator to summary field to populate formulas. 
        Sheet name = Project.name """

        # Necessity checking & logging
        if project.dct_grid_bool == True:
            self.log.info(f"Existing sheet for {project.name}")
            return
        else:
            self.dct_updates = True
            self.log.info(f"Creating DCT grid sheet for {project.name}...")
        # Request requirements
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
            project = self._add_dct_grid_enum(project)
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
    def create_rm_projects(self):
        """Creates new RM projects for each project in the todo list that does not already have a RM project.
        Uses the RM API to create the project. Does not add custom fields yet.
        Updates the project object with the RM project ID and name, and sets the rm_project_bool to True.
        This function is called after the DCT grid has been created for the project.
        Calls _verify_rm_creation to verify that the RM projects were created successfully.
        Params: None
        Returns: True if project was created, False if project already exists or failed to create.
        """
        #initialize smartsheet bot for RM
        self.log.info("auto_rm Initializing Smartsheet Bot for RM...") 
        smartbot = SmartsheetBot(self.ss_username, self.ss_password, headless=False)
        #TODO: replace with non-user log in
        smartbot.user_login_auto()
        self.log.info("Logged in to Smartsheet Bot for RM...")
        created_projects = False # flag to check if any projects were created
        for project in self.todo_list: # loop through projects in todo list
            # Create new RM project
            if project.dct_grid_url > '' and project.rm_project_bool == False:
                self.log.info(f"Creating RM Project: {project.name}")
                if  not smartbot.track_workload(project.dct_grid_url):
                    self.log.error(f"Failed to create RM project: {project.name}")
                    project.rm_project_bool = False
                else:
                    created_projects = True
        # Close the bot session
        smartbot.close()

        # verify that RM projects were created & update summary fields
        if created_projects:
            self.log.info(F"Verifying RM project creation...")
            self.update_rm_project_data() #verify if a project was created and mark project.rm_project_bool true, updates custom fields
        #endregion
    
        #region Fetch RM Data -------------------------------------------------------
    def fetch_rm_projects(self):
        """Gets a list of RM project names, enums, and IDs 
        Returns: dictionary of projects as name: {enum, id}
        Example: {"cool Project" : {enum: 02600, id: 1234567890}}
        """
        #TODO: pull only projects that were created today to improve efficiency
        #Get all projects in RM
        endpoint = "/api/v1/projects"
        headers = {
            "auth": self.rm_token,
            "Content-Type": "application/json",
            "per_page": "1000",
        }
        data = self.paginated_rm_getrequest(endpoint, headers)

        with open("data/rm_projects.json", "w") as of:
            json.dump(data, of, indent=2)
        for project in data: # loop through projects
            name = str(project["name"])
            self.rm_projects_dict[name] = project["id"] #assign project ID to enum
        self.log.info(f"RM Projects: {len(self.rm_projects_dict)}")
        self.log.info(f"LEN OF RAW DATA: {len(data)}")
        return self.rm_projects_dict
    
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

    def update_rm_project_data(self):
        """Verifies that the RM projects were created by comparing the RM projects to the todo list.
        Compares by name.
        Params: None   
        """
        #verify that RM projects were created
        self.log.info("Updating RM project data...")
        rm_projects = self.fetch_rm_projects()
        for project in self.todo_list: #goes through entire todo_list, which consists of full intake sheet
            if project.name in rm_projects: #if the project exists in RM its either seasoned, or newly arrived
                if project.rm_project_id == None: #if its fresh, add the RM ID and set the bool
                    project.rm_project_id = rm_projects[project.name]
                    project.rm_project_bool = True
                #Check if summary fields need updates
                self.log.info(f"Found RM Project '{project.name}'. Updating summary fields...")
                self.rm_field_updates(project)
            else: #if its not in the RM list, a project didn't get created :(
                self.failed_rm_projects.append(project)
                project.rm_project_bool = False
        self.log.info(f"Total RM Projects: {len(rm_projects)}")
        #endregion

        #region Process Updates -----------------------------------------------------
    def rm_field_updates(self, project:Project):
        """Checks and updates Standard and Custom fields for a project. If there are no differences it will not post the update to RM.
        Calls _get_rm_fields() to get custom and standard field id's and values
        Checks for differences in the values
        Sends updates if necessary """
        #validity checking
        if project.rm_project_id == None:
            self.log.info(f"{project.name} does not have an RM sheet...")
            return
        fields = self._get_rm_fields(project.rm_project_id)
        # Get all the fieds that need to be updated
        update_custom = {} #creates dict of field_id:value from data in fields for custom field update
        for field in fields:
            field_name = field["custom_field_name"]
            value = field["value"]
            if field_name == "DCT Status":
                if value != project.dct_status:
                    update_custom[field.get("id")] == project.dct_status
            elif field_name == "Project Enumerator":
                if value != project.enum:
                    update_custom[field.get("id")] = project.enum
            elif field_name == "Architect":
                if value != project.architect:
                    update_custom[field.get("id")] = project.architect
            elif field_name == "Estimate":
                if value != project.estimate:
                    update_custom[field.get("id")] = project.estimate
            elif field_name == "Estimate Presented?":
                if value != project.estimate_presented:
                    update_custom[field.get("id")] = project.estimate_presented
        #send the new updates to get posted
        for id, value in update_custom.items():
            if value:
                self._post_custom_field(id, value, project)
                self.log.info(f"Updating custom field {id} for project {project.name}")
        #now, we check the standard fields. there's only really two to worry about I guess
        fields = self._get_rm_fields(project.rm_project_id, standard=True)
        if fields.get("ciient") != project.client or fields.get("project_code") != project.project_code:
            self.log.info(f"Updating standard fields for project {project}")
            self._post_standard_field(project)
    #endregion
        
        #region Post RM Data --------------------------------------------------------
    def _post_custom_field(self, field_id, value, project: Project):
        """Calls the post method on a singular custom field to update the value
        Params:
        field_id: field_id of the custom field to update
        value: Value to be set to the custom field
        project: Project object associated to the fields"""

        url = self.rm_base_url + f"/api/v1/projects/{project.rm_project_id}/custom_field_values/{field_id}"
        response = requests.put(url, headers=self.rm_headers, data=json.dumps({'value':value}))
        
        #TODO: fix this 
        if response.status_code == 200:
            self.log.info(f"Updated Custom field to value {value} for project {project.name}")
            return True
        else:
            self.log.error(f"Error updating custom field: {field_id} : {value} for project {project.name} \n {response.status_code} {response.content}")
            return False
        
    def _post_standard_field(self, project:Project):
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
    #endregion
        
    #endregion

def main():
    rmm = AutoRM()
    # #rmm.fetch_new_dct_projects()
    # p= Project(name='_TEST IT 2.7*', enum='01151', dct_status='status', estimate='estimate', estimate_presented='ep', dct_sheet_id=4834941121548164, rm_project_bool=True, dct_grid_bool='', dct_grid_url='https://app.smartsheet.com/sheets/jphh9fwHW267hcvRq5m25PgwVpGVc34FXcvHFFv1', dct_enum_field_id=6231669148176260)
    # # p = Project(name= "_Test Formula2", enum="01151", dct_status='status', estimate='estimate', estimate_presented='ep', dct_sheet_id=2687330368311172)
    # # #rmm.create_DCT_grid(p)
    # # # # print(p)
    # # # p = rmm._add_dct_grid_enum(p)
    # # print(p)
    # #rmm._fetch_template()
    # rmm._add_dct_grid_enum(project=p)

    
    # #compare existing pl to dct planning
    # rmm.retroactive_DCT_grid()
    #endregion ------------------------------------------

    # # Selenium
    # rmm.initialize_selenium()

    # # RM handling
    #rmm.fetch_rm_projects()
    # print(rmm.get_rm_custom_fields(9038651))

    # p = Project(name='_TEST Auto_RM', enum='01244', dct_status='Closed', estimate='$7,050,000', estimate_presented=None, row_id=8478043445661572, rm_project_bool=False, dct_grid_bool=True, rm_project_id=None, dct_sheet_id=7554767950663556, dct_grid_url='https://app.smartsheet.com/sheets/w7gPJ6vpWxRhXh4JGC75m7f4V6PrPCwwr3fJrpv1', dct_enum_field_id=None, dct_enum_field_set=True)
    # rmm.todo_list = [p]
    # # rmm.create_rm_projects()

    # #update intake sheet
    # rmm.update_intake_rows()

    #standard fields
    fields = rmm._get_rm_fields(10441467, standard=True)
    print(fields)

    #Main flow ------------------------------------------
    # rmm.fetch_new_dct_projects() # fetch new projects from DCT RM Intake sheet
    # rmm.todo_handler() # handle todo list


main()






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

