import os
import logging
import smtplib
import sqlite3
import socket
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5000').split(','))
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024

# Define upload folder
BASE_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(BASE_DIR, exist_ok=True)
app.config["UPLOAD_FOLDER"] = BASE_DIR
app.config["SECRET_KEY"] = os.getenv('SECRET_KEY', secrets.token_hex(32))  # Set a persistent secure key via environment variable or generate a secure random key

# Configure logging
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "app.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Rate limiter
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200 per hour"]
)

# Database setup
DB_PATH = os.path.join(BASE_DIR, "secusign.db")

def init_db():
    """Initialize SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT UNIQUE,
            role TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Helper Functions
def log_to_db(user_id, action, details):
    """Log actions to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO audit_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, action, details, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def generate_filename(base_name, extension=""):
    """Generate a timestamped professional filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{base_name}_{timestamp}{extension}"

def send_email(subject, recipient, body):
    """Send email notifications."""
    try:
        smtp = smtplib.SMTP("smtp.gmail.com", 587)
        smtp.starttls()
        smtp.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASSWORD'))  # Use environment variables for credentials
        message = f"Subject: {subject}\n\n{body}"
        smtp.sendmail(os.getenv('EMAIL_USER'), recipient, message)
        smtp.quit()
        logging.info(f"Email sent to {recipient}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")

# JWT Utility Functions
def generate_token(username):
    """Generate a JWT token for authentication."""
    payload = {
        "username": username,
        "exp": datetime.utcnow() + timedelta(hours=1)
    }
    token = jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")
    return token

def validate_token(token):
    """Validate JWT token."""
    try:
        payload = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Key Management Functions
def generate_keys():
    """Generate RSA keys and save them with a professional, timestamped name."""
    private_key_file = os.path.join(BASE_DIR, generate_filename("private_key", ".pem"))
    public_key_file = os.path.join(BASE_DIR, generate_filename("public_key", ".pem"))

    # Use secrets module to generate a unique seed for key generation
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    with open(private_key_file, "wb") as priv_file:
        priv_file.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
    with open(public_key_file, "wb") as pub_file:
        pub_file.write(
            public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

    # Logging the generated key details professionally
    log_to_db(1, "generate_keys", f"Generated keys: Private key - {private_key_file}, Public key - {public_key_file}")  # Replace `1` with actual user_id
    return {"private_key": private_key_file, "public_key": public_key_file}

# Signing and Verification Functions
def sign_file(file_path, private_key_path):
    """Sign a file with a private key."""
    with open(file_path, "rb") as f:
        file_data = f.read()
    with open(private_key_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(key_file.read(), password=None)

    signature = private_key.sign(
        file_data,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH
        ),
        hashes.SHA256(),
    )

    signature_file = f"{file_path}.sig"
    with open(signature_file, "wb") as sig_file:
        sig_file.write(signature)

    log_to_db(1, "sign_file", f"Signed file: {file_path} with signature: {signature_file}")  # Replace `1` with actual user_id
    return {"file": file_path, "signature": signature_file}

# API Endpoints
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    email = data.get("email")
    if isinstance(username, str) and username.casefold() == 'admin':
        return jsonify({"error": "Reserved account name"}), 400
    if not username or not password or not email:
        return jsonify({"error": "Missing required fields"}), 400
    hashed_password = generate_password_hash(password)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                       (username, hashed_password, email, "user"))
        conn.commit()
        conn.close()
        return jsonify({"message": "User registered successfully"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 400

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and check_password_hash(user[1], password):
        return jsonify({"token": generate_token(username)})
    return jsonify({"error": "Invalid credentials"}), 401

@app.route("/generate-keys", methods=["POST"])
def api_generate_keys():
    token = request.headers.get("Authorization")
    if not validate_token(token):
        return jsonify({"error": "Unauthorized"}), 401
    keys = generate_keys()
    return jsonify(keys)

@app.route("/batch-sign", methods=["POST"])
def api_batch_sign():
    token = request.headers.get("Authorization")
    if not validate_token(token):
        return jsonify({"error": "Unauthorized"}), 401

    private_key = request.files["private_key"]
    files = request.files.getlist("files")
    private_key_path = os.path.join(BASE_DIR, secure_filename(private_key.filename))
    private_key.save(private_key_path)

    results = []
    for file in files:
        file_path = os.path.join(BASE_DIR, secure_filename(file.filename))
        file.save(file_path)
        results.append(sign_file(file_path, private_key_path))

    return jsonify(results)

@app.route("/admin/dashboard", methods=["GET"])
def admin_dashboard():
    token = request.headers.get("Authorization")
    payload = validate_token(token)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username = ?", (payload.get("username"),))
    row = cursor.fetchone()
    if not row or row[0] != "admin":
        conn.close()
        return jsonify({"error": "Forbidden"}), 403
    cursor.execute("SELECT * FROM audit_logs")
    logs = cursor.fetchall()
    conn.close()
    return jsonify({"logs": logs})

# Run the server
if __name__ == "__main__":
    # Local development only. Keys are generated only by an authorized API call.
    print(" * Local development only: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
