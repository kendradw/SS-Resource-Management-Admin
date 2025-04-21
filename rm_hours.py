#region imports
import smartsheet
from smartsheet.exceptions import ApiError
from datetime import datetime
from smartsheet_grid import grid
import requests
import json
import time
import os
from dotenv import load_dotenv
import pandas as pd
from configs.setup_logger import setup_logger
#endregion


class RMHoursUpdate():
    #region init --------------------------------------------------------------------
    def __init__(self, config):
        self.config = config
        self.apply_config(config) # '''turns all config items into self.key = value'''
        #smartsheet setup
        grid.token=self.smartsheet_token 
        self.smart = smartsheet.Smartsheet(access_token=self.smartsheet_token)
        self.smart.errors_as_exceptions(True)
        self.start_time = time.time()
        self.log=setup_logger(__name__)
        self.rm_header = {
            'Content-Type': 'application/json',
            'auth': self.rm_token
        }
        self.error_w_hh2sheet = []
        self.base_url='https://api.rm.smartsheet.com'

    def apply_config(self, config):
        '''turns all config items into self.key = value'''
        for key, value in config.items():
            setattr(self, key, value)
    #endregion

    #region Main Hours Function ----------------------------------------------------
    def run_hours_update(self):
        '''runs main script as intended'''
        self.log.info("""Time & Expense Updates:
                     """)
        self.grab_rm_userids()
        self.fetch_and_prepare_hh2_data()
        self.grab_rm_timedata()
        if self.error_w_hh2sheet == []:
            self.process_timedata_discrepencies()
            self.post_rm_time_changes()
            self.post_ss_data(self.flat_hh2_records)
        else:
            self.post_ss_data([{"key":"EmployeeNumberDateJobApprovalType", 'messages':self.error_w_hh2sheet}])
        grid(self.hh2_data_sheetid).handle_update_stamps()
    #endregion

    #region Get Data ---------------------------------------------------------------
    def grab_rm_userids(self):
        '''grabs each user's id, this will help with allocating hours to users correctly'''
        response_dict = self.paginated_rm_getrequest(endpoint='/api/v1/users')

        self.rm_user_list=[]
        self.sageid_to_email={}
        self.userid_to_email={}
        self.email_to_userid={}
        self.email_to_sageid = {}
        for user in response_dict:
            if user['email'] is not None:
                self.rm_user_list.append({'email': user['email'].lower(), 'rm_usr_id':  user['id'], 'name': user['display_name'], 'sage id': user['employee_number']})
                self.sageid_to_email[user['employee_number']] = user['email'].lower()
                self.email_to_sageid[user['email'].lower()] = user['employee_number']
                self.userid_to_email[user['id']] = user['email'].lower()
                self.email_to_userid[user['email'].lower()] = user['id']

    def fetch_and_prepare_hh2_data(self):
        '''grabs the hh2 data from ss, then cleans the df and creates a list of dict records
        I have to replace Jobs with resulting Jobs because Katherine added jobs that are the results of certain data conditions, not from hh2 8.5.24'''
        sheet = grid(self.hh2_data_sheetid)
        sheet.fetch_content()
        df = sheet.df
        self.scriptkey_to_script_message = pd.Series(df['Script Message'].values,index=df['Script Key']).to_dict()

        columns_to_keep = [
            'EmployeeNumber', 'EmployeeName', 'Date', 'PayrollGroup', 'PayrollServiceId',
            'Job', 'JobName', 'CostCode', 'CostCodeName', 'CertifiedClass', 'CertifiedClassName',
            'PayType', 'PayTypeName', 'Units', 'Description', 'ApprovalType', 'id'
        ]
        df['Job'] = df['Resulting Job Number']
        df = df.filter(columns_to_keep)

        invalid_column_list = self.validate_and_contains_first_row(df)

        if invalid_column_list == []:
            df = self.clean_df_for_processing(df)
            self.flat_hh2_records = self.aggregate_hh2_data(df)
        else: 
            self.error_w_hh2sheet.append(f"First row validation failed (so script did not run properly). Please check {invalid_column_list} columns. ({self.generate_now_string()})")
            self.log.error(f'HH2 Sheet error: please check the following column(s) {invalid_column_list} at https://app.smartsheet.com/sheets/GffHvGGxVJwQ9P8w8gwgfqrmJjcq39JXvMQmH7q1?view=grid&filterId=3306346053062532')
            self.log.info('if this is a new column, add it to df.drop in fetch_and_prepare_hh2_data(self)')
            return None  # Return to avoid further processing

    def grab_rm_timedata(self):
        '''grabs existing data from rm, translates rm job id to job number, rm user id to user email, 
        and then builds out a reference dictionary of time entries (hrs) for verifying if update is needed, adding hours for same job/time as needed
        and building reference of entry ids w list of ids per entry'''
        self.current_rm_timedata = []
        self.rm_quickreference_hrs = {}
        self.rm_quickreference_id = {}
        for user in self.rm_user_list:
            self.current_rm_timedata.extend(self.paginated_rm_getrequest(f"/api/v1/users/{user['rm_usr_id']}/time_entries"))
        for timeentry in self.current_rm_timedata:
            try:
                timeentry['job_num'] = self.rm_id_to_jobnum[timeentry['assignable_id']]
            except KeyError:
                # not longterm solution!
                timeentry['job_num'] = "no_job_num"
            timeentry['usr_email'] = self.userid_to_email[timeentry['user_id']]
            key = f"{timeentry['usr_email'].lower()}{timeentry['date']}{timeentry['job_num']}"
            if key not in self.rm_quickreference_hrs:
                self.rm_quickreference_hrs[key] = timeentry['hours']
                self.rm_quickreference_id[key] = [timeentry['id']]  # Initialize with a list containing the id
            else:
                old_number = self.rm_quickreference_hrs[key]
                self.rm_quickreference_hrs[key] = old_number + timeentry['hours']
                self.rm_quickreference_id[key].append(timeentry['id'])  # Directly append the new id to the list
    
    def paginated_rm_getrequest(self, endpoint, params=None):
        """
        Fetches data from an API endpoint. Handles both single item and paginated responses.

        :param endpoint: The specific endpoint to fetch data from.
        :param headers: Dictionary containing request headers.
        :param params: Dictionary containing any query parameters for the GET request.
        :return: A single item or a list of items aggregated from all pages.
        """
        url = f"{self.base_url}{endpoint}"
        items = []
        while url:
            response = requests.get(url, headers=self.rm_header, params=params)
            if response.status_code == 200:
                response_json = response.json()
                # Check if response is paginated
                if 'data' in response_json:
                    items.extend(response_json.get('data', []))
                    next_page = response_json.get('paging', {}).get('next')
                    url = f"{self.base_url}{next_page}" if next_page and not next_page.startswith('http') else next_page
                else:
                    return response_json  # Return a single item
            else:
                self.log.error(f"Failed to fetch data: {response.status_code} - {response.reason}")
                break  # Exit loop on failure
        return items if items else []    
    #endregion

    #region Process Data -----------------------------------------------------------
    def process_timedata_discrepencies(self):
        '''compare hh2 data (on ss) w/ rm data. The end result is a list of time entries and their needed actions'''
        up_to_date, to_update, to_add, self.to_add_projntime=0,0,0,0
        self.undeployed_job_nums = []
        for timeentry in self.flat_hh2_records:
            key = f"{timeentry['user_email'].lower()}{timeentry['date']}{timeentry['job_num']}"
            try:
                # print(key, self.rm_quickreference[key], timeentry['hours'])
                if self.rm_quickreference_hrs[key] != timeentry['hours']:
                    timeentry['action'] = 'update'
                    timeentry['rm_entry_id'] = self.rm_quickreference_id[key]
                    to_update += 1
                else:
                    timeentry['action'] = 'current'
                    up_to_date += 1
            except KeyError:
                timeentry['action'] = 'add'
                if timeentry['rm_proj_id'] == '':
                    timeentry['messages'].extend([f"FAILED TO PROCESS: Job Number {timeentry['job_num']} is not in the system, so cannot post time to a time entry ({self.generate_now_string()})"])
                    self.to_add_projntime +=1
                    if timeentry['job_num'] not in self.undeployed_job_nums:
                        self.undeployed_job_nums.append(timeentry['job_num'])
                else:
                    to_add += 1
                continue
        self.log.info(f"""Of the SS/HH2 Time Entries between {self.min_date} and {self.max_date}: 
    {up_to_date} entries current,
    {to_update} entries needing update
    {to_add} entries need to be added
    {self.to_add_projntime} entries that first need project added, then time added""")
        
    def clean_df_for_processing(self, df):
        '''cleans incoming hh2 data from smartsheet'''
        df.drop(index=df.index[0], inplace=True)
        df.reset_index(drop=True, inplace=True)
        df['Date'] = pd.to_datetime(df['Date'])
        df['Description'] = df['Description'].astype(str)
        df['Units'] = pd.to_numeric(df['Units'], errors='coerce')
        return df
    
    def validate_and_contains_first_row(self, dataframe):
        #Not sure, called by "fetch_and_prepare_hh2_data()"
        '''Checks if all columns have the words from the first row (minus the last, which is row ids)
        this is important because that match represents that the data DCT pastes in matches what this script is expecting to see'''
        correct_columns = []
        incorrect_columns = []
        for i in range(len(dataframe.columns)-1):
            # Check if the value of each cell in the first row is contained within the corresponding column name
            if str(dataframe.iloc[0, i]) in dataframe.columns[i]:
                correct_columns.append(str(dataframe.iloc[0, i]))
            # check each column to make sure it is in the correct columns list, otherwise it is missing and therefore wrong
        for column in dataframe.columns.tolist():
            if column !='id' and column not in correct_columns:
                incorrect_columns.append(column)
        return incorrect_columns  # If all cells are contained, return True
    #endregion

    #region Post Data --------------------------------------------------------------------
    def post_rm_time_changes(self):
        'processes and posts time changes. It tracks job numbers not in RM, error messages, and generally posts action results and a summary of everything it did'
        self.api_error_messages = []
        self.api_error_messages_instance, successful_update, successful_add = 0, 0, 0
        success = False
        # actions
        for i, entry in enumerate(self.flat_hh2_records):
            action = entry.get('action')
            if action== "add":
                success= self.add_new_timedata(entry)
            elif action== "update":
                success= self.delete_old_timedata(entry) and self.add_new_timedata(entry)
            elif action == "current":
                entry['messages'].append(f"Job was current with {entry['hours']}, no action excuted ({self.generate_now_string()})")

        # loging actions
            if success:
                entry['messages'].append(f"Successful post of {entry['hours']} ({self.generate_now_string()})")
                if action == 'add':
                    successful_add += 1
                elif action == 'update':
                    successful_update += 1

        # summary of action
        if self.to_add_projntime > 0:
            self.log.error(f"There was {self.to_add_projntime} instances where a time entry post was attempted on a job we didn't have in the Resouce manager, these were for job(s): {self.undeployed_job_nums}")
        if self.api_error_messages != []:
            self.log.error(f"There was {self.api_error_messages_instance} instances where a time entry post failed due to api error, those errors were: {self.api_error_messages}")
        if successful_update > 0 or successful_add > 0:
            self.log.info(f"~~Time Entry adjustedments are complete, there was {successful_add} successful time entries added and {successful_update} successful time entries updated~~")

    def post_ss_data(self, data):
        '''posts back to ss a message if the message is different than what is currently there '''
        self.posting_data = []
        for row in data:
            existing_message = str(self.scriptkey_to_script_message[row['key']])
            new_message = " ".join(row['messages'])
            # if the new message and old are the same (barring time-stamp, but not date-stamp), do not update ss
            if existing_message[:len(existing_message)-6] != new_message[:len(new_message)-6]:
                self.posting_data.append({"Script Key":row['key'], 'Script Message':new_message})
        self.posting_data.insert(0, {"Script Key":"EmployeeNumberDateJobApprovalType", 'Script Message':""})
        sheet = grid(self.hh2_data_sheetid)
        sheet.update_rows(posting_data = self.posting_data, primary_key = "Script Key", update_type = "batch")


if __name__ == "__main__":
    # https://app.smartsheet.com/sheets/GffHvGGxVJwQ9P8w8gwgfqrmJjcq39JXvMQmH7q1?view=grid is hh2 data sheet
    # https://app.smartsheet.com/browse/workspaces/GXmwRM4wcCmjMVGVjhJ2cWCFR9QWMQCr5w8WGrx1 is proj workspace

    with open("configs/config.json", "r") as inf:
        config = json.load(inf)

    update_hours = RMHoursUpdate(config)
    update_hours.run_hours_update()
    update_hours.log.info("""~Fin""")

