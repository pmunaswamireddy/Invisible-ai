import codecs
path = 'd:/invisibleai/overlay.py'
with codecs.open(path, 'r', 'utf-8') as f:
    text = f.read()

index = text.find('if __name__ == "__main__":')
if index != -1:
    text = text[:index]
    
    correct_end = '''if __name__ == "__main__":
    import os
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--disable-gpu "
        "--disable-software-rasterizer "
        "--disable-gpu-compositing "
        "--disable-smooth-scrolling "
        "--js-flags='--expose-gc' "
        "--num-raster-threads=1 "
        "--disable-extensions "
        "--disable-background-networking "
        "--disable-sync"
    )
    # Setup programmatic logging to handle locked files gracefully without startup crashes
    import sys
    for i in range(10):
        try:
            log_name = f"error_{i}.log" if i > 0 else "error.log"
            log_file_handle = open(log_name, "a", encoding="utf-8", buffering=1)
            sys.stdout = log_file_handle
            sys.stderr = log_file_handle
            break
        except Exception:
            continue
    try:
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # OpenGL removed to fix 60-second initialization conflict with Chromium GPU flags
        app = QApplication(sys.argv)
        overlay = TransparentOverlay()
        overlay.show()
        app_filter = AppEventFilter(overlay)
        app.installEventFilter(app_filter)
        sys.exit(app.exec_())
    except Exception as e:
        import traceback
        with open("crash_log.txt", "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
'''
    with codecs.open(path, 'w', 'utf-8') as f:
        f.write(text + correct_end)
    print("Fixed successfully.")
else:
    print("Could not find main block.")
