import sys
import os
import json
import uuid
import urllib.request
import urllib.parse
import subprocess
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, 
                             QTabWidget, QFrame, QSlider, QMessageBox)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QFont

# Helper to locate resources in PyInstaller bundle
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_app_dir():
    app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'InvisibleAI')
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

def get_device_id():
    return uuid.UUID(int=uuid.getnode()).hex[-12:].upper()

def get_device_name():
    import socket
    return socket.gethostname()

class FirebaseWorker(QThread):
    status_signal = pyqtSignal(str, bool) # status_msg, is_approved
    
    def __init__(self, project_id, device_id):
        super().__init__()
        self.project_id = project_id
        self.device_id = device_id
        self.running = True
        
    def stop(self):
        self.running = False
        
    def run(self):
        # Poll Firestore document for status approval
        url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents/users/{self.device_id}"
        
        while self.running:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    fields = data.get("fields", {})
                    status = fields.get("status", {}).get("stringValue", "pending")
                    tier = fields.get("tier", {}).get("stringValue", "Free")
                    
                    if status == "approved":
                        self.status_signal.emit(tier, True)
                        break
                    elif status == "denied":
                        self.status_signal.emit("denied", False)
                        break
            except Exception:
                pass
            self.msleep(3000) # Poll every 3 seconds

class ManagerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.device_id = get_device_id()
        self.device_name = get_device_name()
        
        # Load environment defaults
        self.firebase_project = os.environ.get("FIREBASE_PROJECT_ID", "invisibleai-pay")
        self.discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
        self.upi_id = os.environ.get("UPI_ID", "9390776117@axl")
        self.upi_name = os.environ.get("UPI_NAME", "PMR")
        
        self.settings_path = os.path.join(get_app_dir(), "settings.json")
        self.settings = self.load_settings()
        
        # Enforce tier default
        self.user_tier = self.settings.get("tier", "Free")
        self.verification_worker = None
        
        self.init_ui()
        self.check_active_verification()
        
        # Anti-Tampering Check on Startup
        self.security_timer = QTimer(self)
        self.security_timer.timeout.connect(self.check_security_integrity)
        self.security_timer.start(5000) # Check every 5 seconds
        self.check_security_integrity()
        
    def load_settings(self):
        try:
            with open(self.settings_path, "r") as f:
                return json.load(f)
        except Exception:
            return {}
            
    def save_settings(self):
        try:
            with open(self.settings_path, "w") as f:
                json.dump(self.settings, f)
        except Exception as e:
            print("Failed to save settings:", e)
            
    def init_ui(self):
        self.setWindowTitle("Invisible AI - Manager Panel")
        self.setFixedSize(550, 450)
        self.setStyleSheet("""
            QWidget {
                background-color: #111116;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QTabWidget::panel {
                border: 1px solid #2d2d39;
                background: #15151e;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #1a1a26;
                border: 1px solid #2d2d39;
                padding: 8px 20px;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #8b5cf6;
                border-color: #8b5cf6;
                color: white;
            }
            QLineEdit {
                background-color: #1e1e2d;
                border: 1px solid #3f3f52;
                border-radius: 4px;
                padding: 6px;
                color: white;
            }
            QPushButton {
                background-color: #8b5cf6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7c3aed;
            }
            QPushButton:disabled {
                background-color: #4b5563;
                color: #9ca3af;
            }
            QLabel {
                background: transparent;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        
        # Header banner
        header = QLabel("🔮 INVISIBLE AI CONTROL HUB")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #a78bfa; margin-bottom: 10px;")
        main_layout.addWidget(header)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Dashboard / Launch
        self.init_dashboard_tab()
        
        # Tab 2: Provider & API Configuration
        self.init_config_tab()
        
        # Tab 3: UPI Paywall / Upgrades
        self.init_paywall_tab()
        
    def init_dashboard_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        info_frame = QFrame()
        info_frame.setStyleSheet("background: #1e1e2d; border-radius: 6px; border: 1px solid #2d2d39; padding: 15px;")
        info_layout = QVBoxLayout(info_frame)
        
        self.tier_lbl = QLabel(f"Current Status: <b>{self.user_tier.upper()} TIER</b>")
        self.tier_lbl.setStyleSheet("font-size: 16px; color: #34d399;")
        info_layout.addWidget(self.tier_lbl)
        
        dev_lbl = QLabel(f"Device ID: <code style='color:#a78bfa;'>{self.device_id}</code>")
        info_layout.addWidget(dev_lbl)
        
        layout.addWidget(info_frame)
        layout.addStretch()
        
        self.launch_btn = QPushButton("🚀 LAUNCH STEALTH OVERLAY")
        self.launch_btn.setStyleSheet("font-size: 15px; padding: 12px; background-color: #10b981;")
        self.launch_btn.clicked.connect(self.launch_overlay)
        layout.addWidget(self.launch_btn)
        
        self.tabs.addTab(tab, "Dashboard")
        
    def init_config_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Standard Keys
        layout.addWidget(QLabel("<b>Gemini API Key:</b>"))
        self.key_gemini = QLineEdit()
        self.key_gemini.setEchoMode(QLineEdit.Password)
        self.key_gemini.setText(self.settings.get("api_keys", {}).get("gemini", ""))
        layout.addWidget(self.key_gemini)
        
        layout.addWidget(QLabel("<b>Groq API Key:</b>"))
        self.key_groq = QLineEdit()
        self.key_groq.setEchoMode(QLineEdit.Password)
        self.key_groq.setText(self.settings.get("api_keys", {}).get("groq", ""))
        layout.addWidget(self.key_groq)
        
        layout.addWidget(QLabel("<b>OpenRouter API Key:</b>"))
        self.key_or = QLineEdit()
        self.key_or.setEchoMode(QLineEdit.Password)
        self.key_or.setText(self.settings.get("api_keys", {}).get("openrouter", ""))
        layout.addWidget(self.key_or)
        
        # Custom / Paid API Endpoint
        layout.addWidget(QLabel("<b>Custom AI API Base URL (Pro/Ultra):</b>"))
        self.key_custom_url = QLineEdit()
        self.key_custom_url.setPlaceholderText("https://integrate.api.nvidia.com/v1")
        self.key_custom_url.setText(self.settings.get("custom_api_base", ""))
        layout.addWidget(self.key_custom_url)
        
        layout.addWidget(QLabel("<b>Custom API Key:</b>"))
        self.key_custom_key = QLineEdit()
        self.key_custom_key.setEchoMode(QLineEdit.Password)
        self.key_custom_key.setText(self.settings.get("custom_api_key", ""))
        layout.addWidget(self.key_custom_key)
        
        layout.addWidget(QLabel("<b>Custom Model Name:</b>"))
        self.key_custom_model = QLineEdit()
        self.key_custom_model.setPlaceholderText("meta/llama-3.3-70b-instruct")
        self.key_custom_model.setText(self.settings.get("custom_api_model", ""))
        layout.addWidget(self.key_custom_model)
        
        layout.addStretch()
        
        save_btn = QPushButton("Save Configurations")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        
        self.tabs.addTab(tab, "API Settings")
        
    def init_paywall_tab(self):
        tab = QWidget()
        self.paywall_layout = QVBoxLayout(tab)
        self.paywall_layout.setContentsMargins(20, 20, 20, 20)
        
        self.render_paywall()
        self.tabs.addTab(tab, "Billing & Upgrade")
        
    def render_paywall(self):
        # Clear layout first
        for i in reversed(range(self.paywall_layout.count())): 
            self.paywall_layout.itemAt(i).widget().setParent(None)
            
        if self.user_tier in ["Pro", "Ultra"]:
            self.paywall_layout.addWidget(QLabel("<h2>💎 Pro/Ultra Access Activated!</h2>"))
            self.paywall_layout.addWidget(QLabel("Your device has been approved for premium features."))
            
            reset_btn = QPushButton("Deactivate / Switch Key")
            reset_btn.setStyleSheet("background-color: #ef4444;")
            reset_btn.clicked.connect(self.deactivate_tier)
            self.paywall_layout.addWidget(reset_btn)
        else:
            self.paywall_layout.addWidget(QLabel("<b>Upgrade to Premium (₹20 Plan):</b>"))
            
            # Generated UPI link
            upi_payload = f"upi://pay?pa={self.upi_id}&pn={urllib.parse.quote(self.upi_name)}&am=20.00&cu=INR&tn=InvisibleAI_Upgrade"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=130x130&data={urllib.parse.quote(upi_payload)}"
            
            qr_row = QHBoxLayout()
            qr_img = QLabel()
            
            # Fetch QR code asynchronously or simple inline fetch
            try:
                req = urllib.request.Request(qr_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    pixmap = QPixmap()
                    pixmap.loadFromData(resp.read())
                    qr_img.setPixmap(pixmap)
            except Exception:
                qr_img.setText("[Scan UPI: 9390776117@axl]")
                
            qr_row.addWidget(qr_img)
            
            desc = QLabel("<b>Scan QR to Pay with any UPI App (GPay/PhonePe/Paytm)</b><br>"
                          "1. Pay <b>₹20</b> for Pro Access.<br>"
                          "2. Locate the <b>12-digit UTR</b> Transaction ID.<br>"
                          "3. Paste the UTR below to request approval.")
            desc.setWordWrap(True)
            qr_row.addWidget(desc)
            self.paywall_layout.addLayout(qr_row)
            
            self.utr_input = QLineEdit()
            self.utr_input.setPlaceholderText("Enter 12-digit UPI UTR Transaction ID")
            self.paywall_layout.addWidget(self.utr_input)
            
            self.submit_btn = QPushButton("Submit Proof of Payment")
            self.submit_btn.clicked.connect(self.submit_proof)
            self.paywall_layout.addWidget(self.submit_btn)
            
            self.status_msg = QLabel("Status: Awaiting Payment Proof Submission...")
            self.status_msg.setStyleSheet("color: #9ca3af; font-style: italic;")
            self.paywall_layout.addWidget(self.status_msg)
            
    def save_config(self):
        if not "api_keys" in self.settings:
            self.settings["api_keys"] = {}
        self.settings["api_keys"]["gemini"] = self.key_gemini.text().strip()
        self.settings["api_keys"]["groq"] = self.key_groq.text().strip()
        self.settings["api_keys"]["openrouter"] = self.key_or.text().strip()
        
        self.settings["custom_api_base"] = self.key_custom_url.text().strip()
        self.settings["custom_api_key"] = self.key_custom_key.text().strip()
        self.settings["custom_api_model"] = self.key_custom_model.text().strip()
        
        self.save_settings()
        QMessageBox.information(self, "Success", "Configuration settings saved successfully!")
        
    def submit_proof(self):
        utr = self.utr_input.text().strip()
        if len(utr) != 12 or not utr.isdigit():
            QMessageBox.warning(self, "Invalid UTR", "UTR must be a 12-digit numeric code.")
            return
            
        self.status_msg.setText("Submitting details to database...")
        self.submit_btn.setEnabled(False)
        
        # 1. Update Firestore Document via REST API
        # Using simple REST endpoint
        url = f"https://firestore.googleapis.com/v1/projects/{self.firebase_project}/databases/(default)/documents/users/{self.device_id}?updateMask.fieldPaths=utr&updateMask.fieldPaths=status&updateMask.fieldPaths=tier&updateMask.fieldPaths=deviceName"
        
        payload = {
            "fields": {
                "utr": {"stringValue": utr},
                "status": {"stringValue": "pending"},
                "tier": {"stringValue": "Pro"},
                "deviceName": {"stringValue": self.device_name}
            }
        }
        
        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
                method='PATCH'
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Failed to submit verification to Firestore: {e}")
            self.submit_btn.setEnabled(True)
            self.status_msg.setText("Status: Submission Failed.")
            return
            
        # 2. Fire Discord Notification Hook
        if self.discord_webhook:
            discord_payload = {
                "embeds": [{
                    "title": "🚨 New Desktop Payment Request",
                    "color": 8947967, # Purpleish
                    "fields": [
                        {"name": "UTR Code", "value": f"`{utr}`", "inline": True},
                        {"name": "Device ID", "value": f"`{self.device_id}`", "inline": True},
                        {"name": "System Name", "value": f"*{self.device_name}*", "inline": True},
                        {"name": "Requested Plan", "value": "Desktop Pro (₹20)", "inline": True}
                    ],
                    "description": "Please verify deposit in your bank app and approve status in Firestore console."
                }]
            }
            try:
                d_req = urllib.request.Request(
                    self.discord_webhook,
                    data=json.dumps(discord_payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(d_req, timeout=5) as resp:
                    pass
            except Exception:
                pass # Webhook failure shouldn't block user
                
        self.status_msg.setText("Status: Awaiting developer approval... (Real-time monitoring)")
        self.start_verification_listener()
        
    def start_verification_listener(self):
        if self.verification_worker:
            self.verification_worker.stop()
        self.verification_worker = FirebaseWorker(self.firebase_project, self.device_id)
        self.verification_worker.status_signal.connect(self.on_verification_completed)
        self.verification_worker.start()
        
    def check_active_verification(self):
        # On launch, check if Firestore document is already approved
        # If yes, update local tier directly
        url = f"https://firestore.googleapis.com/v1/projects/{self.firebase_project}/databases/(default)/documents/users/{self.device_id}"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                fields = data.get("fields", {})
                status = fields.get("status", {}).get("stringValue", "")
                tier = fields.get("tier", {}).get("stringValue", "Free")
                utr = fields.get("utr", {}).get("stringValue", "")
                
                if status == "approved":
                    self.user_tier = tier
                    self.settings["tier"] = tier
                    self.save_settings()
                    self.tier_lbl.setText(f"Current Status: <b>{self.user_tier.upper()} TIER</b>")
                elif status == "pending" and utr:
                    self.status_msg.setText("Status: Awaiting developer approval... (Real-time monitoring)")
                    if self.utr_input:
                        self.utr_input.setText(utr)
                    self.submit_btn.setEnabled(False)
                    self.start_verification_listener()
        except Exception:
            pass
            
    def on_verification_completed(self, tier, is_approved):
        if is_approved:
            self.user_tier = tier
            self.settings["tier"] = tier
            self.save_settings()
            self.tier_lbl.setText(f"Current Status: <b>{self.user_tier.upper()} TIER</b>")
            QMessageBox.information(self, "Pro Unlocked! 💎", "Your device payment has been approved! All Pro/Ultra features are now available.")
            self.render_paywall()
        else:
            self.status_msg.setText("Status: Transaction Denied or Refused.")
            self.submit_btn.setEnabled(True)
            
    def deactivate_tier(self):
        reply = QMessageBox.question(self, 'Reset License', 'Deactivate pro mode on this device?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.user_tier = "Free"
            self.settings["tier"] = "Free"
            self.save_settings()
            self.tier_lbl.setText(f"Current Status: <b>{self.user_tier.upper()} TIER</b>")
            self.render_paywall()
            
    def launch_overlay(self):
        overlay_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SystemAudioEngine.exe")
        if not os.path.exists(overlay_path):
            overlay_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay.py")
            cmd = ["python", overlay_path]
        else:
            cmd = [overlay_path]
            
        try:
            subprocess.Popen(cmd, creationflags=0x08000000) # CREATE_NO_WINDOW
            QApplication.quit()
        except Exception as e:
            QMessageBox.critical(self, "Launch Error", f"Failed to launch overlay engine: {e}")
            
    def check_security_integrity(self):
        import ctypes
        if getattr(sys, 'frozen', False):
            # Detect active debugger
            if ctypes.windll.kernel32.IsDebuggerPresent():
                self.self_destruct("Debugger detected.")

    def self_destruct(self, reason):
        import shutil
        import subprocess
        
        # 1. Wipe AppData
        app_dir = get_app_dir()
        try:
            if os.path.exists(app_dir):
                shutil.rmtree(app_dir)
        except Exception:
            pass
            
        # 2. Self-delete the compiled executable
        try:
            exe_path = sys.executable
            cmd = f"timeout /T 1 & del /F /Q \"{exe_path}\""
            subprocess.Popen(cmd, shell=True, creationflags=0x08000000) # CREATE_NO_WINDOW
        except Exception:
            pass
            
        # 3. Exit process instantly
        os._exit(1)

    def closeEvent(self, event):
        if self.verification_worker:
            self.verification_worker.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ManagerWindow()
    window.show()
    sys.exit(app.exec_())
