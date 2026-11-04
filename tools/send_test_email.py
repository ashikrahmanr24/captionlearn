import argparse, os, smtplib
from email.message import EmailMessage
from email.utils import formataddr
from dotenv import load_dotenv
load_dotenv()
p=argparse.ArgumentParser();p.add_argument("to");a=p.parse_args();u,pw=os.getenv("SMTP_USER"),os.getenv("SMTP_PASSWORD")
if not u or not pw: raise SystemExit("Set SMTP_USER and SMTP_PASSWORD in .env")
m=EmailMessage();m["Subject"]="CaptionLearn email setup test";m["From"]=formataddr((os.getenv("SMTP_FROM_NAME","CaptionLearn"),u));m["To"]=a.to;m.set_content("CaptionLearn email delivery is configured correctly.")
host,port=os.getenv("SMTP_HOST","smtp.gmail.com"),int(os.getenv("SMTP_PORT","465"))
if os.getenv("SMTP_SECURITY","ssl").lower()=="starttls":
 with smtplib.SMTP(host,port,timeout=10) as s:s.starttls();s.login(u,pw);s.send_message(m)
else:
 with smtplib.SMTP_SSL(host,port,timeout=10) as s:s.login(u,pw);s.send_message(m)
print("Test email sent.")
