import logging
import os
import uuid
from pathlib import Path
from dotenv import load_dotenv
from typing import Any

import resend

from dailydevfinds.config import get_config
from dailydevfinds.models import EmailContent
from dailydevfinds.state import add_posted

# Load .env file explicitly
load_dotenv()

logger = logging.getLogger(__name__)


async def send_email(
    post_text: str,
    reason: str,
    runner_ups: list[str],
    image_path: str | None,
    pick_name: str,
    dry_run: bool = False,
) -> bool:
    """Send the daily email with post, image, and runner-ups."""
    config = get_config()
    email_config = config.get("email", {})

    owner_email = email_config.get("owner") or os.getenv("OWNER_EMAIL")
    from_email = email_config.get("from") or os.getenv("FROM_EMAIL")

    if not owner_email or not from_email:
        logger.error("Email configuration missing: OWNER_EMAIL or FROM_EMAIL")
        return False

    # Build email content
    email_content = _build_email(post_text, reason, runner_ups, image_path, pick_name)

    if dry_run:
        logger.info("DRY RUN - Email content:")
        logger.info(f"Subject: {email_content.subject}")
        logger.info(f"Text body:\n{email_content.text_body}")
        logger.info(f"Runner-ups: {email_content.runner_ups_text}")
        return True

    try:
        # Send via Resend
        resend.api_key = os.getenv("RESEND_API_KEY") or email_config.get("api_key")

        params: dict[str, Any] = {
            "from": from_email,
            "to": [owner_email],
            "subject": email_content.subject,
            "html": email_content.html_body,
            "text": email_content.text_body,
        }

        if image_path and Path(image_path).exists():
            with open(image_path, "rb") as f:
                image_data = f.read()
            params["attachments"] = [{
                "filename": Path(image_path).name,
                "content": image_data,
            }]

        response = resend.Emails.send(params)  # type: ignore[arg-type]
        logger.info(f"Email sent successfully: {response.get('id')}")

        return True

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        await send_failure_email(str(e))
        return False


def _build_email(post_text: str, reason: str, runner_ups: list[str], image_path: str | None, pick_name: str) -> EmailContent:
    """Build email content with inline image."""
    cid = f"image_{uuid.uuid4().hex[:8]}@dailydevfinds"

    # Runner-ups text
    runner_ups_text = "\n".join([f"• {r}" for r in runner_ups]) if runner_ups else "None"

    # Plain text version
    text_body = f"""LinkedIn Post Ready

{post_text}

---

Why this was picked:
{reason}

Runner-ups:
{runner_ups_text}

---
DailyDevFinds - Automated daily developer resource discovery
"""

    # HTML version with inline image
    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <h2 style="color: #1a1a1a;">LinkedIn Post Ready</h2>

    <div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; border-left: 4px solid #2563eb;">
        <pre style="white-space: pre-wrap; font-family: inherit; margin: 0;">{post_text}</pre>
    </div>

    {f'<img src="cid:{cid}" alt="Preview image" style="max-width: 100%; height: auto; border-radius: 8px; margin: 20px 0;">' if image_path else ''}

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">

    <h3 style="color: #374151;">Why this was picked</h3>
    <p style="color: #4b5563;">{reason}</p>

    <h3 style="color: #374151;">Runner-ups</h3>
    <p style="color: #4b5563;">{runner_ups_text.replace(chr(10), '<br>')}</p>

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 30px 0;">
    <p style="color: #9ca3af; font-size: 12px;">DailyDevFinds - Automated daily developer resource discovery</p>
</body>
</html>"""

    return EmailContent(
        subject=f"LinkedIn Post Ready: {pick_name}",
        html_body=html_body,
        text_body=text_body,
        image_cid=cid,
        image_path=image_path or "",
        runner_ups_text=runner_ups_text,
        reason=reason,
    )


async def send_failure_email(error: str) -> None:
    """Send failure notification email."""
    try:
        config = get_config()
        email_config = config.get("email", {})
        owner_email = email_config.get("owner") or os.getenv("OWNER_EMAIL")
        from_email = email_config.get("from") or os.getenv("FROM_EMAIL")

        if not owner_email or not from_email:
            return

        resend.api_key = os.getenv("RESEND_API_KEY") or email_config.get("api_key")

        resend.Emails.send({
            "from": from_email,
            "to": [owner_email],
            "subject": "Agent failed: DailyDevFinds",
            "text": f"DailyDevFinds agent failed with error:\n\n{error}",
        })

    except Exception:
        pass  # Best effort


async def update_state(pick_url: str) -> None:
    """Update posted state after successful email."""
    add_posted(pick_url)
    logger.info(f"Updated state with: {pick_url}")
