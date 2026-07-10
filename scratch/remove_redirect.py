import codecs

path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

bad_block = """    # Setup programmatic logging to handle locked files gracefully without startup crashes
    import sys
    for i in range(10):
        try:
            log_name = f"error_{i}.log" if i > 0 else "error.log"
            log_file_handle = open(log_name, "a", encoding="utf-8", buffering=1)
            sys.stdout = log_file_handle
            sys.stderr = log_file_handle
            break
        except PermissionError:
            continue"""

# Actually, the original code I saw was:
#     import sys
#     for i in range(10):
#         try:
#             log_name = f"error_{i}.log" if i > 0 else "error.log"
#             log_file_handle = open(log_name, "a", encoding="utf-8", buffering=1)
#             sys.stdout = log_file_handle
#             sys.stderr = log_file_handle

import re
text = re.sub(r'    # Setup programmatic logging.*?sys\.stderr = log_file_handle.*?continue', '', text, flags=re.DOTALL)

with codecs.open(path, 'w', 'utf-8') as f:
    f.write(text)
print("Redirect removed.")
'''

'''