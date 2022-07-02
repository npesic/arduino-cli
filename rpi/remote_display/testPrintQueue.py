import requests
url = 'http://head2toes.asuscomm.com/sub/example/printQueue.json'
payload = {"text":"Hi from Py!","x":200,"y":200}
res = requests.put(url, json=payload)
print(res)
print(res.json())
