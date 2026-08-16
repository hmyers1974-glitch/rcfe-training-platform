from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import sqlite3, json, os, io, csv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rcfe.db")
MODULES_PATH = os.path.join(BASE_DIR, "modules.json")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "CHANGE-ME-BEFORE-PRODUCTION")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)


@app.route("/maria-caregiver.png")
def maria_caregiver_image():
    return send_file(os.path.join(BASE_DIR, "maria-caregiver.png"))


@app.route("/incident-storyboard.png")
def incident_storyboard_image():
    return send_file(os.path.join(BASE_DIR, "incident-storyboard.png"))


with open(MODULES_PATH, "r", encoding="utf-8") as f:
    MODULES = json.load(f)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student','admin','reviewer')),
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS enrollments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        course_version TEXT NOT NULL,
        enrolled_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS module_progress(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        module_id INTEGER NOT NULL,
        module_version TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        active_seconds INTEGER NOT NULL DEFAULT 0,
        last_seen_at TEXT,
        hunt_response TEXT,
        scenario_responses TEXT,
        comparison_response TEXT,
        exit_ticket TEXT,
        quiz_attempts INTEGER NOT NULL DEFAULT 0,
        quiz_passed INTEGER NOT NULL DEFAULT 0,
        UNIQUE(user_id,module_id,module_version),
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS activity_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        module_id INTEGER,
        event_type TEXT NOT NULL,
        event_data TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS certificates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        certificate_no TEXT UNIQUE NOT NULL,
        issued_at TEXT NOT NULL,
        course_version TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    conn.commit()

    seeds = [
        ("admin@rcfeacademy.local", "Heather Myers", "admin", "Admin123!"),
        ("reviewer@rcfeacademy.local", "ACB Reviewer", "reviewer", "Review123!"),
        ("student@rcfeacademy.local", "Demo Student", "student", "Student123!")
    ]

    for email, name, role, pw in seeds:
        try:
            cur.execute(
                "INSERT INTO users(email,full_name,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                (
                    email,
                    name,
                    generate_password_hash(pw),
                    role,
                    datetime.utcnow().isoformat()
                )
            )

            uid = cur.lastrowid

            if role == "student":
                cur.execute(
                    "INSERT INTO enrollments(user_id,course_version,enrolled_at) VALUES (?,?,?)",
                    (
                        uid,
                        "2026.08",
                        datetime.utcnow().isoformat()
                    )
                )

        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


init_db()


def current_user():
    uid = session.get("uid")

    if not uid:
        return None

    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE id=? AND active=1",
        (uid,)
    ).fetchone()
    conn.close()

    return row


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            u = current_user()

            if not u:
                return redirect(url_for("login"))

            if u["role"] not in roles:
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return deco


@app.route("/")
def index():
    u = current_user()

    if not u:
        return redirect(url_for("login"))

    if u["role"] == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("admin_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")

        conn = db()
        u = conn.execute(
            "SELECT * FROM users WHERE email=? AND active=1",
            (email,)
        ).fetchone()
        conn.close()

        if u and check_password_hash(u["password_hash"], pw):
            session.clear()
            session["uid"] = u["id"]
            session.permanent = True

            return redirect(url_for("index"))

        error = "Invalid email or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def student_progress(uid):
    conn = db()

    rows = conn.execute(
        "SELECT * FROM module_progress WHERE user_id=?",
        (uid,)
    ).fetchall()

    conn.close()

    by = {
        r["module_id"]: dict(r)
        for r in rows
    }

    return by


@app.route("/student")
@login_required
def student_dashboard():
    u = current_user()

    if u["role"] != "student":
        return redirect(url_for("admin_dashboard"))

    prog = student_progress(u["id"])

    complete = sum(
        1
        for m in MODULES
        if prog.get(m["id"], {}).get("completed_at")
    )

    return render_template(
        "student.html",
        user=u,
        modules=MODULES,
        progress=prog,
        complete=complete
    )


@app.route("/module/<int:module_id>")
@role_required("student", "reviewer", "admin")
def module_page(module_id):
    m = next(
        (x for x in MODULES if x["id"] == module_id),
        None
    )

    if not m:
        abort(404)

    u = current_user()
    prog = {}

    if u["role"] == "student":
        conn = db()

        row = conn.execute(
            """
            SELECT *
            FROM module_progress
            WHERE user_id=?
            AND module_id=?
            AND module_version=?
            """,
            (
                u["id"],
                module_id,
                "2026.08"
            )
        ).fetchone()

        if not row:
            conn.execute(
                """
                INSERT INTO module_progress(
                    user_id,
                    module_id,
                    module_version,
                    started_at,
                    last_seen_at
                )
                VALUES (?,?,?,?,?)
                """,
                (
                    u["id"],
                    module_id,
                    "2026.08",
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat()
                )
            )

            conn.commit()

            row = conn.execute(
                """
                SELECT *
                FROM module_progress
                WHERE user_id=?
                AND module_id=?
                AND module_version=?
                """,
                (
                    u["id"],
                    module_id,
                    "2026.08"
                )
            ).fetchone()

        prog = dict(row)
        conn.close()

    return render_template(
        "module.html",
        user=u,
        m=m,
        prog=prog
    )


@app.route("/api/progress/<int:module_id>", methods=["POST"])
@role_required("student")
def save_progress(module_id):
    u = current_user()
    payload = request.get_json(force=True)

    allowed = {
        "hunt_response",
        "scenario_responses",
        "comparison_response",
        "exit_ticket",
        "active_seconds"
    }

    sets = []
    vals = []

    for k in allowed:
        if k in payload:
            val = payload[k]

            if isinstance(val, (dict, list)):
                val = json.dumps(val)

            sets.append(f"{k}=?")
            vals.append(val)

    sets.append("last_seen_at=?")
    vals.append(datetime.utcnow().isoformat())

    vals += [
        u["id"],
        module_id,
        "2026.08"
    ]

    conn = db()

    conn.execute(
        f"""
        UPDATE module_progress
        SET {','.join(sets)}
        WHERE user_id=?
        AND module_id=?
        AND module_version=?
        """,
        vals
    )

    conn.execute(
        """
        INSERT INTO activity_events(
            user_id,
            module_id,
            event_type,
            event_data,
            created_at
        )
        VALUES (?,?,?,?,?)
        """,
        (
            u["id"],
            module_id,
            "progress_save",
            json.dumps(payload),
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()

    return jsonify(ok=True)


@app.route("/api/quiz/<int:module_id>", methods=["POST"])
@role_required("student")
def quiz(module_id):
    u = current_user()

    m = next(
        (x for x in MODULES if x["id"] == module_id),
        None
    )

    if not m:
        abort(404)

    idx = int(
        request.get_json(force=True).get(
            "answer",
            -1
        )
    )

    ok = idx == m["quiz"]["answer"]

    conn = db()

    conn.execute(
        """
        UPDATE module_progress
        SET quiz_attempts=quiz_attempts+1,
            quiz_passed=?,
            last_seen_at=?
        WHERE user_id=?
        AND module_id=?
        AND module_version=?
        """,
        (
            1 if ok else 0,
            datetime.utcnow().isoformat(),
            u["id"],
            module_id,
            "2026.08"
        )
    )

    conn.execute(
        """
        INSERT INTO activity_events(
            user_id,
            module_id,
            event_type,
            event_data,
            created_at
        )
        VALUES (?,?,?,?,?)
        """,
        (
            u["id"],
            module_id,
            "quiz_attempt",
            json.dumps({
                "answer": idx,
                "correct": ok
            }),
            datetime.utcnow().isoformat()
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        ok=ok,
        why=m["quiz"]["why"]
    )


@app.route("/api/complete/<int:module_id>", methods=["POST"])
@role_required("student")
def complete_module(module_id):
    u = current_user()
    payload = request.get_json(force=True)

    conn = db()

    row = conn.execute(
        """
        SELECT *
        FROM module_progress
        WHERE user_id=?
        AND module_id=?
        AND module_version=?
        """,
        (
            u["id"],
            module_id,
            "2026.08"
        )
    ).fetchone()

    if not row:
        abort(400)

    minimum_seconds = int(
        os.environ.get(
            "MODULE_MIN_ACTIVE_SECONDS",
            "60"
        )
    )

    required = [
        row["hunt_response"],
        row["scenario_responses"],
        row["comparison_response"],
        row["exit_ticket"]
    ]

    if not all(required):
        return jsonify(
            ok=False,
            error="Required interactions are incomplete."
        ), 400

    if not row["quiz_passed"]:
        return jsonify(
            ok=False,
            error="Knowledge check must be passed."
        ), 400

    if row["active_seconds"] < minimum_seconds:
        return jsonify(
            ok=False,
            error=f"Minimum active time not yet met ({minimum_seconds} seconds configured)."
        ), 400

    conn.execute(
        "UPDATE module_progress SET completed_at=? WHERE id=?",
        (
            datetime.utcnow().isoformat(),
            row["id"]
        )
    )

    conn.execute(
        """
        INSERT INTO activity_events(
            user_id,
            module_id,
            event_type,
            event_data,
            created_at
        )
        VALUES (?,?,?,?,?)
        """,
        (
            u["id"],
            module_id,
            "module_complete",
            "{}",
            datetime.utcnow().isoformat()
        )
    )

    count = conn.execute(
        """
        SELECT COUNT(*) n
        FROM module_progress
        WHERE user_id=?
        AND completed_at IS NOT NULL
        """,
        (u["id"],)
    ).fetchone()["n"]

    if count >= len(MODULES):
        conn.execute(
            """
            UPDATE enrollments
            SET completed_at=?
            WHERE user_id=?
            AND course_version=?
            """,
            (
                datetime.utcnow().isoformat(),
                u["id"],
                "2026.08"
            )
        )

    conn.commit()
    conn.close()

    return jsonify(ok=True)


@app.route("/admin")
@role_required("admin", "reviewer")
def admin_dashboard():
    u = current_user()
    conn = db()

    students = conn.execute(
        """
        SELECT
            u.id,
            u.full_name,
            u.email,
            e.enrolled_at,
            e.completed_at,
            SUM(
                CASE
                    WHEN mp.completed_at IS NOT NULL
                    THEN 1
                    ELSE 0
                END
            ) completed_modules,
            COALESCE(
                SUM(mp.active_seconds),
                0
            ) active_seconds
        FROM users u
        LEFT JOIN enrollments e
            ON e.user_id=u.id
        LEFT JOIN module_progress mp
            ON mp.user_id=u.id
        WHERE u.role='student'
        GROUP BY u.id
        ORDER BY u.full_name
        """
    ).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        user=u,
        students=students,
        module_count=len(MODULES)
    )


@app.route("/admin/student/<int:uid>")
@role_required("admin", "reviewer")
def student_detail(uid):
    conn = db()

    student = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id=?
        AND role='student'
        """,
        (uid,)
    ).fetchone()

    rows = conn.execute(
        """
        SELECT *
        FROM module_progress
        WHERE user_id=?
        ORDER BY module_id
        """,
        (uid,)
    ).fetchall()

    events = conn.execute(
        """
        SELECT *
        FROM activity_events
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (uid,)
    ).fetchall()

    conn.close()

    return render_template(
        "student_detail.html",
        user=current_user(),
        student=student,
        rows=rows,
        events=events,
        modules=MODULES
    )


@app.route("/admin/create-student", methods=["POST"])
@role_required("admin")
def create_student():
    name = request.form["full_name"].strip()
    email = request.form["email"].strip().lower()
    pw = request.form["password"]

    conn = db()

    try:
        conn.execute(
            """
            INSERT INTO users(
                email,
                full_name,
                password_hash,
                role,
                created_at
            )
            VALUES (?,?,?,?,?)
            """,
            (
                email,
                name,
                generate_password_hash(pw),
                "student",
                datetime.utcnow().isoformat()
            )
        )

        uid = conn.execute(
            "SELECT id FROM users WHERE email=?",
            (email,)
        ).fetchone()["id"]

        conn.execute(
            """
            INSERT INTO enrollments(
                user_id,
                course_version,
                enrolled_at
            )
            VALUES (?,?,?)
            """,
            (
                uid,
                "2026.08",
                datetime.utcnow().isoformat()
            )
        )

        conn.commit()

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export.csv")
@role_required("admin", "reviewer")
def export_csv():
    conn = db()

    rows = conn.execute(
        """
        SELECT
            u.full_name,
            u.email,
            mp.module_id,
            mp.module_version,
            mp.started_at,
            mp.completed_at,
            mp.active_seconds,
            mp.quiz_attempts,
            mp.quiz_passed
        FROM users u
        JOIN module_progress mp
            ON u.id=mp.user_id
        WHERE u.role='student'
        ORDER BY u.full_name, mp.module_id
        """
    ).fetchall()

    conn.close()

    sio = io.StringIO()
    w = csv.writer(sio)

    w.writerow([
        "Student",
        "Email",
        "Module",
        "Version",
        "Started",
        "Completed",
        "Active Seconds",
        "Quiz Attempts",
        "Quiz Passed"
    ])

    for r in rows:
        w.writerow(list(r))

    mem = io.BytesIO(
        sio.getvalue().encode("utf-8")
    )

    mem.seek(0)

    return send_file(
        mem,
        mimetype="text/csv",
        as_attachment=True,
        download_name="rcfe_completion_records.csv"
    )


@app.route("/certificate")
@role_required("student")
def certificate():
    u = current_user()
    conn = db()

    count = conn.execute(
        """
        SELECT COUNT(*) n
        FROM module_progress
        WHERE user_id=?
        AND completed_at IS NOT NULL
        """,
        (u["id"],)
    ).fetchone()["n"]

    if count < len(MODULES):
        conn.close()
        abort(403)

    cert = conn.execute(
        """
        SELECT *
        FROM certificates
        WHERE user_id=?
        AND course_version=?
        """,
        (
            u["id"],
            "2026.08"
        )
    ).fetchone()

    if not cert:
        cert_no = (
            f"RCFE-{datetime.utcnow().year}-"
            f"{u['id']:05d}-"
            f"{int(datetime.utcnow().timestamp())}"
        )

        conn.execute(
            """
            INSERT INTO certificates(
                user_id,
                certificate_no,
                issued_at,
                course_version
            )
            VALUES (?,?,?,?)
            """,
            (
                u["id"],
                cert_no,
                datetime.utcnow().isoformat(),
                "2026.08"
            )
        )

        conn.commit()

        cert = conn.execute(
            """
            SELECT *
            FROM certificates
            WHERE user_id=?
            AND course_version=?
            """,
            (
                u["id"],
                "2026.08"
            )
        ).fetchone()

    conn.close()

    mem = io.BytesIO()

    c = canvas.Canvas(
        mem,
        pagesize=letter
    )

    W, H = letter

    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(
        W / 2,
        H - 1.2 * inch,
        "CALIFORNIA RCFE LEADERSHIP ACADEMY"
    )

    c.setFont("Helvetica", 12)
    c.drawCentredString(
        W / 2,
        H - 1.55 * inch,
        "Regulation to Real Life"
    )

    c.setFont("Helvetica-Bold", 25)
    c.drawCentredString(
        W / 2,
        H - 2.3 * inch,
        "Certificate of Completion"
    )

    c.setFont("Helvetica", 13)
    c.drawCentredString(
        W / 2,
        H - 3.05 * inch,
        "This certifies that"
    )

    c.setFont("Helvetica-Bold", 19)
    c.drawCentredString(
        W / 2,
        H - 3.45 * inch,
        u["full_name"]
    )

    c.setFont("Helvetica", 12)
    c.drawCentredString(
        W / 2,
        H - 4.05 * inch,
        "completed the 20-Hour Interactive Self-Paced RCFE ICTP Component"
    )

    c.drawCentredString(
        W / 2,
        H - 4.35 * inch,
        "Course Version 2026.08"
    )

    c.setFont("Helvetica", 10)
    c.drawCentredString(
        W / 2,
        H - 5.0 * inch,
        f"Certificate No.: {cert['certificate_no']}"
    )

    c.drawCentredString(
        W / 2,
        H - 5.25 * inch,
        f"Issued: {cert['issued_at'][:10]}"
    )

    c.setFont("Helvetica-Oblique", 9)
    c.drawCentredString(
        W / 2,
        0.75 * inch,
        "Prototype certificate — vendor/course numbers to be added after ACB approval."
    )

    c.showPage()
    c.save()

    mem.seek(0)

    return send_file(
        mem,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="RCFE_Self_Paced_Certificate.pdf"
    ) 
