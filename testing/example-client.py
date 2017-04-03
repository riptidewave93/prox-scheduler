#!/usr/bin/env python3
#
import requests
import json
try:
    from options import *
except ImportError:
    print('Error importing options.py. Did you rename and edit options.py.example?')
    sys.exit(1)

# Call our API
headers = {'content-type': 'application/json'}
response = requests.post(url,
                         auth=(user, passwd),
                          data=json.dumps(dataz), headers=headers)
data = response.json()
print(data)
