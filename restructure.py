import os
import shutil

print("Restructuring repo for multi-mode deployment...")

files_to_move = ["app.py", "logic.py", "models.py", "tasks.py"]
os.makedirs("server", exist_ok=True)

with open("server/__init__.py", "w") as f:
    f.write("")

for filename in files_to_move:
    if os.path.exists(filename):
        shutil.move(filename, os.path.join("server", filename))

def replace_in_file(path, old, new):
    if not os.path.exists(path): return
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old in content:
        content = content.replace(old, new)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

# Update imports inside server component to be relative structure
replace_in_file("server/logic.py", "from models import", "from server.models import")
replace_in_file("server/logic.py", "from tasks import", "from server.tasks import")

replace_in_file("server/app.py", "from models import", "from server.models import")
replace_in_file("server/app.py", "from logic import", "from server.logic import")
replace_in_file("server/app.py", "from tasks import", "from server.tasks import")

# Add start() method inside app.py for openenv scripts entrypoint
start_method = """

def start():
    import uvicorn
    import sys
    port = 7860
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    uvicorn.run("server.app:app", host="0.0.0.0", port=port)
"""
with open("server/app.py", "r", encoding="utf-8") as f:
    content = f.read()
if "def start():" not in content:
    with open("server/app.py", "a", encoding="utf-8") as f:
        f.write(start_method)

# Update external root files to point to server module
replace_in_file("test_logic.py", "from logic import", "from server.logic import")
replace_in_file("test_logic.py", "from models import", "from server.models import")
replace_in_file("quick_test.py", "from logic import", "from server.logic import")
replace_in_file("quick_test.py", "from models import", "from server.models import")
replace_in_file("Dockerfile", '"app:app"', '"server.app:app"')

print("Done reorganizing files!")
