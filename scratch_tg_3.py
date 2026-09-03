from email.mime.multipart import MIMEMultipart

outer = MIMEMultipart("form-data")
raw = outer.as_bytes()
ct = outer.get("Content-Type")
print("Content-Type repr:", repr(ct))
