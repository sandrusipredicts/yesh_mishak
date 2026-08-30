from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class PasswordResetEmail:
    subject: str
    html_body: str
    text_body: str


def build_password_reset_email(
    reset_url: str,
    expires_in_minutes: int,
    *,
    business_name: str,
) -> PasswordResetEmail:
    escaped_url = escape(reset_url, quote=True)
    escaped_business_name = escape(business_name)
    subject = f"Reset your {business_name} password / איפוס סיסמה ב-{business_name}"
    text_body = f"""Reset your {business_name} password

Use this link to choose a new password:
{reset_url}

This link expires in {expires_in_minutes} minutes.
If you did not request this, you can ignore this email.

איפוס סיסמה ב-{business_name}

כדי לבחור סיסמה חדשה, יש לפתוח את הקישור:
{reset_url}

הקישור יפוג בעוד {expires_in_minutes} דקות.
אם לא ביקשת איפוס סיסמה, אפשר להתעלם מההודעה.
"""
    html_body = f"""<!doctype html>
<html lang="en">
  <body>
    <h1>Reset your {escaped_business_name} password</h1>
    <p>Use the link below to choose a new password.</p>
    <p><a href="{escaped_url}">Reset password</a></p>
    <p>This link expires in {expires_in_minutes} minutes.</p>
    <p>If you did not request this, you can ignore this email.</p>
    <hr>
    <div dir="rtl" lang="he">
      <h1>איפוס סיסמה ב-{escaped_business_name}</h1>
      <p>כדי לבחור סיסמה חדשה, יש לפתוח את הקישור הבא.</p>
      <p><a href="{escaped_url}">איפוס סיסמה</a></p>
      <p>הקישור יפוג בעוד {expires_in_minutes} דקות.</p>
      <p>אם לא ביקשת איפוס סיסמה, אפשר להתעלם מההודעה.</p>
    </div>
  </body>
</html>"""
    return PasswordResetEmail(subject=subject, html_body=html_body, text_body=text_body)
