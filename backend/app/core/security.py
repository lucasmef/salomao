import hashlib
import hmac
import json
import secrets
from base64 import b32decode, b32encode
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timedelta, timezone


PBKDF2_ITERATIONS = 120_000
DEFAULT_ADMIN_EMAIL = "lucasmef@gmail.com"
DEFAULT_ADMIN_PASSWORD = "admin123"
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(candidate, digest)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiration(hours: int = 12) -> datetime:
    return utc_now() + timedelta(hours=hours)


def generate_mfa_secret() -> str:
    return b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp_counter(for_time: datetime | None = None) -> int:
    current = for_time or utc_now()
    return int(current.timestamp()) // TOTP_PERIOD_SECONDS


def _totp_secret_bytes(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    return b32decode(f"{normalized}{padding}".encode("ascii"), casefold=True)


def generate_totp_code(secret: str, for_time: datetime | None = None) -> str:
    counter = _totp_counter(for_time)
    message = counter.to_bytes(8, byteorder="big")
    digest = hmac.new(_totp_secret_bytes(secret), message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], byteorder="big") & 0x7FFFFFFF
    return str(binary % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def verify_totp_code(secret: str, code: str, *, allowed_drift: int = 1, for_time: datetime | None = None) -> bool:
    normalized_code = "".join(char for char in code if char.isdigit())
    if len(normalized_code) != TOTP_DIGITS:
        return False
    now = for_time or utc_now()
    for drift in range(-allowed_drift, allowed_drift + 1):
        candidate_time = now + timedelta(seconds=drift * TOTP_PERIOD_SECONDS)
        if hmac.compare_digest(generate_totp_code(secret, candidate_time), normalized_code):
            return True
    return False


def build_totp_uri(secret: str, account_name: str, issuer: str) -> str:
    safe_issuer = issuer.replace(" ", "%20")
    safe_account = account_name.replace(" ", "%20")
    return f"otpauth://totp/{safe_issuer}:{safe_account}?secret={secret}&issuer={safe_issuer}&period={TOTP_PERIOD_SECONDS}&digits={TOTP_DIGITS}"


def sign_state_token(payload: dict, secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_body = urlsafe_b64encode(body).decode("ascii").rstrip("=")
    signature = hmac.new(secret.encode("utf-8"), encoded_body.encode("ascii"), hashlib.sha256).digest()
    encoded_signature = urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded_body}.{encoded_signature}"


def verify_state_token(token: str, secret: str) -> dict:
    encoded_body, encoded_signature = token.split(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded_body.encode("ascii"), hashlib.sha256).digest()
    expected_encoded = urlsafe_b64encode(expected).decode("ascii").rstrip("=")
    if not hmac.compare_digest(expected_encoded, encoded_signature):
        raise ValueError("Assinatura invalida")
    padding = "=" * (-len(encoded_body) % 4)
    body = urlsafe_b64decode(f"{encoded_body}{padding}".encode("ascii"))
    return json.loads(body.decode("utf-8"))
