import sqlite3
import tempfile
import unittest
from pathlib import Path
import SecuSign as m

class SecurityChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original = m.DB_PATH
        m.DB_PATH = str(Path(self.tmp.name) / "secusign.db")
        m.init_db()
        self.client = m.app.test_client()

    def tearDown(self):
        m.DB_PATH = self.original
        self.tmp.cleanup()

    def test_rejects_reserved_admin_registration(self):
        r = self.client.post("/register", json={"username":"ADMIN","password":"TestPassword123!","email":"test@example.com"})
        self.assertEqual(r.status_code,400)

    def test_username_alone_does_not_grant_admin(self):
        with sqlite3.connect(m.DB_PATH) as db:
            db.execute("INSERT INTO users(username,password,email,role) VALUES (?,?,?,?)",
                       ("admin","hash","admin@example.com","user"))
        token = m.generate_token("admin")
        r = self.client.get("/admin/dashboard",headers={"Authorization":token})
        self.assertEqual(r.status_code,403)

    def test_unauthorized_admin_request(self):
        self.assertEqual(self.client.get("/admin/dashboard").status_code,401)

    def test_body_size_limited(self):
        self.assertEqual(m.app.config["MAX_CONTENT_LENGTH"],10*1024*1024)

if __name__ == "__main__":
    unittest.main()
