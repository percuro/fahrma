"""Texts of the e-mails, German and English.

Like the CSV export, a mail is something people keep, so it is written in the recipient's
language on the server. Everything else the interface shows lives in the frontend.
"""

from datetime import date, datetime, timedelta

from fastapi import Request

from app.config import APP_NAME, get_public_url
from app.services.auth_service import utcnow
from app.services.mail import Mail

LOCALES = ("de", "en")


def pick_locale(*candidates: str | None, request: Request | None = None) -> str:
    """The first known language of the candidates, else the browser's, else English."""
    for candidate in candidates:
        if candidate in LOCALES:
            return candidate
    if request is not None:
        for part in request.headers.get("Accept-Language", "").split(","):
            language = part.split(";")[0].strip().lower()[:2]
            if language in LOCALES:
                return language
    return "en"


def _validity(locale: str, expires_at: datetime) -> str:
    left = expires_at - utcnow()
    if left >= timedelta(days=2):
        days = round(left / timedelta(days=1))
        return f"{days} Tage" if locale == "de" else f"{days} days"
    hours = max(1, round(left / timedelta(hours=1)))
    if locale == "de":
        return "1 Stunde" if hours == 1 else f"{hours} Stunden"
    return "1 hour" if hours == 1 else f"{hours} hours"


def _footer(locale: str) -> str:
    if locale == "de":
        return f"\n\n-- \n{APP_NAME} · {get_public_url()}\nDiese Nachricht wurde automatisch verschickt."
    return f"\n\n-- \n{APP_NAME} · {get_public_url()}\nThis message was sent automatically."


def _mail(to: str, locale: str, subject: str, body: str) -> Mail:
    return Mail(to=to, subject=subject, body=body.strip() + _footer(locale))


def group_invite(
    to: str,
    locale: str,
    inviter: str,
    group_name: str,
    url: str,
    expires_at: datetime,
    member_name: str | None = None,
) -> Mail:
    valid = _validity(locale, expires_at)
    if locale == "de":
        as_whom = f" als „{member_name}“" if member_name else ""
        return _mail(
            to,
            locale,
            f"Einladung in die Gruppe „{group_name}“",
            f"""
Hallo,

{inviter} lädt dich{as_whom} in die Gruppe „{group_name}“ bei {APP_NAME} ein. Dort tragt ihr
eure Fahrten, Tankbelege und Kosten ein, und {APP_NAME} rechnet aus, wer wem wie viel schuldet.

Mit diesem Link trittst du bei (mit deinem Konto oder einem neuen):

{url}

Der Link gilt {valid} und funktioniert einmal.

Wenn du damit nichts anfangen kannst, ignoriere diese Nachricht einfach.
""",
        )
    as_whom = f" as “{member_name}”" if member_name else ""
    return _mail(
        to,
        locale,
        f"Invitation to the group “{group_name}”",
        f"""
Hello,

{inviter} invites you{as_whom} to the group “{group_name}” on {APP_NAME}. There you record
your trips, fuel receipts and costs, and {APP_NAME} works out who owes whom how much.

Use this link to join (with your account or a new one):

{url}

The link is valid for {valid} and works once.

If this means nothing to you, simply ignore this message.
""",
    )


def signup_invite(to: str, locale: str, inviter: str, url: str, expires_at: datetime) -> Mail:
    valid = _validity(locale, expires_at)
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Einladung zu {APP_NAME}",
            f"""
Hallo,

{inviter} lädt dich zu {APP_NAME} ein, einer App, mit der sich Leute die Kosten gemeinsam
genutzter Autos fair aufteilen.

Mit diesem Link legst du dein Konto an:

{url}

Der Link gilt {valid} und funktioniert einmal.

Wenn du damit nichts anfangen kannst, ignoriere diese Nachricht einfach.
""",
        )
    return _mail(
        to,
        locale,
        f"Invitation to {APP_NAME}",
        f"""
Hello,

{inviter} invites you to {APP_NAME}, an app for sharing the costs of shared cars fairly.

Use this link to create your account:

{url}

The link is valid for {valid} and works once.

If this means nothing to you, simply ignore this message.
""",
    )


def password_reset(to: str, locale: str, username: str, url: str, expires_at: datetime) -> Mail:
    valid = _validity(locale, expires_at)
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Neues Passwort für {APP_NAME}",
            f"""
Hallo,

für dein Konto „{username}“ wurde ein neues Passwort angefordert. Mit diesem Link legst du es fest:

{url}

Der Link gilt {valid} und funktioniert einmal. Danach meldet {APP_NAME} alle Geräte ab.

Wenn du kein neues Passwort angefordert hast, ignoriere diese Nachricht; dein Passwort
bleibt dann, wie es ist.
""",
        )
    return _mail(
        to,
        locale,
        f"New password for {APP_NAME}",
        f"""
Hello,

a new password was requested for your account “{username}”. Use this link to set it:

{url}

The link is valid for {valid} and works once. Afterwards {APP_NAME} logs out all devices.

If you did not ask for a new password, ignore this message; your password stays as it is.
""",
    )


def verify_email(to: str, locale: str, username: str, url: str, expires_at: datetime) -> Mail:
    valid = _validity(locale, expires_at)
    if locale == "de":
        return _mail(
            to,
            locale,
            f"E-Mail-Adresse für {APP_NAME} bestätigen",
            f"""
Hallo,

bitte bestätige, dass diese Adresse zu deinem Konto „{username}“ gehört:

{url}

Der Link gilt {valid}. Erst danach verwendet {APP_NAME} die Adresse, zum Beispiel wenn du
dein Passwort vergessen hast.

Wenn du die Adresse nicht eingetragen hast, ignoriere diese Nachricht.
""",
        )
    return _mail(
        to,
        locale,
        f"Confirm your e-mail address for {APP_NAME}",
        f"""
Hello,

please confirm that this address belongs to your account “{username}”:

{url}

The link is valid for {valid}. Only then does {APP_NAME} use the address, for example when
you forgot your password.

If you did not enter this address, ignore this message.
""",
    )


def registration(to: str, locale: str, username: str, url: str, expires_at: datetime) -> Mail:
    valid = _validity(locale, expires_at)
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Registrierung bei {APP_NAME} abschließen",
            f"""
Hallo,

mit diesem Link schließt du die Registrierung als „{username}“ ab:

{url}

Der Link gilt {valid}. Bis dahin ist das Konto nicht angelegt.

Wenn du dich nicht registriert hast, ignoriere diese Nachricht.
""",
        )
    return _mail(
        to,
        locale,
        f"Finish your registration with {APP_NAME}",
        f"""
Hello,

use this link to finish your registration as “{username}”:

{url}

The link is valid for {valid}. Until then the account does not exist.

If you did not register, ignore this message.
""",
    )


def registration_existing(to: str, locale: str, username: str) -> Mail:
    """Someone tried to register with an address that already has an account."""
    forgot = f"{get_public_url()}/forgot-password"
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Du hast schon ein Konto bei {APP_NAME}",
            f"""
Hallo,

gerade wollte sich jemand mit dieser Adresse neu registrieren. Zu ihr gehört aber schon dein
Konto „{username}“, deshalb wurde kein zweites angelegt.

Passwort vergessen? Hier bekommst du ein neues: {forgot}

Wenn du das nicht warst, ignoriere diese Nachricht; an deinem Konto hat sich nichts geändert.
""",
        )
    return _mail(
        to,
        locale,
        f"You already have an account with {APP_NAME}",
        f"""
Hello,

someone just tried to register with this address. It already belongs to your account
“{username}”, so no second account was created.

Forgot your password? Get a new one here: {forgot}

If this was not you, ignore this message; nothing changed in your account.
""",
    )


def email_changed(to: str, locale: str, username: str) -> Mail:
    """Notice to the previous address after a new one was confirmed."""
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Deine E-Mail-Adresse bei {APP_NAME} wurde geändert",
            f"""
Hallo,

für dein Konto „{username}“ gilt ab jetzt eine andere E-Mail-Adresse. Diese Adresse
bekommt keine Nachrichten von {APP_NAME} mehr.

Wenn du das nicht selbst geändert hast, melde dich bei den Admins deiner Instanz.
""",
        )
    return _mail(
        to,
        locale,
        f"Your e-mail address with {APP_NAME} was changed",
        f"""
Hello,

your account “{username}” uses a different e-mail address from now on. This address no
longer receives messages from {APP_NAME}.

If you did not change it yourself, contact the admins of your instance.
""",
    )


def inactive_warning(to: str, locale: str, username: str, months: int, last_seen: date, due: date) -> Mail:
    """INACTIVE_DELETE_MONTHS: the account will be deleted unless it is used again."""
    login = get_public_url()
    if locale == "de":
        return _mail(
            to,
            locale,
            f"Dein Zugang bei {APP_NAME} wird am {due:%d.%m.%Y} gelöscht",
            f"""
Hallo,

du hast deinen Zugang „{username}“ bei {APP_NAME} seit dem {last_seen:%d.%m.%Y} nicht mehr
benutzt. Damit keine Daten unnötig liegen bleiben, löscht diese Instanz Zugänge nach
{months} Monaten ohne Anmeldung.

Dein Zugang wird am {due:%d.%m.%Y} gelöscht. Wenn du ihn behalten willst, melde dich vorher
einfach an:

{login}

Was beim Löschen passiert: Deine Fahrten und Zahlungen bleiben in Fahrgemeinschaften mit
anderen Mitgliedern unter einem anonymen Namen erhalten, damit deren Abrechnungen stimmen.
Fahrgemeinschaften ohne weitere Mitglieder werden mit allen Einträgen gelöscht. Vorher
kannst du unter Profil → Meine Daten alles herunterladen.
""",
        )
    return _mail(
        to,
        locale,
        f"Your {APP_NAME} account will be deleted on {due:%Y-%m-%d}",
        f"""
Hello,

you have not used your account “{username}” with {APP_NAME} since {last_seen:%Y-%m-%d}. So
that no data is kept without need, this instance deletes accounts after {months} months
without a login.

Your account will be deleted on {due:%Y-%m-%d}. If you want to keep it, simply log in
before then:

{login}

What deleting means: your trips and payments stay in groups with other members under an
anonymous name, so that their settlements add up. Groups without other members are deleted
with all their entries. Before that, you can download everything under Profile → My data.
""",
    )
