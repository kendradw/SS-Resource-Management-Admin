from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM
import json

def main():
    #run project updates
    arm = AutoRM()
    arm.update_projects()
    with open("configs/config.json", "r") as f:
        config = json.load(f)
        #run time/assignments updates
    sra = SmartsheetRmAdmin(config)
    sra.run_all()

main()