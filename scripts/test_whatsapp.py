#!/usr/bin/env python3
"""
Quick script to test Twilio WhatsApp delivery to your phone.
Run from project root with: set -a && source envs/local.env && set +a && python scripts/test_whatsapp.py
Or: make test-whatsapp (if added to Makefile)
"""
import os
import sys

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.whatsapp_service import WhatsAppService, WhatsAppServiceError


def main() -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.environ.get("TWILIO_WHATSAPP_NUMBER", "").strip()
    to_num = os.environ.get("WHATSAPP_STATUS_RECIPIENT_DEFAULT", "").strip()

    if not all([sid, token, from_num, to_num]):
        print("Missing env vars. Source envs/local.env first.")
        print("  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER, WHATSAPP_STATUS_RECIPIENT_DEFAULT")
        sys.exit(1)

    svc = WhatsAppService(account_sid=sid, auth_token=token, from_number=from_num)
    try:
        msg_sid = svc.send_message(to_number=to_num, body="Test from notion_place_inserter. If you see this, WhatsApp is working.")
        print(f"Sent successfully. Twilio SID: {msg_sid}")
    except WhatsAppServiceError as e:
        print(f"Send failed: {e}")
        if e.cause:
            print(f"  Cause: {e.cause}")
        sys.exit(1)


if __name__ == "__main__":
    main()
