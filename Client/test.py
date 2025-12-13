import requests

token = "041bd4ef-4da8-4569-8fe9-56ef7d9cb18c"

headers = {}
headers['Authorization'] = f'Bearer {token}'

url = f"http://127.0.0.1:8000/events/{41}"
response = requests.delete(url, headers=headers, timeout=10)