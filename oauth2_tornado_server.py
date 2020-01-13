import logging
import oauth2
import os
import sys
import selectors
import asyncio

sys.path.insert(0, os.path.abspath(os.path.realpath(__file__) + '/../../../'))

from oauth2 import Provider
from oauth2.error import UserNotAuthenticated
from oauth2.store.memory import ClientStore, TokenStore
from oauth2.web.tornado import OAuth2Handler
from tornado.web import Application, url
from wsgiref.simple_server import WSGIRequestHandler

logging.basicConfig(level=logging.DEBUG)


class OAuthRequestHandler(WSGIRequestHandler):
    """
    Request handler that enables formatting of the log messages on the console.

    This handler is used by the python-oauth2 application.
    """

    def address_string(self):
        return "python-oauth2"


# Create a SiteAdapter to interact with the user.
# This can be used to display confirmation dialogs and the like.
class TestSiteAdapter(oauth2.web.AuthorizationCodeGrantSiteAdapter):
    """
    This adapter renders a confirmation page so the user can confirm the auth
    request.
    """

    CONFIRMATION_TEMPLATE = """
        <html>
            <body>
                <p>
                    <a href="{url}&confirm=1">confirm</a>
                </p>
                <p>
                    <a href="{url}&confirm=0">deny</a>
                </p>
            </body>
        </html>
    """

    def render_auth_page(self, request, response, environ, scopes, client):
        url_auth = request.path + "?" + request.query_string
        response.body = self.CONFIRMATION_TEMPLATE.format(url=url_auth)

        return response

    def authenticate(self, request, environ, scopes, client):
        # Check if the user has granted access
        if request.method == "GET":
            if request.get_param("confirm") == "1":
                return
        raise UserNotAuthenticated

    def user_has_denied_access(self, request):
        # Check if the user has denied access
        if request.method == "GET":
            if request.get_param("confirm") == "0":
                return True
        return False


def run_auth_server():
    # Create an in-memory storage to store your client apps.
    client_store = oauth2.store.memory.ClientStore()
    # Add a client
    client_store.add_client(client_id="openbanking", client_secret="CtEsG8EeUcXdFFFkdzUrnARyXqIyTVA2",
                            redirect_uris=["http://localhost:8080/"])

    # Create an in-memory storage to store issued tokens.
    # LocalTokenStore can store access and auth tokens
    token_store = TokenStore()

    # Create the controller.
    provider = Provider(
        access_token_store=token_store,
        auth_code_store=token_store,
        client_store=client_store,
        token_generator=oauth2.tokengenerator.Uuid4()
    )
    # Add Grants you want to support
    provider.add_grant(oauth2.grant.AuthorizationCodeGrant(site_adapter=TestSiteAdapter()))

    # Add refresh token capability and set expiration time of access tokens
    # to 5 minutes
    provider.add_grant(oauth2.grant.RefreshToken(expires_in=300))

    try:
        app = Application([
            url(provider.authorize_path, OAuth2Handler, dict(provider=provider)),
            url(provider.token_path, OAuth2Handler, dict(provider=provider)),
        ])
        selector = selectors.SelectSelector()
        loop = asyncio.SelectorEventLoop(selector)
        asyncio.set_event_loop(loop)
        app.listen(8088)
        print("Starting OAuth2 server on http://localhost:8088/...")
        loop.run_forever()

    except KeyboardInterrupt:
        loop.stop()


if __name__ == "__main__":
    run_auth_server()
