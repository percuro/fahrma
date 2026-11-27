"""Login through OIDC end to end against the in-process fake provider."""

import unittest
from datetime import timedelta
from unittest import mock

from app.config import ConfigError, get_oidc_settings, validate
from app.models.group import Membership
from app.models.invitation import PURPOSE_VERIFY_EMAIL, Invitation
from app.models.oidc_state import OidcLoginState
from app.models.user import NO_PASSWORD, OidcIdentity, User, UserSession
from app.services import oidc_service, setup_service
from app.services.auth_service import utcnow
from app.services.invitation_service import new_token
from app.services.oidc_client import OidcClient
from app.services.placeholders import new_placeholder
from tests.oidc_fake import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeProvider
from tests.support import PASSWORD, TEST_ORIGIN, ApiTestEnvironment, accept, token_of

OIDC_ENV = {"OIDC_ISSUER": ISSUER, "OIDC_CLIENT_ID": CLIENT_ID, "OIDC_CLIENT_SECRET": CLIENT_SECRET}


class OidcTestCase(unittest.TestCase):
    extra_env: dict[str, str] = {}

    def setUp(self):
        self.env = ApiTestEnvironment()
        self._oidc_env = mock.patch.dict("os.environ", {**OIDC_ENV, **self.extra_env})
        self._oidc_env.start()
        self.provider = FakeProvider()
        self.provider.add_user(
            "sub-anna", email="anna@example.org", email_verified=True, preferred_username="anna", name="Anna A."
        )
        self.provider.add_user("sub-ben", email="ben@example.org", preferred_username="ben")
        self.oidc_client = OidcClient(get_oidc_settings(), transport=self.provider)
        self._client = mock.patch.object(oidc_service, "client_for", lambda _settings: self.oidc_client)
        self._client.start()

    def tearDown(self):
        self._client.stop()
        self._oidc_env.stop()
        self.env.close()

    # --- Helpers ------------------------------------------------------------

    def start(self, client, path="/v1/auth/oidc/start", **body):
        response = client.post(path, json=body or {"purpose": "login"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["authorize_url"]

    def finish(self, client, url, subject, **auth) -> str:
        """Log in at the provider and come back; returns where the web app is sent (path#fragment)."""
        callback = self.provider.sign_in(url, subject, **auth)
        response = client.get("/v1/auth/oidc/callback", params=callback, follow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text)
        location = response.headers["location"]
        self.assertTrue(location.startswith(TEST_ORIGIN), location)
        return location[len(TEST_ORIGIN) :]

    def sign_in(self, client, subject, path="/v1/auth/oidc/start", **body) -> str:
        return self.finish(client, self.start(client, path, **body), subject)

    def guest(self):
        return self.env.client(username=None)

    def query(self, model, **filters):
        db = self.env.SessionLocal()
        try:
            return db.query(model).filter_by(**filters).all()
        finally:
            db.close()

    def link(self, username, subject):
        db = self.env.SessionLocal()
        try:
            user = db.query(User).filter_by(username=username).one()
            db.add(OidcIdentity(user_id=user.id, issuer=ISSUER, subject=subject))
            db.commit()
        finally:
            db.close()

    def assertCode(self, response, status, code):
        detail = response.json().get("detail", {})
        self.assertEqual((response.status_code, detail.get("code")), (status, code), response.text)


class OidcLoginTest(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.env.create_user("alex", role="admin")

    def test_meta_announces_oidc(self):
        with mock.patch.dict("os.environ", {"OIDC_LABEL": "Authelia"}):
            meta = self.guest().get("/v1/meta").json()
        self.assertEqual((meta["password_login"], meta["oidc"]), (True, {"label": "Authelia"}))

    def test_unknown_subject_has_no_account(self):
        self.assertEqual(self.sign_in(self.guest(), "sub-anna"), "/login#error=oidc_no_account")
        self.assertEqual(self.query(User, username="anna"), [])

    def test_link_then_log_in_with_the_provider(self):
        alex = self.env.client("alex")
        url = self.start(alex, purpose="link", password=PASSWORD, return_to="/profile")
        self.assertEqual(self.finish(alex, url, "sub-anna"), "/profile#oidc=linked")
        me = alex.get("/v1/auth/me").json()
        self.assertEqual((me["oidc"]["email"], me["has_password"]), ("anna@example.org", True))
        # An existing account keeps managing its own address
        self.assertIsNone(me["email"])

        guest = self.guest()
        self.assertEqual(self.sign_in(guest, "sub-anna"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "alex")
        sessions = guest.get("/v1/account/sessions").json()
        self.assertEqual([s["auth_method"] for s in sessions if s["current"]], ["oidc"])

    def test_link_needs_the_password(self):
        alex = self.env.client("alex")
        self.assertCode(alex.post("/v1/auth/oidc/start", json={"purpose": "link"}), 403, "wrong_password")
        self.link("alex", "sub-anna")
        response = alex.post("/v1/auth/oidc/start", json={"purpose": "link", "password": PASSWORD})
        self.assertCode(response, 409, "oidc_already_linked")

    def test_a_subject_links_only_one_account(self):
        self.link("alex", "sub-anna")
        self.env.create_user("sam")
        sam = self.env.client("sam")
        url = self.start(sam, purpose="link", password=PASSWORD)
        self.assertEqual(self.finish(sam, url, "sub-anna"), "/profile#error=oidc_already_linked")

    def test_state_is_bound_to_the_browser_and_used_once(self):
        url = self.start(self.guest(), purpose="login")
        callback = self.provider.sign_in(url, "sub-anna")
        # Another browser (no state cookie) cannot finish it
        other = self.guest()
        response = other.get("/v1/auth/oidc/callback", params=callback, follow_redirects=False)
        self.assertTrue(response.headers["location"].endswith("/login#error=oidc_state_invalid"))

        self.link("alex", "sub-anna")
        guest = self.guest()
        url = self.start(guest)
        callback = self.provider.sign_in(url, "sub-anna")
        first = guest.get("/v1/auth/oidc/callback", params=callback, follow_redirects=False)
        self.assertTrue(first.headers["location"].endswith("/"), first.headers["location"])
        guest.cookies.set(oidc_service.STATE_COOKIE_NAME, callback["state"], path="/v1/auth/oidc")
        again = guest.get("/v1/auth/oidc/callback", params=callback, follow_redirects=False)
        self.assertTrue(again.headers["location"].endswith("#error=oidc_state_invalid"))

    def test_state_cookie_flags(self):
        response = self.guest().post("/v1/auth/oidc/start", json={"purpose": "login"})
        cookie = response.headers["set-cookie"]
        self.assertIn("fahrma_oidc=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/v1/auth/oidc", cookie)
        self.assertIn("SameSite=lax", cookie)

    def test_expired_state(self):
        self.link("alex", "sub-anna")
        guest = self.guest()
        url = self.start(guest)
        db = self.env.SessionLocal()
        try:
            db.query(OidcLoginState).update({"expires_at": utcnow() - timedelta(seconds=1)})
            db.commit()
        finally:
            db.close()
        self.assertEqual(self.finish(guest, url, "sub-anna"), "/login#error=oidc_state_invalid")

    def test_denied_at_the_provider(self):
        guest = self.guest()
        url = self.start(guest)
        state = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))["state"]
        response = guest.get(
            "/v1/auth/oidc/callback", params={"state": state, "error": "access_denied"}, follow_redirects=False
        )
        self.assertTrue(response.headers["location"].endswith("/login#error=oidc_denied"))

    def test_deactivated_account(self):
        self.link("alex", "sub-anna")
        db = self.env.SessionLocal()
        try:
            db.query(User).filter_by(username="alex").update({"is_active": False})
            db.commit()
        finally:
            db.close()
        self.assertEqual(self.sign_in(self.guest(), "sub-anna"), "/login#error=account_disabled")

    def test_provider_down(self):
        self.provider.down = True
        response = self.guest().post("/v1/auth/oidc/start", json={"purpose": "login"})
        self.assertCode(response, 503, "oidc_provider_unavailable")

    def test_return_to_only_known_pages(self):
        self.link("alex", "sub-anna")
        alex = self.env.client("alex")
        url = self.start(alex, purpose="reauth", return_to="https://evil.example/")
        self.assertEqual(self.finish(alex, url, "sub-anna", auth_time=None), "/profile#reauth=ok")

    def test_unlink_needs_a_password_left(self):
        self.link("alex", "sub-anna")
        alex = self.env.client("alex")
        self.assertCode(alex.request("DELETE", "/v1/account/oidc", json={}), 403, "wrong_password")
        response = alex.request("DELETE", "/v1/account/oidc", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.query(OidcIdentity), [])
        self.assertIsNone(alex.get("/v1/auth/me").json()["oidc"])

    def test_admin_unlinks_and_logs_out(self):
        self.env.create_user("sam")
        self.link("sam", "sub-ben")
        sam = self.guest()
        self.assertEqual(self.sign_in(sam, "sub-ben"), "/")
        users = {u["username"]: u for u in self.env.client("alex").get("/v1/admin/users").json()}
        self.assertTrue(users["sam"]["oidc_linked"])
        response = self.env.client("alex").delete(f"/v1/admin/users/{users['sam']['id']}/oidc")
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(sam.get("/v1/auth/me").status_code, 401)
        self.assertEqual(self.sign_in(self.guest(), "sub-ben"), "/login#error=oidc_no_account")

    def test_deleted_account_cannot_log_in_again(self):
        self.env.create_user("sam")
        self.link("sam", "sub-ben")
        sam = self.env.client("sam")
        response = sam.request("DELETE", "/v1/account", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.query(OidcIdentity), [])
        self.assertEqual(self.sign_in(self.guest(), "sub-ben"), "/login#error=oidc_no_account")


class OidcInvitationTest(OidcTestCase):
    def setUp(self):
        super().setUp()
        self.env.create_user("alex", display_name="Alex", role="admin")
        self.alex = self.env.client("alex")
        self.gid = self.alex.post("/v1/groups", json={"name": "Test group"}).json()["id"]

    def group_link(self, **body):
        return self.alex.post(f"/v1/groups/{self.gid}/invites", json=body or None).json()["url"]

    def test_group_link_creates_an_account_without_password(self):
        url = self.group_link()
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(url), username="anna", display_name="Anna")
        self.assertEqual(self.finish(guest, start, "sub-anna"), f"/g/{self.gid}")
        me = guest.get("/v1/auth/me").json()
        self.assertEqual((me["username"], me["display_name"], me["has_password"]), ("anna", "Anna", False))
        # The provider confirmed the address
        self.assertEqual(me["email"], "anna@example.org")
        self.assertEqual([g["id"] for g in me["groups"]], [self.gid])
        user = self.query(User, username="anna")[0]
        self.assertEqual(user.password_hash, NO_PASSWORD)
        # The link is used up
        self.assertCode(accept(self.guest(), url, username="ben", password=PASSWORD), 404, "invite_invalid")
        # Logging in again needs no password
        self.assertEqual(self.sign_in(self.guest(), "sub-anna"), "/")

    def test_unconfirmed_address_is_not_taken(self):
        self.provider.add_user("sub-carla", email="carla@example.org", preferred_username="carla", email_verified=False)
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(self.group_link()), username="carla")
        self.finish(guest, start, "sub-carla")
        self.assertIsNone(guest.get("/v1/auth/me").json()["email"])

    def test_username_is_checked_before_the_redirect(self):
        token = token_of(self.group_link())
        response = self.guest().post("/v1/invites/oidc", json={"token": token, "username": "alex"})
        self.assertCode(response, 409, "username_taken")
        response = self.guest().post("/v1/invites/oidc", json={"token": token, "username": "A"})
        self.assertCode(response, 422, "username_invalid")

    def test_linked_subject_does_not_use_up_the_link(self):
        self.link("alex", "sub-anna")
        url = self.group_link()
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(url), username="anna")
        self.assertEqual(self.finish(guest, start, "sub-anna"), "/login#error=oidc_already_linked")
        response = accept(self.guest(), url, username="ben", password=PASSWORD)
        self.assertEqual(response.status_code, 200, response.text)

    def test_personal_link_takes_over_the_placeholder(self):
        db = self.env.SessionLocal()
        try:
            placeholder = new_placeholder(db, "Sam")
            db.add(Membership(group_id=self.gid, user_id=placeholder.id))
            db.commit()
            placeholder_id = placeholder.id
        finally:
            db.close()
        url = self.alex.post(f"/v1/groups/{self.gid}/members/{placeholder_id}/invite").json()["url"]
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(url), username="samuel")
        self.assertEqual(self.finish(guest, start, "sub-ben"), f"/g/{self.gid}")
        me = guest.get("/v1/auth/me").json()
        self.assertEqual((me["id"], me["username"], me["display_name"]), (placeholder_id, "samuel", "Sam"))
        self.assertFalse(me["has_password"])

    def test_instance_invitation(self):
        url = self.alex.post("/v1/admin/invitations", json={"role": "user"}).json()["url"]
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(url), username="anna")
        self.assertEqual(self.finish(guest, start, "sub-anna"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "anna")

    def test_password_reset_link_links_the_account(self):
        self.env.create_user("sam")
        sam = self.env.client("sam")
        users = {u["username"]: u for u in self.alex.get("/v1/admin/users").json()}
        url = self.alex.post(f"/v1/admin/users/{users['sam']['id']}/password-reset").json()["url"]
        guest = self.guest()
        start = self.start(guest, "/v1/invites/oidc", token=token_of(url))
        self.assertEqual(self.finish(guest, start, "sub-ben"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "sam")
        # Every other device is logged out
        self.assertEqual(sam.get("/v1/auth/me").status_code, 401)
        self.assertEqual(len(self.query(OidcIdentity, subject="sub-ben")), 1)

    def test_confirmation_links_are_not_for_the_provider(self):
        db = self.env.SessionLocal()
        try:
            token, token_hash = new_token()
            user = db.query(User).filter_by(username="alex").one()
            db.add(
                Invitation(
                    purpose=PURPOSE_VERIFY_EMAIL,
                    token_hash=token_hash,
                    email="alex@example.org",
                    target_user_id=user.id,
                    expires_at=utcnow() + timedelta(days=1),
                )
            )
            db.commit()
        finally:
            db.close()
        response = self.guest().post("/v1/invites/oidc", json={"token": token})
        self.assertCode(response, 409, "oidc_not_for_link")


class OidcRegisterTest(OidcTestCase):
    extra_env = {"REGISTRATION": "open"}

    def setUp(self):
        super().setUp()
        self.env.create_user("alex", role="admin")

    def test_register_with_the_provider(self):
        guest = self.guest()
        self.assertEqual(self.sign_in(guest, "sub-anna", purpose="register", locale="en"), "/")
        me = guest.get("/v1/auth/me").json()
        self.assertEqual((me["username"], me["display_name"], me["locale"]), ("anna", "Anna A.", "en"))
        self.assertFalse(me["has_password"])

    def test_chosen_username_and_taken_ones(self):
        self.assertCode(
            self.guest().post("/v1/auth/oidc/start", json={"purpose": "register", "username": "alex"}),
            409,
            "username_taken",
        )
        self.env.create_user("anna")
        guest = self.guest()
        self.assertEqual(self.sign_in(guest, "sub-anna", purpose="register"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "anna-2")

    def test_terms_must_be_accepted(self):
        with mock.patch.dict("os.environ", {"TERMS_URL": "https://example.org/terms"}):
            response = self.guest().post("/v1/auth/oidc/start", json={"purpose": "register"})
            self.assertCode(response, 422, "terms_not_accepted")
            self.assertEqual(self.sign_in(self.guest(), "sub-anna", purpose="register", accept_terms=True), "/")

    def test_closed_registration(self):
        with mock.patch.dict("os.environ", {"REGISTRATION": "invite"}):
            response = self.guest().post("/v1/auth/oidc/start", json={"purpose": "register"})
        self.assertCode(response, 403, "registration_closed")

    def test_registered_subject_just_logs_in(self):
        self.link("alex", "sub-anna")
        guest = self.guest()
        self.assertEqual(self.sign_in(guest, "sub-anna", purpose="register"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "alex")


class AutoCreateTest(OidcTestCase):
    extra_env = {"OIDC_AUTO_CREATE": "on"}

    def test_first_login_creates_the_account(self):
        self.env.create_user("alex", role="admin")
        guest = self.guest()
        self.assertEqual(self.sign_in(guest, "sub-anna"), "/")
        self.assertEqual(guest.get("/v1/auth/me").json()["username"], "anna")

    def test_not_before_setup(self):
        self.assertEqual(self.sign_in(self.guest(), "sub-anna"), "/login#error=setup_required")

    def test_refused_together_with_terms(self):
        with mock.patch.dict("os.environ", {"TERMS_URL": "https://example.org/terms"}):
            with self.assertRaises(ConfigError):
                validate()


class OidcSetupTest(OidcTestCase):
    def test_setup_through_the_provider(self):
        token = setup_service.issue_token()
        guest = self.guest()
        url = self.start(guest, "/v1/setup/oidc", token=token, username="anna", display_name="Anna")
        self.assertEqual(self.finish(guest, url, "sub-anna"), "/")
        me = guest.get("/v1/auth/me").json()
        self.assertEqual((me["username"], me["role"], me["has_password"]), ("anna", "admin", False))
        self.assertFalse(setup_service.needs_setup(self.env.SessionLocal()))

    def test_wrong_token(self):
        setup_service.issue_token()
        response = self.guest().post("/v1/setup/oidc", json={"token": "wrong", "username": "anna"})
        self.assertCode(response, 403, "setup_token_invalid")


class PasswordlessAccountTest(OidcTestCase):
    """An account that only logs in through the provider confirms changes there."""

    def setUp(self):
        super().setUp()
        self.env.create_user("alex", role="admin")
        url = self.env.client("alex").post("/v1/admin/invitations", json={"role": "user"}).json()["url"]
        self.anna = self.guest()
        start = self.start(self.anna, "/v1/invites/oidc", token=token_of(url), username="anna")
        self.finish(self.anna, start, "sub-anna")

    def age_sessions(self, minutes):
        db = self.env.SessionLocal()
        try:
            db.query(UserSession).update({"authenticated_at": utcnow() - timedelta(minutes=minutes)})
            db.commit()
        finally:
            db.close()

    def test_fresh_login_confirms(self):
        response = self.anna.request("DELETE", "/v1/account/email", json={})
        self.assertEqual(response.status_code, 204, response.text)

    def test_old_login_needs_reauth(self):
        self.age_sessions(11)
        self.assertCode(self.anna.request("DELETE", "/v1/account/email", json={}), 403, "reauth_required")
        url = self.start(self.anna, purpose="reauth", return_to="/profile")
        self.assertEqual(self.finish(self.anna, url, "sub-anna"), "/profile#reauth=ok")
        self.assertEqual(self.anna.request("DELETE", "/v1/account/email", json={}).status_code, 204)

    def test_reauth_must_be_the_same_subject(self):
        url = self.start(self.anna, purpose="reauth")
        self.assertEqual(self.finish(self.anna, url, "sub-ben"), "/profile#error=oidc_wrong_account")

    def test_reauth_needs_a_new_login_at_the_provider(self):
        url = self.start(self.anna, purpose="reauth")
        callback = self.provider.sign_in(url, "sub-anna", auth_time=0)
        response = self.anna.get("/v1/auth/oidc/callback", params=callback, follow_redirects=False)
        self.assertTrue(response.headers["location"].endswith("/profile#error=oidc_reauth_failed"))

    def test_set_a_first_password(self):
        response = self.anna.post("/v1/account/password", json={"new_password": PASSWORD})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertTrue(self.anna.get("/v1/auth/me").json()["has_password"])
        self.assertEqual(self.env.client("anna").get("/v1/auth/me").status_code, 200)

    def test_cannot_unlink_without_a_password(self):
        self.assertCode(self.anna.request("DELETE", "/v1/account/oidc", json={}), 409, "last_login_method")

    def test_delete_the_account(self):
        self.age_sessions(30)
        self.assertCode(self.anna.request("DELETE", "/v1/account", json={}), 403, "reauth_required")
        self.age_sessions(0)
        self.assertEqual(self.anna.request("DELETE", "/v1/account", json={}).status_code, 204)

    def test_password_login_never_works(self):
        response = self.guest().post("/v1/auth/login", json={"username": "anna", "password": NO_PASSWORD})
        self.assertCode(response, 401, "invalid_credentials")


class RemovePasswordTest(OidcTestCase):
    """A linked account can give up its password and then logs in with the provider only."""

    def setUp(self):
        super().setUp()
        self.env.create_user("alex", role="admin")
        self.env.create_user("sam")
        self.link("sam", "sub-ben")
        self.sam = self.env.client("sam")

    def remove(self, client):
        return client.request("DELETE", "/v1/account/password")

    def test_needs_a_fresh_login_at_the_provider(self):
        # Logged in with the password: first confirm at the provider
        self.assertCode(self.remove(self.sam), 403, "reauth_required")
        url = self.start(self.sam, purpose="reauth", return_to="/profile")
        self.assertEqual(self.finish(self.sam, url, "sub-ben"), "/profile#reauth=ok")
        other_device = self.env.client("sam")
        self.assertEqual(self.remove(self.sam).status_code, 204)
        me = self.sam.get("/v1/auth/me").json()
        self.assertFalse(me["has_password"])
        # The password no longer works, other devices are logged out, this one stays
        response = self.guest().post("/v1/auth/login", json={"username": "sam", "password": PASSWORD})
        self.assertCode(response, 401, "invalid_credentials")
        self.assertEqual(other_device.get("/v1/auth/me").status_code, 401)
        self.assertEqual(self.sign_in(self.guest(), "sub-ben"), "/")
        # Cannot unlink now, and removing again says so
        self.assertCode(self.sam.request("DELETE", "/v1/account/oidc", json={}), 409, "last_login_method")
        self.assertCode(self.remove(self.sam), 409, "no_password")

    def test_only_for_linked_accounts(self):
        alex = self.env.client("alex")
        self.assertCode(self.remove(alex), 409, "oidc_not_linked")
        with mock.patch.dict("os.environ", {"OIDC_ISSUER": ""}):
            self.assertCode(self.remove(self.sam), 409, "oidc_not_linked")

    def test_no_password_reset_by_mail_afterwards(self):
        from tests.test_mail import MailOutbox

        outbox = MailOutbox()
        try:
            db = self.env.SessionLocal()
            try:
                db.query(User).filter_by(username="sam").update({"email": "sam@example.org"})
                db.commit()
            finally:
                db.close()
            response = self.guest().post("/v1/auth/forgot-password", json={"login": "sam"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(len(outbox.messages()), 1)
            url = self.start(self.sam, purpose="reauth")
            self.finish(self.sam, url, "sub-ben")
            self.assertEqual(self.remove(self.sam).status_code, 204)
            response = self.guest().post("/v1/auth/forgot-password", json={"login": "sam"})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(len(outbox.messages()), 1)
            # An instance admin can still create a link (the way back)
            users = {u["username"]: u for u in self.env.client("alex").get("/v1/admin/users").json()}
            response = self.env.client("alex").post(f"/v1/admin/users/{users['sam']['id']}/password-reset")
            self.assertEqual(response.status_code, 201, response.text)
        finally:
            outbox.close()


class PasswordLoginOffTest(OidcTestCase):
    extra_env = {"PASSWORD_LOGIN": "off", "REGISTRATION": "open"}

    def test_passwords_are_refused(self):
        self.env.create_user("alex", role="admin")
        guest = self.guest()
        self.assertCode(
            guest.post("/v1/auth/login", json={"username": "alex", "password": PASSWORD}),
            403,
            "password_login_disabled",
        )
        response = guest.post("/v1/auth/register", json={"username": "anna", "password": PASSWORD})
        self.assertCode(response, 403, "password_login_disabled")
        self.assertCode(guest.post("/v1/auth/forgot-password", json={"login": "alex"}), 403, "password_login_disabled")
        self.assertFalse(guest.get("/v1/meta").json()["password_login"])

    def test_start_refused_without_oidc(self):
        with mock.patch.dict("os.environ", {"OIDC_ISSUER": ""}):
            with self.assertRaises(ConfigError):
                validate()


class OidcDisabledTest(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()

    def tearDown(self):
        self.env.close()

    def test_everything_is_404(self):
        guest = self.env.client(None)
        response = guest.post("/v1/auth/oidc/start", json={"purpose": "login"})
        self.assertEqual((response.status_code, response.json()["detail"]["code"]), (404, "oidc_disabled"))
        self.assertIsNone(guest.get("/v1/meta").json()["oidc"])


if __name__ == "__main__":
    unittest.main()
