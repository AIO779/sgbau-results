from email.mime.multipart import MIMEMultipart

outer = MIMEMultipart("form-data")
raw = outer.as_bytes()
print("Boundary:", outer.get_boundary())
print("Content-Type from get:", outer.get("Content-Type"))
