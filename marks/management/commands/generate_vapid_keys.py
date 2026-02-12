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

        # Private key in PEM format
        raw_priv = vapid.private_pem()
        priv_str = raw_priv.decode() if isinstance(raw_priv, bytes) else raw_priv

        # Public key as URL-safe base64 (applicationServerKey format)
        pub_bytes = vapid.public_key.public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint
        )
        pub_key = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()

        self.stdout.write(self.style.SUCCESS("\n=== VAPID Keys Generated ===\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={pub_key}\n")
        self.stdout.write(f"VAPID_PRIVATE_KEY={priv_str}\n")
        self.stdout.write(self.style.WARNING(
            "\nAdd these to your .env file. "
            "The PRIVATE key must be kept secret!\n"
        ))
