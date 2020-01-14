import logging
import json
import os
import sys
import urllib
import urllib.request
from urllib.parse import urlencode, quote_plus

sys.path.insert(
    0,
    os.path.abspath(os.path.realpath(__file__) + '/../../../')
)

from wsgiref.simple_server import make_server, WSGIRequestHandler

logging.basicConfig(level=logging.DEBUG)


class ClientRequestHandler(WSGIRequestHandler):
    """
    Request handler that enables formatting of the log messages on the console.

    This handler is used by the client application.
    """

    def address_string(self):
        return "client app"


class ClientApplication(object):
    """
    Very basic application that simulates calls to the API of the
    python-oauth2 app.
    """
    callback_url = "http://localhost:8080/"
    client_id = "openbanking"
    client_secret = "CtEsG8EeUcXdFFFkdzUrnARyXqIyTVA2"
    api_server_url = "http://localhost:8088"

    def __init__(self):
        self.access_token = None
        self.auth_token = None
        self.token_type = ""

    def __call__(self, env, start_response):
        if env["PATH_INFO"] == "/app":
            status, body, headers = self._serve_application(env)
        elif env["PATH_INFO"] == "/callback":
            status, body, headers = self._read_auth_token(env)
        else:
            status = "301 Moved"
            body = ""
            headers = {"Location": "/app"}

        start_response(
            status,
            [(header, val) for header, val in headers.items()]
        )
        return body

    def _request_access_token(self):
        print("Requesting access token...")

        post_params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": self.auth_token,
            "grant_type": "authorization_code",
            "redirect_uri": self.callback_url
        }

        token_endpoint = self.api_server_url + "/token"

        data = json.dumps(post_params).encode()
        req = urllib.request.Request(
            url=token_endpoint,
            data=data,
            method='POST'
        )
        with urllib.request.urlopen(req) as f:
            response = f.read()
            if len(response) > 1:
                resp = json.loads(response)
                self.access_token = resp["access_token"]
                self.token_type = resp["token_type"]

        confirmation = "Received access token '%s' of type '%s'" \
                       % (self.access_token, self.token_type)
        print(confirmation)

        return "302 Found", "", {"Location": "/app"}

    def _read_auth_token(self, env):
        print("Receiving authorization token...")

        query_params = urllib.parse.parse_qs(env["QUERY_STRING"])

        if "error" in query_params:
            location = "/app?error=" + query_params["error"][0]
            return "302 Found", "", {"Location": location}

        self.auth_token = query_params["code"][0]

        print(
            "Received temporary authorization token '%s'"
            % (self.auth_token,)
        )

        return "302 Found", "", {"Location": "/app"}

    def _request_auth_token(self):
        print("Requesting authorization token...")

        auth_endpoint = self.api_server_url + "/authorize"
        query = urlencode(
            {
                "client_id": "openbanking",
                "redirect_uri": self.callback_url,
                "response_type": "code"
            },
            quote_via=quote_plus
        )

        location = "%s?%s" % (auth_endpoint, query)

        return "302 Found", "", {"Location": location}

    def _serve_application(self, env):
        query_params = urllib.parse.parse_qs(env["QUERY_STRING"])

        if (
                "error" in query_params
                and query_params["error"][0] == "access_denied"
        ):
            return "200 OK", "User has denied access", {}

        if self.access_token is None:
            if self.auth_token is None:
                return self._request_auth_token()
            else:
                return self._request_access_token()
        else:
            confirmation = "Current access token '%s' of type '%s'" \
                           % (self.access_token, self.token_type)
            return "200 OK", str(confirmation), {}


def run_app_server():
    try:
        app = ClientApplication()
        httpd = make_server(
            '',
            8081,
            app,
            handler_class=ClientRequestHandler
        )
        print("Starting Client app on http://localhost:8081/...")
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


def main():
    print("Access http://localhost:8081/app in your browser")
    run_app_server()


if __name__ == "__main__":
    main()
