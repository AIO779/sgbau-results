import email.policy
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart

outer = MIMEMultipart("form-data")
file_part = MIMEBase("application", "octet-stream")
file_part.add_header("Content-Disposition", "form-data", name="document", filename="test.csv")
file_part.set_payload(b"abc\r\n123")
outer.attach(file_part)

raw = outer.as_bytes(policy=email.policy.HTTP)
print(repr(raw))
print("Split body:", repr(raw.split(b"\r\n\r\n", 1)[1]))
