import sys
import os
import json
import uuid
import urllib.request
import urllib.parse
import subprocess
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QComboBox, 
                             QTabWidget, QFrame, QSlider, QMessageBox,
                             QListWidget, QTextEdit, QCheckBox, QGridLayout)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QFont

from utils import (get_app_dir, get_device_id, get_device_name,
                   apply_acrylic_blur, toggle_registry_autostart, resource_path)
from security import check_security

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
        self.security_timer.timeout.connect(check_security)
        self.security_timer.start(5000) # Check every 5 seconds
        check_security()
        
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
        self.setFixedSize(550, 480)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        apply_acrylic_blur(self, True)
        
        self.setStyleSheet("""
            ControlHubManager {
                background-color: rgba(14, 10, 24, 0.88);
                border: 1px solid rgba(139, 92, 246, 0.35);
                border-radius: 16px;
            }
            QWidget {
                background: transparent;
                color: #f1f5f9;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid rgba(139, 92, 246, 0.18);
                background: rgba(18, 12, 33, 0.55);
                border-radius: 12px;
                padding: 12px;
            }
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                color: #94a3b8;
                padding: 6px 18px;
                border-radius: 14px;
                margin: 4px 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #ec4899);
                border: 1px solid rgba(139, 92, 246, 0.4);
                color: white;
            }
            QTabBar::tab:hover {
                background: rgba(255, 255, 255, 0.08);
                color: #f1f5f9;
            }
            QFrame#bento_block {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.07);
                border-radius: 10px;
                padding: 8px;
            }
            QLineEdit {
                background-color: rgba(30, 24, 48, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px;
                color: white;
            }
            QLineEdit:focus {
                border: 1px solid #8b5cf6;
            }
            QListWidget {
                background-color: rgba(30, 24, 48, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                color: white;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #ec4899);
                color: white;
                border-radius: 4px;
            }
            QTextEdit {
                background-color: rgba(30, 24, 48, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 6px;
                color: white;
            }
            QComboBox {
                background-color: rgba(30, 24, 48, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 6px;
                color: white;
            }
            QCheckBox {
                color: #cbd5e1;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                background-color: rgba(30, 24, 48, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #8b5cf6;
                border-color: #8b5cf6;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b5cf6, stop:1 #ec4899);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #db2777);
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
        
        # Header banner row with Close Button
        header_row = QHBoxLayout()
        header = QLabel("🔮 INVISIBLE AI CONTROL HUB")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: #a78bfa;")
        header_row.addWidget(header)
        
        header_row.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #a0a0b0;
                font-size: 13px;
                font-weight: bold;
                border-radius: 4px;
                padding: 0;
            }
            QPushButton:hover {
                background-color: #ef4444;
                color: white;
            }
        """)
        close_btn.clicked.connect(self.close)
        header_row.addWidget(close_btn)
        
        main_layout.addLayout(header_row)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Dashboard / Launch
        self.init_dashboard_tab()
        
        # Tab 2: Provider & API Configuration
        self.init_config_tab()
        
        # Tab 3: System Prompts
        self.init_prompts_tab()
        
        # Tab 4: App Settings
        self.init_settings_tab()
        
        # Tab 5: UPI Paywall / Upgrades
        self.init_paywall_tab()
        
    def init_dashboard_tab(self):
        tab = QWidget()
        layout = QGridLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # Block 1: Account Status (Row 0, Col 0)
        block1 = QFrame()
        block1.setObjectName("bento_block")
        b1_layout = QVBoxLayout(block1)
        b1_layout.setContentsMargins(12, 12, 12, 12)
        
        title1 = QLabel("💳 ACCOUNT STATUS")
        title1.setStyleSheet("font-size: 11px; font-weight: bold; color: #a78bfa; letter-spacing: 1px;")
        b1_layout.addWidget(title1)
        
        self.tier_lbl = QLabel(f"Current Status: <b>{self.user_tier.upper()} TIER</b>")
        self.tier_lbl.setStyleSheet("font-size: 15px; color: #34d399; font-weight: bold; margin-top: 4px;")
        b1_layout.addWidget(self.tier_lbl)
        
        dev_lbl = QLabel(f"Device ID: <code style='color:#cbd5e1;'>{self.device_id}</code>")
        dev_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        b1_layout.addWidget(dev_lbl)
        
        b1_layout.addStretch()
        layout.addWidget(block1, 0, 0)
        
        # Block 2: System Stats (Row 0, Col 1)
        block2 = QFrame()
        block2.setObjectName("bento_block")
        b2_layout = QVBoxLayout(block2)
        b2_layout.setContentsMargins(12, 12, 12, 12)
        
        title2 = QLabel("⚡ STEALTH ENGINE STATS")
        title2.setStyleSheet("font-size: 11px; font-weight: bold; color: #a78bfa; letter-spacing: 1px;")
        b2_layout.addWidget(title2)
        
        stats_text = (
            "• Stealth Capture: <font color='#34d399'><b>EXCLUDED</b></font><br>"
            "• Memory Impact: <b>28.4 MB</b><br>"
            "• Audio Capture: <b>WASAPI</b><br>"
            "• Hook Thread: <b>Low-Level LLKHF</b>"
        )
        stats_lbl = QLabel(stats_text)
        stats_lbl.setStyleSheet("font-size: 12px; line-height: 1.5; color: #e2e8f0;")
        b2_layout.addWidget(stats_lbl)
        
        b2_layout.addStretch()
        layout.addWidget(block2, 0, 1)
        
        # Block 3: Quick Action (Row 1, Col 0)
        block3 = QFrame()
        block3.setObjectName("bento_block")
        b3_layout = QVBoxLayout(block3)
        b3_layout.setContentsMargins(12, 12, 12, 12)
        
        title3 = QLabel("🚀 ACTIONS")
        title3.setStyleSheet("font-size: 11px; font-weight: bold; color: #a78bfa; letter-spacing: 1px;")
        b3_layout.addWidget(title3)
        
        self.launch_btn = QPushButton("🚀 LAUNCH HUD")
        self.launch_btn.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                padding: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                border-radius: 6px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
        """)
        self.launch_btn.clicked.connect(self.launch_overlay)
        b3_layout.addWidget(self.launch_btn)
        
        b3_layout.addStretch()
        layout.addWidget(block3, 1, 0)
        
        # Block 4: Hotkey cheatsheet (Row 1, Col 1)
        block4 = QFrame()
        block4.setObjectName("bento_block")
        b4_layout = QVBoxLayout(block4)
        b4_layout.setContentsMargins(12, 12, 12, 12)
        
        title4 = QLabel("🎹 KEYBOARD SHORTCUTS")
        title4.setStyleSheet("font-size: 11px; font-weight: bold; color: #a78bfa; letter-spacing: 1px;")
        b4_layout.addWidget(title4)
        
        shortcuts_text = (
            "<b>Alt + Z</b> : Enter Command Mode<br>"
            "&nbsp;&nbsp;• <b>Space / H</b> : Hide Overlay HUD<br>"
            "&nbsp;&nbsp;• <b>S</b> : Scan Target Region<br>"
            "&nbsp;&nbsp;• <b>I</b> : Type Code Snippet"
        )
        shortcuts_lbl = QLabel(shortcuts_text)
        shortcuts_lbl.setStyleSheet("font-size: 11px; color: #cbd5e1; line-height: 1.4;")
        b4_layout.addWidget(shortcuts_lbl)
        
        b4_layout.addStretch()
        layout.addWidget(block4, 1, 1)
        
        self.tabs.addTab(tab, "Home")
        
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
        
        self.tabs.addTab(tab, "APIs")
        
    def init_paywall_tab(self):
        tab = QWidget()
        self.paywall_layout = QVBoxLayout(tab)
        self.paywall_layout.setContentsMargins(20, 20, 20, 20)
        
        self.render_paywall()
        self.tabs.addTab(tab, "Billing")
        
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
            
    def init_prompts_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Left side: list of prompts and add/delete buttons
        left_layout = QVBoxLayout()
        self.prompts_list = QListWidget()
        self.prompts_list.itemClicked.connect(self.on_prompt_selected)
        left_layout.addWidget(self.prompts_list)
        
        btn_row = QHBoxLayout()
        add_btn = QPushButton("New")
        add_btn.clicked.connect(self.add_new_prompt)
        btn_row.addWidget(add_btn)
        
        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet("background-color: #ef4444;")
        del_btn.clicked.connect(self.delete_prompt)
        btn_row.addWidget(del_btn)
        left_layout.addLayout(btn_row)
        layout.addLayout(left_layout, 2)
        
        # Right side: editing fields
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel("<b>Prompt Name:</b>"))
        self.prompt_name_input = QLineEdit()
        right_layout.addWidget(self.prompt_name_input)
        
        right_layout.addWidget(QLabel("<b>System Instructions:</b>"))
        self.prompt_content_input = QTextEdit()
        right_layout.addWidget(self.prompt_content_input)
        
        action_row = QHBoxLayout()
        save_prompt_btn = QPushButton("Save")
        save_prompt_btn.clicked.connect(self.save_prompt_edits)
        action_row.addWidget(save_prompt_btn)
        
        self.active_prompt_btn = QPushButton("Set Active")
        self.active_prompt_btn.setStyleSheet("background-color: #10b981;")
        self.active_prompt_btn.clicked.connect(self.set_prompt_active)
        action_row.addWidget(self.active_prompt_btn)
        
        right_layout.addLayout(action_row)
        layout.addLayout(right_layout, 3)
        
        self.tabs.addTab(tab, "Prompts")
        
        # Load from settings
        self.custom_prompts = self.settings.get("prompts", [
            {
                "name": "Standard AI Assistant",
                "content": "You are a highly capable AI assistant operating within a stealth overlay. Provide direct, concise answers. If providing code, always wrap it in ``` backticks. You have access to the user's Chat History. Use context intelligently."
            },
            {
                "name": "Software Engineer Interview",
                "content": "You are an expert software engineer helper. Provide clean, production-ready, optimally-formatted code solutions with zero extra conversational fluff. Do not explain unless specifically asked."
            }
        ])
        self.active_prompt_name = self.settings.get("active_prompt", "Standard AI Assistant")
        self.load_prompts_list()

    def load_prompts_list(self):
        self.prompts_list.clear()
        for p in self.custom_prompts:
            name = p["name"]
            if name == self.active_prompt_name:
                name = f"⭐ {name}"
            self.prompts_list.addItem(name)
        if self.prompts_list.count() > 0:
            self.prompts_list.setCurrentRow(0)
            self.on_prompt_selected(self.prompts_list.item(0))

    def on_prompt_selected(self, item):
        if not item: return
        clean_name = item.text().replace("⭐ ", "")
        for p in self.custom_prompts:
            if p["name"] == clean_name:
                self.prompt_name_input.setText(p["name"])
                self.prompt_content_input.setText(p["content"])
                if p["name"] == self.active_prompt_name:
                    self.active_prompt_btn.setEnabled(False)
                    self.active_prompt_btn.setText("Active")
                else:
                    self.active_prompt_btn.setEnabled(True)
                    self.active_prompt_btn.setText("Set Active")
                break

    def add_new_prompt(self):
        new_name = f"Custom Prompt {len(self.custom_prompts) + 1}"
        new_prompt = {
            "name": new_name,
            "content": "Enter system prompt instructions here..."
        }
        self.custom_prompts.append(new_prompt)
        self.settings["prompts"] = self.custom_prompts
        self.save_settings()
        self.load_prompts_list()
        for i in range(self.prompts_list.count()):
            if self.prompts_list.item(i).text() == new_name:
                self.prompts_list.setCurrentRow(i)
                self.on_prompt_selected(self.prompts_list.item(i))
                break

    def delete_prompt(self):
        curr_row = self.prompts_list.currentRow()
        if curr_row < 0: return
        item = self.prompts_list.item(curr_row)
        clean_name = item.text().replace("⭐ ", "")
        
        if clean_name == self.active_prompt_name:
            QMessageBox.warning(self, "Delete Denied", "Cannot delete the active prompt. Set another prompt active first.")
            return
            
        reply = QMessageBox.question(self, 'Delete Prompt', f"Delete '{clean_name}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.custom_prompts = [p for p in self.custom_prompts if p["name"] != clean_name]
            self.settings["prompts"] = self.custom_prompts
            self.save_settings()
            self.load_prompts_list()

    def save_prompt_edits(self):
        curr_row = self.prompts_list.currentRow()
        if curr_row < 0: return
        item = self.prompts_list.item(curr_row)
        old_name = item.text().replace("⭐ ", "")
        new_name = self.prompt_name_input.text().strip()
        new_content = self.prompt_content_input.toPlainText().strip()
        
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Prompt name cannot be empty.")
            return
            
        for p in self.custom_prompts:
            if p["name"] == old_name:
                p["name"] = new_name
                p["content"] = new_content
                break
                
        if old_name == self.active_prompt_name:
            self.active_prompt_name = new_name
            self.settings["active_prompt"] = new_name
            
        self.settings["prompts"] = self.custom_prompts
        self.save_settings()
        self.load_prompts_list()
        for i in range(self.prompts_list.count()):
            check_name = self.prompts_list.item(i).text().replace("⭐ ", "")
            if check_name == new_name:
                self.prompts_list.setCurrentRow(i)
                break

    def set_prompt_active(self):
        curr_row = self.prompts_list.currentRow()
        if curr_row < 0: return
        item = self.prompts_list.item(curr_row)
        clean_name = item.text().replace("⭐ ", "")
        
        self.active_prompt_name = clean_name
        self.settings["active_prompt"] = clean_name
        self.save_settings()
        self.load_prompts_list()

    def init_settings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(8)
        
        from PyQt5.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 10, 0)
        scroll_layout.setSpacing(8)
        
        # 1. Behavior Checkboxes Row
        cb_layout = QHBoxLayout()
        self.autostart_cb = QCheckBox("Autostart")
        self.autostart_cb.setChecked(self.settings.get("autostart", False))
        cb_layout.addWidget(self.autostart_cb)
        
        self.always_on_top_cb = QCheckBox("Stays on Top")
        self.always_on_top_cb.setChecked(self.settings.get("always_on_top", True))
        cb_layout.addWidget(self.always_on_top_cb)
        
        self.auto_scroll_cb = QCheckBox("Auto-Scroll")
        self.auto_scroll_cb.setChecked(self.settings.get("auto_scroll", True))
        cb_layout.addWidget(self.auto_scroll_cb)
        
        scroll_layout.addLayout(cb_layout)
        
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.05);")
        scroll_layout.addWidget(sep)
        
        # 2. Dropdown configurations grid
        grid = QGridLayout()
        grid.setSpacing(6)
        
        # Cursor Mode
        grid.addWidget(QLabel("<b>Cursor Settings:</b>"), 0, 0)
        self.cursor_mode_combo = QComboBox()
        self.cursor_mode_combo.addItems(["Default", "Invisible", "Auto"])
        self.cursor_mode_combo.setCurrentText(self.settings.get("cursor_mode", "Default"))
        grid.addWidget(self.cursor_mode_combo, 0, 1)
        
        # Scan Method
        grid.addWidget(QLabel("<b>Screen Capture Mode:</b>"), 1, 0)
        self.scan_method_combo = QComboBox()
        self.scan_method_combo.addItems(["Overlay Bounds", "Selection"])
        self.scan_method_combo.setCurrentText(self.settings.get("scan_method", "Overlay Bounds"))
        grid.addWidget(self.scan_method_combo, 1, 1)
        
        # Screenshot Processing Mode
        grid.addWidget(QLabel("<b>Screenshot Processing:</b>"), 2, 0)
        self.processing_mode_combo = QComboBox()
        self.processing_mode_combo.addItems(["Auto", "Manual"])
        self.processing_mode_combo.setCurrentText(self.settings.get("screenshot_processing_mode", "Auto"))
        grid.addWidget(self.processing_mode_combo, 2, 1)
        
        # AI Response Length
        grid.addWidget(QLabel("<b>AI Response Detail:</b>"), 3, 0)
        self.resp_length_combo = QComboBox()
        self.resp_length_combo.addItems(["Short", "Medium", "Detailed"])
        self.resp_length_combo.setCurrentText(self.settings.get("response_length", "Medium"))
        grid.addWidget(self.resp_length_combo, 3, 1)
        
        # AI Response Language
        grid.addWidget(QLabel("<b>AI Response Language:</b>"), 4, 0)
        self.resp_lang_combo = QComboBox()
        self.resp_lang_combo.addItems(["English", "Hindi", "Spanish", "Telugu", "French", "German", "Chinese", "Russian", "Arabic", "Portuguese"])
        self.resp_lang_combo.setCurrentText(self.settings.get("response_language", "English"))
        grid.addWidget(self.resp_lang_combo, 4, 1)
        
        scroll_layout.addLayout(grid)
        
        # 3. Screenshot Auto Prompt Configuration
        scroll_layout.addWidget(QLabel("<b>Screenshot Auto Prompt:</b>"))
        self.auto_prompt_input = QLineEdit()
        self.auto_prompt_input.setPlaceholderText("Configure prompt for automatic screenshot analysis...")
        self.auto_prompt_input.setText(self.settings.get("screenshot_auto_prompt", ""))
        scroll_layout.addWidget(self.auto_prompt_input)
        
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        
        # Save Button
        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.clicked.connect(self.save_app_settings)
        layout.addWidget(save_settings_btn)
        
        self.tabs.addTab(tab, "Settings")

    def save_app_settings(self):
        autostart = self.autostart_cb.isChecked()
        self.settings["autostart"] = autostart
        self.settings["always_on_top"] = self.always_on_top_cb.isChecked()
        self.settings["auto_scroll"] = self.auto_scroll_cb.isChecked()
        self.settings["cursor_mode"] = self.cursor_mode_combo.currentText()
        self.settings["scan_method"] = self.scan_method_combo.currentText()
        self.settings["screenshot_processing_mode"] = self.processing_mode_combo.currentText()
        self.settings["response_length"] = self.resp_length_combo.currentText()
        self.settings["response_language"] = self.resp_lang_combo.currentText()
        self.settings["screenshot_auto_prompt"] = self.auto_prompt_input.text()
        
        self.save_settings()
        toggle_registry_autostart(autostart)
        QMessageBox.information(self, "Success", "Application settings saved successfully.")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, 'drag_position'):
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def closeEvent(self, event):
        if self.verification_worker:
            self.verification_worker.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ManagerWindow()
    window.show()
    sys.exit(app.exec_())
