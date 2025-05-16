from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import json

def main():
    arm = AutoRM()
    arm.sync_projects()
    with open("configs/config.json", "r") as f:
        config = json.load(f)
    srm = SmartsheetRmAdmin(config)
    srm.run_all()
    srm.run_assignment_updates()
main()