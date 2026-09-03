import asyncio
import os
import urllib.request
import json
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

# Mock telegram bot token and chat id for testing format
def send_document_test():
    filename = "test.csv"
    file_bytes = b"roll,name\n123,test"
    caption = "test caption"
    
    outer = MIMEMultipart("form-data")

    def _field(name: str, value: str) -> MIMEBase:
        part = MIMEBase("text", "plain")
        part.add_header("Content-Disposition", "form-data", name=name)
        part.set_payload(value)
        return part

    outer.attach(_field("chat_id", "1234"))
    outer.attach(_field("caption", caption))

    file_part = MIMEBase("application", "octet-stream")
    file_part.add_header(
        "Content-Disposition", "form-data",
        name="document", filename=filename,
    )
    file_part.set_payload(file_bytes)
    outer.attach(file_part)

    content_type = outer["Content-Type"]
    print("Content-Type:", content_type)
    
    raw = outer.as_bytes()
    print("Raw headers + body split:")
    print(repr(raw[:200]))
    try:
        raw_body = raw.split(b"\n\n", 1)[1].replace(b"\n", b"\r\n")
        print("Body parsed ok, length:", len(raw_body))
    except Exception as e:
        print("Error parsing body:", e)

send_document_test()
