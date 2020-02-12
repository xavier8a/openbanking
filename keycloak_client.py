import base64
import hashlib
import html
import json
import os
import re
import urllib.parse
import requests
from termcolor import colored

provider = "http://localhost:9090/auth/realms/master"
client_id = "pkce-test"
username = "xochoa"
password = "interdin.1"
redirect_uri = "http://localhost:8080/"


def _b64_decode(data):
    data += '=' * (4 - len(data) % 4)
    return base64.b64decode(data).decode('utf-8')


def jwt_payload_decode(jwt):
    _, payload, _ = jwt.split('.')
    return json.loads(_b64_decode(payload))


# PKCE code verifier and challenge
code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
code_verifier = re.sub('[^a-zA-Z0-9]+', '', code_verifier)
print("code_verifier {} len {}".format(code_verifier, code_verifier))

code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8')
code_challenge = code_challenge.replace('=', '')
print("code_challenge {} len {}".format(code_challenge, code_challenge))

# Request login page
print(colored("invoking /protocol/openid-connect/auth ...", "yellow"))
state = "xyz"
resp = requests.get(
    url=provider + "/protocol/openid-connect/auth",
    params={
        "response_type": "code",
        "client_id": client_id,
        "scope": "openid",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    },
    allow_redirects=False
)
print(
    colored(
        "status code response login page http-{}".format(resp.status_code),
        "green" if resp.status_code == 200 else "red"
    )
)

# Parse login page (response)
cookie = resp.headers['Set-Cookie']
cookie = '; '.join(c.split(';')[0] for c in cookie.split(', '))
print("cookie {} ...".format(cookie))

page = resp.text
form_action = html.unescape(re.search('<form\s+.*?\s+action="(.*?)"', page, re.DOTALL).group(1))
print("form_action {} ... ".format(form_action))

# Do the login (aka authenticate)
resp = requests.post(
    url=form_action,
    data={
        "username": username,
        "password": password,
    },
    headers={"Cookie": cookie},
    allow_redirects=False
)
print(
    colored(
        "status code response login http-{}".format(resp.status_code),
        "green" if resp.status_code == 200 else "red"
    )
)


redirect = resp.headers['Location']

print("api redirect {} ...".format(redirect))
assert redirect.startswith(redirect_uri)

# Extract authorization code from redirect

query = urllib.parse.urlparse(redirect).query
redirect_params = urllib.parse.parse_qs(query)
print("redirect_params {} ...".format(redirect_params))

auth_code = redirect_params['code'][0]
print("auth_code {} ...".format(auth_code))

# Exchange authorization code for an access token
resp = requests.post(
    url=provider + "/protocol/openid-connect/token",
    data={
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": auth_code,
        "code_verifier": code_verifier,
    },
    allow_redirects=False
)
print(
    colored(
        "status code response authorization code for an access token http-{}".format(resp.status_code),
        "green" if resp.status_code == 200 else "red"
    )
)

result = resp.json()
print("result => {}".format(json.dumps(result)))

# Decode the JWT tokens (Access Token)
access_token = jwt_payload_decode(result['access_token'])
print("access_token => {}".format(json.dumps(access_token)))

# Decode the JWT tokens (ID Token)
id_token = jwt_payload_decode(result['id_token'])
print("id_token => {}".format(json.dumps(id_token)))
