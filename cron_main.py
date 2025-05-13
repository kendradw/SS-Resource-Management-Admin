from SS_RM_admin import SmartsheetRmAdmin
from auto_rm import AutoRM

def main():
    arm = AutoRM()
    arm.sync_projects()
    # srm = SmartsheetRmAdmin()
    # srm.run_all()

main()