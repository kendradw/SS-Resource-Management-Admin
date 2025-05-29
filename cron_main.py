from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import json
from configs.setup_logger import setup_logger

def main():
    # Setup Logger
    log = setup_logger(__name__, file_path="configs/log.log")
    log.info("Starting main...")
    # Sync Projects (DCT + RM)
    arm = AutoRM(log)
    arm.sync_projects()
    # Sync Data (Hours + Assignments)
    with open("configs/config.json", "r") as f:
        config = json.load(f)
    srm = SmartsheetRmAdmin(config, log)
    srm.run_all()
    srm.run_assignment_updates()

    log.info("----COMPLETE----")
main()