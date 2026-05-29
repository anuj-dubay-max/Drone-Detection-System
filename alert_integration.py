# Alert Integration Module
# Add these functions to your AlertSystem class in the main code

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import requests
import time
from datetime import datetime

class EnhancedAlertSystem:
    """Enhanced alert system with Email and Telegram support"""
    
    def __init__(self):
        self.last_alert_time = {}
        self.alert_log = []
        
        # Email Configuration
        self.email_enabled = False
        self.email_config = {
            'smtp_server': 'smtp.gmail.com',
            'smtp_port': 587,
            'from_email': 'mroyal1325@gmail.com',
            'from_password': 'your_app_password',  # Use App Password, not regular password
            'to_email': 'recipient@gmail.com'
        }
        
        # Telegram Configuration
        self.telegram_enabled = False
        self.telegram_config = {
            'bot_token': 'YOUR_BOT_TOKEN_HERE',
            'chat_id': 'YOUR_CHAT_ID_HERE'
        }
    
    def configure_email(self, smtp_server, smtp_port, from_email, from_password, to_email):
        """Configure email alert settings"""
        self.email_config = {
            'smtp_server': smtp_server,
            'smtp_port': smtp_port,
            'from_email': from_email,
            'from_password': from_password,
            'to_email': to_email
        }
        self.email_enabled = True
        print("✅ Email alerts configured")
    
    def configure_telegram(self, bot_token, chat_id):
        """Configure Telegram bot settings"""
        self.telegram_config = {
            'bot_token': bot_token,
            'chat_id': chat_id
        }
        self.telegram_enabled = True
        print("✅ Telegram alerts configured")
    
    def send_email_alert(self, drone_id, threat_level, position, screenshot_path=None):
        """Send email alert with optional screenshot"""
        if not self.email_enabled:
            return False
        
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.email_config['from_email']
            msg['To'] = self.email_config['to_email']
            msg['Subject'] = f"🚨 DRONE ALERT: {threat_level} Threat Detected"
            
            # Email body
            body = f"""
            DRONE DETECTION ALERT
            
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Drone ID: {drone_id}
            Threat Level: {threat_level}
            Position: {position}
            
            This is an automated alert from your Drone Detection System.
            
            Action Required:
            - Review the detection immediately
            - Check system logs for details
            - Verify restricted area security
            
            ---
            Advanced Drone Detection & Deflection System
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Attach screenshot if available
            if screenshot_path:
                try:
                    with open(screenshot_path, 'rb') as f:
                        img = MIMEImage(f.read())
                        img.add_header('Content-Disposition', 'attachment', 
                                     filename=screenshot_path)
                        msg.attach(img)
                except Exception as e:
                    print(f"Could not attach screenshot: {e}")
            
            # Send email
            server = smtplib.SMTP(self.email_config['smtp_server'], 
                                 self.email_config['smtp_port'])
            server.starttls()
            server.login(self.email_config['from_email'], 
                        self.email_config['from_password'])
            text = msg.as_string()
            server.sendmail(self.email_config['from_email'], 
                          self.email_config['to_email'], text)
            server.quit()
            
            print(f"✅ Email alert sent for Drone {drone_id}")
            return True
            
        except Exception as e:
            print(f"❌ Email alert failed: {e}")
            return False
    
    def send_telegram_alert(self, drone_id, threat_level, position, screenshot_path=None):
        """Send Telegram alert with optional photo"""
        if not self.telegram_enabled:
            return False
        
        try:
            # Prepare message
            message = f"""
🚨 *DRONE ALERT*

🆔 Drone ID: `{drone_id}`
⚠️ Threat Level: *{threat_level}*
📍 Position: `{position}`
🕐 Time: `{datetime.now().strftime('%H:%M:%S')}`

_Advanced Drone Detection System_
            """
            
            bot_token = self.telegram_config['bot_token']
            chat_id = self.telegram_config['chat_id']
            
            # Send photo if available
            if screenshot_path:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
                    with open(screenshot_path, 'rb') as photo:
                        files = {'photo': photo}
                        data = {
                            'chat_id': chat_id,
                            'caption': message,
                            'parse_mode': 'Markdown'
                        }
                        response = requests.post(url, files=files, data=data)
                        
                        if response.status_code == 200:
                            print(f"✅ Telegram alert sent with photo for Drone {drone_id}")
                            return True
                except Exception as e:
                    print(f"Photo upload failed, sending text only: {e}")
            
            # Send text message
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, data=data)
            
            if response.status_code == 200:
                print(f"✅ Telegram alert sent for Drone {drone_id}")
                return True
            else:
                print(f"❌ Telegram alert failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Telegram alert failed: {e}")
            return False
    
    def send_alert(self, drone_id, threat_level, position, screenshot_path=None):
        """Main alert function - sends through all enabled channels"""
        current_time = time.time()
        key = f"{drone_id}_{threat_level}"
        
        # Check cooldown
        if key in self.last_alert_time:
            if current_time - self.last_alert_time[key] < 5:  # 5 second cooldown
                return False
        
        self.last_alert_time[key] = current_time
        
        # Log alert
        alert = {
            'timestamp': datetime.now().isoformat(),
            'drone_id': drone_id,
            'threat_level': threat_level,
            'position': position
        }
        self.alert_log.append(alert)
        
        # Console alert (always)
        print(f"\n⚠️  ALERT: Drone {drone_id} - {threat_level} threat at {position}")
        
        # Email alert
        if self.email_enabled and threat_level in ['HIGH', 'CRITICAL']:
            self.send_email_alert(drone_id, threat_level, position, screenshot_path)
        
        # Telegram alert
        if self.telegram_enabled and threat_level in ['HIGH', 'CRITICAL']:
            self.send_telegram_alert(drone_id, threat_level, position, screenshot_path)
        
        return True


# ==================== SETUP GUIDES ====================

def setup_gmail_alerts():
    """
    GMAIL SETUP GUIDE:
    
    1. Enable 2-Factor Authentication on your Gmail account
    2. Go to: https://myaccount.google.com/apppasswords
    3. Generate an "App Password" for "Mail"
    4. Use this 16-character password (not your regular Gmail password)
    
    Example configuration:
    
    alert_system = EnhancedAlertSystem()
    alert_system.configure_email(
        smtp_server='smtp.gmail.com',
        smtp_port=587,
        from_email='your_email@gmail.com',
        from_password='your_16_char_app_password',
        to_email='recipient@gmail.com'
    )
    """
    pass

def setup_telegram_bot():
    """
    TELEGRAM BOT SETUP GUIDE:
    
    1. Open Telegram and search for "@BotFather"
    2. Send command: /newbot
    3. Choose a name and username for your bot
    4. BotFather will give you a TOKEN like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    5. Start a chat with your new bot
    6. Send any message to your bot
    7. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
    8. Look for "chat":{"id": YOUR_CHAT_ID}
    9. Copy your chat_id
    
    Example configuration:
    
    alert_system = EnhancedAlertSystem()
    alert_system.configure_telegram(
        bot_token='123456789:ABCdefGHIjklMNOpqrsTUVwxyz',
        chat_id='your_chat_id'
    )
    
    Testing:
    alert_system.send_telegram_alert(1, "HIGH", (100, 200))
    """
    pass


# ==================== USAGE EXAMPLE ====================

if __name__ == "__main__":
    print("📧 Email & Telegram Alert Integration Module")
    print("=" * 60)
    print("\nThis module provides email and Telegram alerts.")
    print("\nTo integrate into main system:")
    print("1. Replace AlertSystem with EnhancedAlertSystem")
    print("2. Configure email/telegram credentials")
    print("3. Alerts will be sent automatically on HIGH/CRITICAL threats")
    print("\n" + "=" * 60)
    
    # Example usage
    print("\nExample Configuration:\n")
    print("""
# In your main code, replace AlertSystem initialization with:

alert_system = EnhancedAlertSystem()

# Configure Email (optional)
alert_system.configure_email(
    smtp_server='smtp.gmail.com',
    smtp_port=587,
    from_email='your_email@gmail.com',
    from_password='your_app_password',
    to_email='recipient@gmail.com'
)

# Configure Telegram (optional)
alert_system.configure_telegram(
    bot_token='YOUR_BOT_TOKEN',
    chat_id='YOUR_CHAT_ID'
)

# Now alerts will be sent via email and Telegram automatically!
    """)
    
    print("\n" + "=" * 60)
    print("📚 For detailed setup guides, see functions:")
    print("  - setup_gmail_alerts()")
    print("  - setup_telegram_bot()")
    print("=" * 60)


# ==================== TESTING FUNCTION ====================

def test_alerts():
    """Test alert system with dummy data"""
    alert_system = EnhancedAlertSystem()
    
    print("\n🧪 Testing Alert System\n")
    
    # Test email
    if input("Test email alerts? (y/n): ").lower() == 'y':
        smtp_server = input("SMTP Server [smtp.gmail.com]: ") or 'smtp.gmail.com'
        smtp_port = int(input("SMTP Port [587]: ") or '587')
        from_email = input("From Email: ")
        from_password = input("App Password: ")
        to_email = input("To Email: ")
        
        alert_system.configure_email(smtp_server, smtp_port, from_email, 
                                     from_password, to_email)
        
        print("\nSending test email...")
        alert_system.send_email_alert(999, "HIGH", (100, 200))
    
    # Test Telegram
    if input("\nTest Telegram alerts? (y/n): ").lower() == 'y':
        bot_token = input("Bot Token: ")
        chat_id = input("Chat ID: ")
        
        alert_system.configure_telegram(bot_token, chat_id)
        
        print("\nSending test Telegram message...")
        alert_system.send_telegram_alert(999, "HIGH", (100, 200))
    
    print("\n✅ Testing complete!")

# Uncomment to run tests:
# test_alerts()