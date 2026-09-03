import os

t = os.environ.get('TELEGRAM_BOT_TOKEN', '')
print(f'Length: {len(t)}')
print(f'Starts with bot: {t.lower().startswith("bot")}')
print(f'Starts with quotes: {t.startswith(chr(34))}')
print(f'Ends with quotes: {t.endswith(chr(34))}')
print(f'Contains spaces: {" " in t}')
