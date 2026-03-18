import os
import pandas as pd
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from supabase import create_client

# 設定
SUPABASE_URL      = os.environ["SUPABASE_URL"]
SUPABASE_KEY      = os.environ["SUPABASE_KEY"]
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
BACKUP_EMAIL      = os.environ["BACKUP_EMAIL"]

def fetch_table(sb, table_name):
    res = sb.table(table_name).select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def send_email(attachments: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USER
    msg["To"]      = BACKUP_EMAIL
    msg["Subject"] = f"英文練習系統備份 {today}"

    msg.attach(MIMEText(f"附件為 {today} 的資料備份，包含 logs 和 assignments。", "plain", "utf-8"))

    for filename, df in attachments.items():
        csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
        part = MIMEBase("application", "octet-stream")
        part.set_payload(csv_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, BACKUP_EMAIL, msg.as_string())
    print("✅ 備份 Email 已寄出")

if __name__ == "__main__":
    print("🔄 連接 Supabase...")
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    today = datetime.now().strftime("%Y%m%d")
    print("📥 讀取資料...")
    df_logs   = fetch_table(sb, "logs")
    df_assign = fetch_table(sb, "assignments")

    print(f"  logs: {len(df_logs)} 筆")
    print(f"  assignments: {len(df_assign)} 筆")

    send_email({
        f"logs_{today}.csv":        df_logs,
        f"assignments_{today}.csv": df_assign,
    })
