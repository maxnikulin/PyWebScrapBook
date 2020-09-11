
"""
Proof of concept modular approach to authentication in PyWebScrapbook

- TODO Test expired session
- TODO Cut it in smaller parts
- TODO Move `SentinelValue` to util
- TODO logging
"""

import functools
import logging
import os
import secrets
# FIXME It seems at least Literal is available only in 3.8
from typing import Callable, Dict, List, Literal, NewType, Optional, Tuple, Union

from flask import request, Response, session
from werkzeug.datastructures import WWWAuthenticate
from werkzeug.exceptions import Forbidden, HTTPException, Unauthorized

from .util import encrypt as util_encrypt

logger = logging.getLogger(__name__)
AuthenticationEntry = NewType('AuthenticationEntry', dict)


class SentinelValue:
    """Sentinel value pattern to distinguish default value from `None`

    A bit more informative in stack traces than just

        _DEFAULT = object()

    Alternatives such as `unittest.mock.sentinel` are described in the references
    given in https://python-patterns.guide/python/sentinel-object/

    >>> NOTHING = SentinelValue('NOTHING')
    >>> some_dict = {'key': None}
    >>> some_dict.get('key', NOTHING) == None
    True
    >>> some_dict.get('absent', NOTHING)
    <SentinelValue('NOTHING')>
    >>> str(NOTHING)
    'NOTHING'
    """

    def __init__(self, name: str):
        self._name = name

    def __str__(self):
        return self._name

    def __repr__(self):
        return '<{}({!r})>'.format(self.__class__.__name__, self._name)


SUCCESS = SentinelValue('SUCCESS')
"""Explicit request approval in authorization plugin

Used to protect against logic error and catch unintentional return.
"""


class AuthenticationFailed(RuntimeError):
    pass


class InconsistentAuthenticationArguments(RuntimeError):
    pass


class AuthorizationFailed(RuntimeError):
    pass


class PluginDependencyError(RuntimeError):
    pass


class PasswordValue:
    """Avoid leak of passwords to logs"""

    def __init__(self, value: Optional[str]=None):
        if isinstance(value, PasswordValue):
            self._value = value.value
        self._value = value

    @property
    def value(self) -> Optional[str]:
        return self._value

    def __str__(self):
        if self._value:
            return '********'
        return str(self._value)

    def __bool__(self):
        return bool(self._value)


class AuthenticationPlugin:
    """Authentication plugin base class.

    Chain of authentication plugins (session, basic authentication,
    temporary authentication tokens for "session-less" API requests, etc.)
    are processed by an authorization plugin.
    """
    # TODO additionally return result, e.g. new session
    # Explicit `Union[SomeType, None]` should be more clear than `Optional` for the argument.
    def check(
            self,
            entry: Union[AuthenticationEntry, None]
            ) -> Optional[AuthenticationEntry]:
        """
        Check if HTTP request has enough information to authenticate the client

        Obtain session cookie, authentication credentials or tokens
        from request, check they are consistent with authentication
        entry returned by earlier queried plugin.

        Plugin could confirm passed entry by returning it,
        provide an entry when `None` is passed, replace, or withdraw
        passed entry.

        Must be implemented by derivatives.
        """
        raise NotImplementedError()

    def on_success(
            self,
            entry: AuthenticationEntry,
            response: Union[Response, None]
            ) -> Optional[Response]:
        """Setup session, update internal data in the case of successful authentication

        Executed when all authentication plugins confirm that there is no problem
        with authentication.

        Could be used to update shot-term session if long-living is still valid
        E.g. in OAuth2 refresh token should be used to obtain new access token.
        Alternatively session could have inactivity timeout
        and hard expiration time independent of activity.

        Notice that authorization for particular resource could fail
        even if client is successfully authenticated.
        """
        return response

    def on_authentication_error(
            self, response, exc: Exception
            ) -> Union[HTTPException, Response, None]:
        """Optionally generate response if `check()` method of some plugin
        raised an exception.

        Likely it is not wise to immediately reset authentication
        since user may click on a specially crafted link that
        aim is to abandon user session or to login as another user.

        Method could pass through response and exception,
        overwrite response, or convert exception to response.
        """
        return response, exc

    def on_authorization_error(
            self, response, exc: Exception
            ) -> Union[HTTPException, Response, None]:
        """Optionally generate response if user is authenticated
        but e.g. it is requested write operation having
        just read-only permissions.

        Likely it is better to avoid immediate login prompt here.

        Method could pass through response and exception,
        overwrite response, or convert exception to response.
        """
        return response, exc

    def clear(self) -> None:
        """Could be suitable to implement logout"""
        pass


class ClientSessionAuthentication(AuthenticationPlugin):
    """Simple werkzeug session encrypted data stored only in cookie

    Pure client-side session. Only secret key shared by all sessions
    is saved on the server.

    Change of password hash invalidates previously created sessions
    (either change password or regenerate hash with new salt).

    Since no information related to sessions (besides encryption key)
    is stored on the server:

    - It is impossible to audit how many active sessions each user has
    - It is hard to invalidate currently active sessions especially
      if there are several users on the server.

    TODO: maybe add "session epoch" to allow invalidation of sessions.
    """

    # TODO clear session should be called somewhere (logout page)
    id_key = 'auth_id'
    hash_key = 'auth_pw'

    def __init__(self, authentication_db, werkzeug_secret_key_plugin):
        self._authentication_db = authentication_db
        if werkzeug_secret_key_plugin is None:
            raise PluginDependencyError(
                "ClientSessionAuthentication requires initialization of werkzeug session secret key")

    def check(
            self,
            entry: Union[AuthenticationEntry, None]
            ) -> Optional[AuthenticationEntry]:
        """Implicit argument: `flask.session`"""

        if entry is None:
            authentication_id = session.get(self.id_key)
            if authentication_id is not None:
                entry = self._authentication_db.query({'id': authentication_id})

        if entry is None:
            return None

        password_hash = session.get(self.hash_key, '')
        if not secrets.compare_digest(password_hash, entry.get('pw', '')):
            raise InconsistentAuthenticationArguments("Session is expired")

        return entry

    def on_success(
            self,
            entry: AuthenticationEntry,
            response: Union[Response, None]
            ) -> Optional[Response]:
        if self.id_key not in session:
            if not entry:
                if session:
                    session.clear()
                return

            session.permanent = True
            session[self.id_key] = entry['id']
            # Protect against session survived after password change.
            # TODO Consider using of just last 6-8 hash characters to make cookie shorter.
            password_hash = entry.get('pw')
            if password_hash:
                session[self.hash_key] = password_hash

    def clear(self) -> None:
        session.clear()


class BasicHttpAuthentication(AuthenticationPlugin):
    def __init__(self, authentication_db):
        self._authentication_db = authentication_db

    def check(
            self,
            entry: Union[AuthenticationEntry, None]
            ) -> Optional[AuthenticationEntry]:
        """Implicit argument: `request.authorization`"""

        credentials = request.authorization
        if not credentials:
            return entry

        username = credentials.get('username')
        if not entry:
            entry = self._authentication_db.query({'username': username})
        elif username != entry.get('user'):
            raise InconsistentAuthenticationArguments("Attempt to change login")

        if not entry:
            return None

        password = PasswordValue(credentials.get('password'))
        if not self._authentication_db.check(entry, {
                'username': username, 'password': password,
                }):
            raise AuthenticationFailed()

        return entry

    def on_authentication_error(self, response, exc):
        if response:
            return response, exc
        elif isinstance(exc, (AuthenticationFailed, AuthorizationFailed)):
            # TODO See a note why it is bad in `AuthenticationPlugin` method docs
            return self.request_http_basic_authentication(), None
        return response, exc

    on_authorization_error = on_authentication_error

    def request_http_basic_authentication(self):
        auth_app = WWWAuthenticate()
        # TODO Consider a better messages
        auth_app.set_basic('Authentication required.')
        # TODO Setting `SameSite=Strict` cookie could help against
        # links with login and password on external sites.
        # Maybe it is worth using `itsdangerous` independent of regular session.
        # While captured pages are served from the same Origin,
        # it would not protect against similar links in the collection.
        # Unsure if Path cookie parameter could be a rescue.
        return Unauthorized('You are not authorized.', www_authenticate=auth_app)


class InconsistentAuthenticationIsForbidden(AuthenticationPlugin):
    """Just send 403 Forbidden if e.g. session is inconsistent with basic HTTP authorization

    Almost unlikely since browser does to send credentials till 401.

    Considerations for better reaction:
    - Authentication through link with embedded credentials from external site
      must be ignored. Especial attention should be payed to attempts to **change**
      login.
    - In the case of authentication through redirection to a dedicated page,
      API calls should receive just 403 Forbidden instead of redirection.
    - I am afraid to send Unauthorized with WWWAuthenticate in response to any request.
      Login/logout likely should be implemented through dedicated pages even for basic
      HTTP authorization.
    """
    def on_authentication_error(self, result, exc):
        if result:
            return result, exc
        elif isinstance(exc, InconsistentAuthenticationArguments):
            # Actual reason should not be revealed to a random visitor.
            # FIXME add logging here.
            # Use `Forbidden` since `Unauthorized` requires `WWWAuthenticate`
            return Forbidden(), None
        return result, exc

    on_authorization_error = on_authentication_error

    def check(self, entry):
        return entry


class RejectBasicHTTPAuthentication(AuthenticationPlugin):
    """Try to catch client-server misconfiguration

    Reject requests if client assumes that server requires authentication
    and passes credentials, but server (e.g. by mistake) got no
    authentication configuration.

    Unfortunately this likely would not work due to browser does not send
    credentials till it receives 401 Unauthorized.

    Maybe client could pass a special argument to force credentials check
    if there is no active session.
    """
    def check(self, entry):
        if request.authorization:
            raise InconsistentAuthenticationArguments()
        return entry


# TODO to application-specific code
def simple_authorization_check(authentication_entry: AuthenticationEntry) -> bool:
    """Ini config has perm key in auth entry

    Implicit argument: `flask.request`.
    """
    if not authentication_entry:
        return False

    action = request.action
    perm = authentication_entry.get('permission', all)
    if perm == 'all':
        return True

    elif perm == 'read':
        if action in {'token', 'lock', 'unlock', 'mkdir', 'save', 'delete', 'move', 'copy'}:
            return False
        else:
            return True

    elif perm == 'view':
        if action in {'view', 'source', 'static'}:
            return True
        else:
            return False

    else:
        return False


class DictPasswordAuthenticationDb:
    """`{'AUTH_ID': {'user': 'LOGIN', 'pw': 'PASSWORD', etc}` entries

    TODO. Expensive password hash should be used for persistent storage.
    (pbkdf2 as in `werkzeug.security.generate_password_hash`, argon2, scrypt)

    Browser could send authentication header in each request,
    so it would be slow and resource consuming to compute true hash.

    TODO. Short part of fast hash as sha1 stored inside session should be enough
    for coarse consistency check but hardly enough for brute force attack
    to restore original password if hash is leaked to logs.

    TODO Create index user name to authentication id.

    TODO More consistent field name for user name
    """

    IniDbDict = NewType("IniDbDict", Dict[str, dict])

    def __init__(self, config: Union[IniDbDict, Callable[[], IniDbDict]]):
        """`config` could be dict or callable (e.g. lambda)"""
        self._config = config

    def get_entry_by_username(self, username: str) -> Optional[AuthenticationEntry]:
        auth_config = self._get_config()
        for id, entry in auth_config.items():
            entry_user = entry.get('user', '')
            if username == entry_user:
                assert entry.get('id', id) == id
                copy = entry.copy()
                copy['id'] = id
                return copy
        return None

    def query(self, query: dict) -> Optional[AuthenticationEntry]:
        if not query:
            return None

        config = self._get_config()
        entry = None
        count = 0
        id = query.get('id')
        if id is not None:
            entry = config.get(id).copy()
            assert entry.get('id', id) == id
            entry['id'] = id
            count += 1

        username = query.get('username')
        if username is not None:
            count += 1
            if not entry:
                entry = self.get_entry_by_username(username)
            elif entry.get('user') != username:
                raise ValueError("Inconsistent id and user in query {!r}".format(query))

        if len(query) > count:
            raise ValueError("Unsupported fields in query {!r}".format(query))
        return entry

    def check(
            self,
            authentication_entry: AuthenticationEntry,
            query: dict) -> bool:
        user = query.get('username')
        pw = query.get('password', '')
        entry_pw = authentication_entry.get('pw', '')
        entry_pw_salt = authentication_entry.get('pw_salt', '')
        entry_pw_type = authentication_entry.get('pw_type', '')
        request_hash = util_encrypt(pw.value, entry_pw_salt, entry_pw_type)
        return (
            user == authentication_entry.get('user') and
            secrets.compare_digest(request_hash, entry_pw))

    def _get_config(self) -> IniDbDict:
        if hasattr(self._config, '__call__'):
            return self._config()
        return self._config


class Authorization:
    def __init__(
            self,
            authentication_plugin_list: List[AuthenticationPlugin],
            check_authorization: Callable[[AuthenticationEntry], bool]
            ):
        self._authentication_plugins = authentication_plugin_list
        self._check_authorization = check_authorization

    def before_request(self):
        """A wrapper to check authorization

        Inverts `flask` `before_request` convention that requires explicit
        return value to signal an error. Require `SUCCESS` to protect
        against erroneous bare `return`.
        """
        result = self._check_authentication_and_authorization()
        if result is SUCCESS:
            return None
        elif result is None:
            raise RuntimeError('Internal error: got None, expected SUCCESS or any other value')
        # I do not think it is worth checking for `Result` or `HTTPException`
        return result

    def _check_authentication_and_authorization(self) -> Union[Literal[SUCCESS], Response, HTTPException]:
        authentication_entry = None
        try:
            authentication_entry = functools.reduce(
                lambda entry, plugin: plugin.check(entry),
                self._authentication_plugins, None)
        except Exception as exc:
            response = self._call_authentication_error_hook(exc)
            if response:
                return response
            logger.exception("authentication failed", exc_info=True)
            return Forbidden()

        if self._check_authorization(authentication_entry):
            response = functools.reduce(
                lambda response, plugin: plugin.on_success(authentication_entry, response),
                self._authentication_plugins,
                None)
            return SUCCESS if response is None else response

        response, exc = self._call_authorization_error_hook(AuthorizationFailed())
        if exc:
            # TODO handle exceptions in authentication and authorization error hooks
            # more consistently
            logger.warning("authorization failed: %s", exc)
            return Forbidden()
        return response or Forbidden()

    def _call_authentication_error_hook(self, exc):
        def on_authentication_error(
                value, plugin
                ) -> Tuple[Union[Response, HTTPException, None], Union[Exception, None]]:
            response, err = value
            # TODO consider error handlers as independent of authentication plugins
            try:
                return plugin.on_authentication_error(response, err)
            except Exception as err:
                return None, err

        response, exc = functools.reduce(on_authentication_error, self._authentication_plugins, (None, exc))
        if exc:
            raise exc
        return response

    def _call_authorization_error_hook(self, exc):
        def on_authorization_error(value, plugin):
            response, err = value
            try:
                return plugin.on_authorization_error(response, err)
            except Exception as err:
                return None, err

        return functools.reduce(on_authorization_error, self._authentication_plugins, (None, exc))


class WerkzeugSecretKeyPlugin:
    def workspace_init(self, path):
        # TODO should not be called on each startup.
        # TODO use os.O_EXCL, set mode to 0o600
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'rb') as f:
                session_key = f.read()
            assert len(session_key) >= 32
        except (FileNotFoundError, AssertionError):
            session_key = secrets.token_bytes(128)
            with open(path, 'wb') as f:
                f.write(session_key)
        self._session_key = session_key

    def app_config(self, config):
        config['SECRET_KEY'] = self._session_key
        del self._session_key
        config['SESSION_COOKIE_NAME'] = 'wsbsession'
        config['SESSION_COOKIE_SAMESITE'] = 'Lax'
