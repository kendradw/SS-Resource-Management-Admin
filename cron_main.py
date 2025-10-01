from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import json
from configs.setup_logger import setup_logger
import logging

def main():
    # Setup Logger
    log = setup_logger(__name__, file_path="configs/log.log", level=logging.DEBUG)
    log.info("Starting main...")
    # Sync Projects (DCT + RM)
    arm = AutoRM(log)
    arm.sync_projects()

    # ---- print data ------
    with open("rm_map.json", "w") as of:
        json.dump(arm.rm_projects_map, of, indent=2)
    with open("dct_sheets.json", "w") as of:
        json.dump(arm.existing_dct_sheets, of, indent=2)
    # # ----------------------

    # Sync Data (Hours + Assignments)
    with open("configs/config.json", "r") as f:
        config = json.load(f)
    srm = SmartsheetRmAdmin(config, log)
    srm.run_all()

    log.info("----COMPLETE----")
# main()

def debug():
    log = setup_logger(__name__, file_path="configs/log.log")
    # log.info("Starting debug...")
    # arm = AutoRM(log)
    # with open("rm_map.json", "w") as of:
    #     json.dump(arm.rm_projects_map, of, indent=2)

    with open("configs/config.json", "r") as f:
        config = json.load(f)
    srm = SmartsheetRmAdmin(config, log)
    srm.grab_rm_data()
    # srm.run_hours_update()
    srm.run_assignment_updates()
    print("COMPLETE----")

debug()