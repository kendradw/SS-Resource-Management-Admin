from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import json
from configs.setup_logger import setup_logger


def main():
    log = setup_logger(__name__, file_path="configs/log.log")
    log.info("Starting main...")
    arm = AutoRM(log_path="configs/log.log")
    arm.sync_projects()
    with open("configs/config.json", "r") as f:
        config = json.load(f)
    srm = SmartsheetRmAdmin(config, log_path="configs/log.log")
    srm.run_all()
    srm.run_assignment_updates()
    log.info("~Fin~")
main()