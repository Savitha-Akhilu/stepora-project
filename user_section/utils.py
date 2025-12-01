from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags

def send_otp_email(email, username, otp, validity_minutes=1):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background:#f6f6f6; padding:20px;">
        <div style="max-width:500px; margin:auto; background:#ffffff; padding:20px; 
                    border-radius:8px; box-shadow:0 0 10px rgba(0,0,0,0.08);">

            <h2 style="text-align:center; color:#333; margin-top:0;">
                Stepora Verification
            </h2>

            <p>Hello <strong>{username}</strong>,</p>

            <p>Your One-Time Password (OTP) is:</p>

            <div style="text-align:center; padding:15px; background:#f1f1f1; 
                        border-radius:6px; font-size:24px; font-weight:bold;">
                {otp}
            </div>

            <p style="margin-top:20px;">
                This OTP is valid for <strong>{validity_minutes} minute(s)</strong>.
            </p>
            
            <p>Please do not share this OTP with anyone.</p>

            <p>If this was not you, simply ignore this message.</p>

            <p style="margin-top:30px;">Regards,<br>
            <strong>Team Stepora</strong><br>
            <a href="https://stepora.com" style="color:#0066cc;">www.stepora.com</a></p>

        </div>
    </body>
    </html>
    """

    text_content = strip_tags(html_content)

    email_msg = EmailMultiAlternatives(
        subject="Your OTP for Stepora",
        body=text_content,
        to=[email]
    )
    email_msg.attach_alternative(html_content, "text/html")
    email_msg.send()
