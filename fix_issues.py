import os
import glob

actions_file = "starter/actions/actions.py"
with open(actions_file, "r") as f:
    content = f.read()

content = content.replace(
    '"update_success",\n        }',
    '"update_success", "flow_hashes",\n        }'
)
with open(actions_file, "w") as f:
    f.write(content)

files_to_fix = glob.glob("starter/data/flows/*.yml") + glob.glob("starter/tests/e2e/*.yml")

for file_path in files_to_fix:
    with open(file_path, "r") as f:
        content = f.read()
    
    content = content.replace("                next: wrap_up\n", "")
    content = content.replace("      - id: wrap_up\n        action: utter_can_do_something_else\n", "")
    content = content.replace("      - action: utter_can_do_something_else\n", "")
    content = content.replace("  - action: utter_can_do_something_else\n", "")
    content = content.replace("  - bot: utter_can_do_something_else\n", "")
    content = content.replace("      - bot: utter_can_do_something_else\n", "")
    
    with open(file_path, "w") as f:
        f.write(content)

print("Fixes applied.")
