"""E-mail: configuration, address confirmation, forgotten password, registration, links by mail."""

import re
import tempfile
import unittest
from email import message_from_bytes, policy
from pathlib import Path
from unittest import mock

from app import config
from app.services import mail
from tests.support import PASSWORD, ApiTestEnvironment, accept
from tests.test_accounts import code
from tests.test_api import GroupSetupMixin

LINK = re.compile(r"http://localhost:5173/invite#[A-Za-z0-9_-]+")


class MailOutbox:
    """Turns e-mail on with MAIL_DIR; every mail lands as a file the test can read."""

    def __init__(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(
            "os.environ", {"MAIL_FROM": "fahrma <noreply@example.org>", "MAIL_DIR": self.directory.name}
        )
        self.env.start()

    def messages(self):
        return [
            message_from_bytes(path.read_bytes(), policy=policy.default)
            for path in sorted(Path(self.directory.name).glob("*.eml"))
        ]

    def last(self):
        messages = self.messages()
        assert messages, "no mail was sent"
        return messages[-1]

    @staticmethod
    def body(message) -> str:
        return message.get_content()

    def link(self, message=None) -> str:
        match = LINK.search(self.body(message or self.last()))
        assert match, self.body(message or self.last())
        return match.group(0)

    def close(self):
        self.env.stop()
        self.directory.cleanup()


class MailTestMixin(GroupSetupMixin):
    def setUp(self):
        super().setUp()
        self.outbox = MailOutbox()

    def tearDown(self):
        self.outbox.close()
        super().tearDown()

    def set_email(self, client, address="alex@example.org"):
        response = client.post("/v1/account/email", json={"email": address, "password": PASSWORD})
        self.assertEqual(response.status_code, 202, response.text)
        response = accept(self.env.client(None), self.outbox.link())
        self.assertEqual(response.json(), {"kind": "verify_email", "group_id": None})


class ConfigTests(unittest.TestCase):
    def settings(self, **env):
        base = {"MAIL_FROM": "", "SMTP_HOST": "", "MAIL_DIR": "", "SMTP_PORT": "", "SMTP_SECURITY": ""}
        with mock.patch.dict("os.environ", {**base, **env}):
            return config.get_mail_settings()

    def test_off_by_default(self):
        self.assertIsNone(self.settings())

    def test_needs_sender_and_server(self):
        with self.assertRaises(config.ConfigError):
            self.settings(SMTP_HOST="mail.example.org")
        with self.assertRaises(config.ConfigError):
            self.settings(MAIL_FROM="noreply@example.org")
        with self.assertRaises(config.ConfigError):
            self.settings(MAIL_FROM="not an address", SMTP_HOST="mail.example.org")
        with self.assertRaises(config.ConfigError):
            self.settings(MAIL_FROM="noreply@example.org", SMTP_HOST="mail.example.org", SMTP_SECURITY="ssl")

    def test_ports_follow_the_security(self):
        sender = {"MAIL_FROM": "fahrma <noreply@example.org>", "SMTP_HOST": "mail.example.org"}
        self.assertEqual(self.settings(**sender).port, 587)
        self.assertEqual(self.settings(**sender, SMTP_SECURITY="tls").port, 465)
        self.assertEqual(self.settings(**sender, SMTP_PORT="2525").port, 2525)

    def test_password_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as handle:
            handle.write("secret\n")
            handle.flush()
            settings = self.settings(
                MAIL_FROM="noreply@example.org", SMTP_HOST="mail.example.org", SMTP_PASSWORD_FILE=handle.name
            )
        self.assertEqual(settings.password, "secret")

    def test_smtp_with_starttls_and_login(self):
        env = {
            "MAIL_FROM": "fahrma <noreply@example.org>",
            "SMTP_HOST": "mail.example.org",
            "SMTP_USERNAME": "fahrma",
            "SMTP_PASSWORD": "secret",
            "MAIL_DIR": "",
        }
        with mock.patch.dict("os.environ", env), mock.patch("smtplib.SMTP") as smtp:
            mail.deliver(mail.Mail(to="kim@example.org", subject="Hello", body="Text"))
        client = smtp.return_value
        smtp.assert_called_once_with("mail.example.org", 587, timeout=mail.SMTP_TIMEOUT_SECONDS)
        client.starttls.assert_called_once()
        client.login.assert_called_once_with("fahrma", "secret")
        sent = client.send_message.call_args.args[0]
        self.assertEqual(
            (sent["To"], sent["Subject"], sent["Auto-Submitted"]), ("kim@example.org", "Hello", "auto-generated")
        )

    def test_failure_is_logged_not_raised(self):
        env = {"MAIL_FROM": "noreply@example.org", "SMTP_HOST": "mail.example.org", "MAIL_DIR": ""}
        with mock.patch.dict("os.environ", env), mock.patch("smtplib.SMTP", side_effect=OSError("refused")):
            with self.assertLogs("app.services.mail", "ERROR") as logs:
                mail.deliver(mail.Mail(to="kim@example.org", subject="Hello", body="Text"))
        self.assertNotIn("kim@example.org", "\n".join(logs.output))


class EmailAddressTests(MailTestMixin, unittest.TestCase):
    def test_meta_says_mail_is_on(self):
        self.assertTrue(self.env.client(None).get("/v1/meta").json()["mail"])
        self.outbox.env.stop()
        self.assertFalse(self.env.client(None).get("/v1/meta").json()["mail"])
        self.outbox.env.start()

    def test_confirm_an_address(self):
        response = self.alex.post("/v1/account/email", json={"email": "alex@example.org", "password": "wrong-password"})
        self.assertEqual(code(response, 403), "wrong_password")
        response = self.alex.post("/v1/account/email", json={"email": " Alex@Example.org ", "password": PASSWORD})
        self.assertEqual(response.status_code, 202, response.text)
        message = self.outbox.last()
        self.assertEqual(message["To"], "alex@example.org")
        self.assertIn("alex", self.outbox.body(message))
        me = self.alex.get("/v1/auth/me").json()
        self.assertEqual((me["email"], me["email_pending"]), (None, "alex@example.org"))
        info = self.env.client(None).post("/v1/invites/inspect", json={"token": self.outbox.link().split("#")[1]})
        self.assertEqual((info.json()["kind"], info.json()["email"]), ("verify_email", "alex@example.org"))
        accept(self.env.client(None), self.outbox.link())
        me = self.alex.get("/v1/auth/me").json()
        self.assertEqual((me["email"], me["email_pending"]), ("alex@example.org", None))

    def test_change_notifies_the_old_address(self):
        self.set_email(self.alex)
        self.set_email(self.alex, "alex@new.example.org")
        notice = self.outbox.messages()[-1]
        self.assertEqual(notice["To"], "alex@example.org")
        self.assertEqual(self.alex.get("/v1/auth/me").json()["email"], "alex@new.example.org")

    def test_address_of_another_account(self):
        self.set_email(self.alex)
        self.sam.post("/v1/account/email", json={"email": "alex@example.org", "password": PASSWORD})
        self.assertEqual(code(accept(self.env.client(None), self.outbox.link()), 409), "email_taken")

    def test_cancel_and_remove(self):
        self.sam.post("/v1/account/email", json={"email": "sam@example.org", "password": PASSWORD})
        self.assertEqual(self.sam.delete("/v1/account/email/pending").status_code, 204)
        self.assertEqual(code(accept(self.env.client(None), self.outbox.link()), 404), "invite_invalid")
        self.set_email(self.sam, "sam@example.org")
        response = self.sam.request("DELETE", "/v1/account/email", json={"password": PASSWORD})
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.sam.get("/v1/auth/me").json()["email"])

    def test_rejects_header_injection(self):
        response = self.alex.post(
            "/v1/account/email", json={"email": "a@example.org\nBcc: b@example.org", "password": PASSWORD}
        )
        self.assertEqual(response.status_code, 422)

    def test_mail_quota_per_account(self):
        for _ in range(20):
            self.alex.post(f"{self.base}/invites", json={"email": "kim@example.org"})
        response = self.alex.post(f"{self.base}/invites", json={"email": "kim@example.org"})
        self.assertEqual(code(response, 429), "too_many_attempts")


class ForgotPasswordTests(MailTestMixin, unittest.TestCase):
    def forgot(self, login):
        response = self.env.client(None).post("/v1/auth/forgot-password", json={"login": login})
        self.assertEqual(response.status_code, 202, response.text)

    def test_same_answer_without_mail(self):
        self.forgot("nobody")
        self.forgot("sam")  # no address
        self.assertEqual(self.outbox.messages(), [])

    def test_reset_by_mail(self):
        self.set_email(self.sam, "sam@example.org")
        sent = len(self.outbox.messages())
        self.forgot("SAM@example.org")
        self.forgot("sam")
        self.assertEqual(len(self.outbox.messages()), sent + 2)
        first, second = self.outbox.messages()[-2:]
        self.assertEqual(second["To"], "sam@example.org")
        # Only the newest link works
        self.assertEqual(code(accept(self.env.client(None), self.outbox.link(first), password="x" * 12), 404),
                         "invite_invalid")  # fmt: skip
        new_password = "ein-ganz-neues-passwort"
        browser = self.env.client(None)
        self.assertEqual(accept(browser, self.outbox.link(second), password=new_password).status_code, 200)
        self.assertEqual(browser.get("/v1/auth/me").json()["username"], "sam")
        self.assertEqual(self.sam.get("/v1/auth/me").status_code, 401)

    def test_at_most_three_mails_per_hour(self):
        self.set_email(self.sam, "sam@example.org")
        sent = len(self.outbox.messages())
        for _ in range(5):
            self.forgot("sam")
        self.assertEqual(len(self.outbox.messages()), sent + 3)

    def test_needs_mail(self):
        self.outbox.env.stop()
        response = self.env.client(None).post("/v1/auth/forgot-password", json={"login": "sam"})
        self.outbox.env.start()
        self.assertEqual(code(response, 409), "mail_disabled")

    def test_admin_sends_a_reset_link(self):
        response = self.alex.post(f"/v1/admin/users/{self.sam_id}/password-reset", json={"send_email": True})
        self.assertEqual(code(response, 409), "no_email")
        self.set_email(self.sam, "sam@example.org")
        response = self.alex.post(f"/v1/admin/users/{self.sam_id}/password-reset", json={"send_email": True})
        self.assertTrue(response.json()["email_sent"])
        self.assertEqual(self.outbox.last()["To"], "sam@example.org")
        self.assertEqual(self.outbox.link(), response.json()["url"])
        users = {u["username"]: u for u in self.alex.get("/v1/admin/users").json()}
        self.assertEqual(users["sam"]["email"], "sam@example.org")


class LinksByMailTests(MailTestMixin, unittest.TestCase):
    def test_group_invite(self):
        response = self.alex.post(f"{self.base}/invites", json={"email": "kim@example.org"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["email_sent"])
        message = self.outbox.last()
        self.assertEqual(message["To"], "kim@example.org")
        self.assertIn("Test group", message["Subject"])
        self.assertIn("Alex", self.outbox.body(message))
        browser = self.env.client(None)
        accept(browser, self.outbox.link(), username="kim", password=PASSWORD)
        # The link came to this address, so it is the confirmed address of the new account
        self.assertEqual(browser.get("/v1/auth/me").json()["email"], "kim@example.org")

    def test_language_of_the_inviter(self):
        self.alex.patch("/v1/auth/me", json={"locale": "de"})
        self.alex.post(f"{self.base}/invites", json={"email": "kim@example.org"})
        self.assertIn("Einladung", self.outbox.last()["Subject"])

    def test_personal_invite(self):
        group = self.alex.post(f"{self.base}/members", json={"display_name": "Grandma"}).json()
        grandma = next(m["user_id"] for m in group["members"] if m["display_name"] == "Grandma")
        response = self.alex.post(f"{self.base}/members/{grandma}/invite", json={"email": "oma@example.org"})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("Grandma", self.outbox.body(self.outbox.last()))

    def test_admin_signup_invite(self):
        response = self.alex.post("/v1/admin/invitations", json={"email": "kim@example.org", "note": "Kim"})
        self.assertTrue(response.json()["email_sent"])
        self.assertEqual(self.alex.get("/v1/admin/invitations").json()[0]["email"], "kim@example.org")
        browser = self.env.client(None)
        accept(browser, self.outbox.link(), username="kim", password=PASSWORD)
        self.assertEqual(browser.get("/v1/auth/me").json()["email"], "kim@example.org")

    def test_email_needs_mail(self):
        self.outbox.env.stop()
        response = self.alex.post(f"{self.base}/invites", json={"email": "kim@example.org"})
        self.outbox.env.start()
        self.assertEqual(code(response, 409), "mail_disabled")
        self.assertEqual(self.alex.post(f"{self.base}/invites").status_code, 201)


class RegistrationWithMailTests(unittest.TestCase):
    def setUp(self):
        self.env = ApiTestEnvironment()
        self.env.create_user("alex", role="admin")
        self.outbox = MailOutbox()
        self.open = mock.patch.dict("os.environ", {"REGISTRATION": "open"})
        self.open.start()

    def tearDown(self):
        self.open.stop()
        self.outbox.close()
        self.env.close()

    def register(self, **fields):
        body = {"username": "kim", "password": PASSWORD, "email": "kim@example.org", "locale": "de", **fields}
        return self.env.client(None).post("/v1/auth/register", json=body)

    def test_account_follows_the_confirmation(self):
        self.assertEqual(code(self.register(email=None), 422), "email_required")
        response = self.register()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"email": "kim@example.org"})
        login = self.env.client(None).post("/v1/auth/login", json={"username": "kim", "password": PASSWORD})
        self.assertEqual(login.status_code, 401)
        message = self.outbox.last()
        self.assertIn("Registrierung", message["Subject"])
        browser = self.env.client(None)
        self.assertEqual(accept(browser, self.outbox.link()).json(), {"kind": "registration", "group_id": None})
        me = browser.get("/v1/auth/me").json()
        self.assertEqual((me["username"], me["email"], me["locale"]), ("kim", "kim@example.org", "de"))
        self.assertEqual(
            self.env.client(None).post("/v1/auth/login", json={"username": "kim", "password": PASSWORD}).status_code,
            200,
        )

    def test_known_address_gets_a_hint_instead(self):
        self.register()
        accept(self.env.client(None), self.outbox.link())
        response = self.register(username="kim2")
        self.assertEqual(response.status_code, 202)
        hint = self.outbox.last()
        self.assertIn("forgot-password", self.outbox.body(hint))
        self.assertIsNone(LINK.search(self.outbox.body(hint)))

    def test_username_taken_in_the_meantime(self):
        self.register()
        self.env.create_user("kim")
        self.assertEqual(code(accept(self.env.client(None), self.outbox.link()), 409), "username_taken")


if __name__ == "__main__":
    unittest.main()
