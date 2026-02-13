"""
Management command to generate VAPID key pair for Web Push notifications.
Run once during initial setup: python manage.py generate_vapid_keys
"""

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand
from py_vapid import Vapid


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Web Push notifications"

    def handle(self, *args, **options):
        vapid = Vapid()
        vapid.generate_keys()

        # Private key as URL-safe base64 raw bytes (single-line, .env friendly)
        priv_raw = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        priv_key = base64.urlsafe_b64encode(priv_raw).rstrip(b"=").decode()

        # Public key as URL-safe base64 (applicationServerKey format)
        pub_bytes = vapid.public_key.public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        pub_key = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()

        self.stdout.write(self.style.SUCCESS("\n=== VAPID Keys Generated ===\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={pub_key}\n")
        self.stdout.write(f"VAPID_PRIVATE_KEY={priv_key}\n")
        self.stdout.write(self.style.WARNING(
            "\nAdd these to your .env file (and Render environment variables). "
            "The PRIVATE key must be kept secret!\n"
        ))
