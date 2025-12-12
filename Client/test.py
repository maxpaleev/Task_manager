import requests

tg_id = 1347477792
message = ('hello\n'
           'world')

url = f"http://127.0.0.1:8000/items/{tg_id}?q={message}"
response = requests.get(url)