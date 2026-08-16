from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    send_file,
    abort,
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
import sqlite3
import json
import os
import io
import csv

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch


# =========================================================
# APP SETUP
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rcfe.db")
MODULES_PATH = os.path.join(BASE_DIR, "modules.json")

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "CHANGE-ME-BEFORE-PRODUCTION",
)

app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)


# =========================================================
# FILE HELPERS
# =========================================================

def serve_root_file(filename, mimetype=None):
    file_path = os.path.join(BASE_DIR, filename)

    if not os.path.exists(file_path):
        abort(404)

    return send_file(
        file_path,
        mimetype=mimetype,
        conditional=True,
    )


# =========================================================
# IMAGE ROUTES
# =========================================================

@app.route("/maria-caregiver.png")
def maria_caregiver_image():
    return serve_root_file("maria-caregiver.png", "image/png")


@app.route("/incident-storyboard.png")
def incident_storyboard_image():
    return serve_root_file("incident-storyboard.png", "image/png")


@app.route("/scene-1-maria-admin.png")
def scene_1_image():
    return serve_root_file("scene-1-maria-admin.png", "image/png")


@app.route("/scene-2-report-fall.png")
def scene_2_image():
    return serve_root_file("scene-2-report-fall.png", "image/png")


@app.route("/scene-3-walk-room108.png")
def scene_3_image():
    return serve_root_file("scene-3-walk-room108.png", "image/png")


@app.route("/scene-4-enter-room.png")
def scene_4_image():
    return serve_root_file("scene-4-enter-room.png", "image/png")


@app.route("/scene-5-resident-floor.png")
def scene_5_image():
    return serve_root_file("scene-5-resident-floor.png", "image/png")


@app.route("/scene-6-resident-speaks.png")
def scene_6_image():
    return serve_root_file("scene-6-resident-speaks.png", "image/png")


@app.route("/scene-7-decision.png")
def scene_7_image():
    return serve_root_file("scene-7-decision.png", "image/png")


@app.route("/scene<int:scene_number>.png")
def numbered_scene_image(scene_number):
    if scene_number < 1 or scene_number > 7:
        abort(404)

    return serve_root_file(
        f"scene{scene_number}.png",
        "image/png",
    )


# =========================================================
# AUDIO ROUTES
# =========================================================

@app.route("/audio/scene<int:scene_number>.mp3")
def numbered_scene_audio(scene_number):
    if scene_number < 1 or scene_number > 7:
        abort(404)

    return serve_root_file(
        f"scene{scene_number}.mp3",
        "audio/mpeg",
    )


# =========================================================
# LOAD MODULE DATA
# =========================================================

with open(MODULES_PATH, "r", encoding="utf-8") as f:
    MODULES = json.load(f)


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(
                role IN ('student','admin','reviewer')
            ),
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
        """
    )

    conn.commit()

    seeds = [
        (
            "admin@rcfeacademy.local",
            "Heather Myers",
            "admin",
            "Admin123!",
        ),
        (
            "reviewer@rcfeacademy.local",
            "ACB Reviewer",
            "reviewer",
            "Review123!",
        ),
        (
            "student@rcfeacademy.local",
            "Demo Student",
            "student",
            "Student123!",
        ),
    ]

    for email, name, role, password in seeds:
        try:
            cur.execute(
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
                    generate_password_hash(password),
                    role,
                    datetime.utcnow().isoformat(),
                ),
            )

            user_id = cur.lastrowid

            if role == "student":
                cur.execute(
                    """
                    INSERT INTO enrollments(
                        user_id,
                        course_version,
                        enrolled_at
                    )
                    VALUES (?,?,?)
                    """,
                    (
                        user_id,
                        "2026.08",
                        datetime.utcnow().isoformat(),
                    ),
                )

        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()


init_db()


# =========================================================
# USER / LOGIN HELPERS
# =========================================================

def current_user():
    user_id = session.get("uid")

    if not user_id:
        return None

    conn = db()

    user = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id=?
        AND active=1
        """,
        (user_id,),
    ).fetchone()

    conn.close()

    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))

        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()

            if not user:
                return redirect(url_for("login"))

            if user["role"] not in roles:
                abort(403)

            return fn(*args, **kwargs)

        return wrapper

    return decorator


# =========================================================
# MAIN ROUTES
# =========================================================

@app.route("/")
def index():
    user = current_user()

    if not user:
        return redirect(url_for("login"))

    if user["role"] == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("admin_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = db()

        user = conn.execute(
            """
            SELECT *
            FROM users
            WHERE email=?
            AND active=1
            """,
            (email,),
        ).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password_hash"],
            password,
        ):
            session.clear()
            session["uid"] = user["id"]
            session.permanent = True

            return redirect(url_for("index"))

        error = "Invalid email or password."

    return render_template(
        "login.html",
        error=error,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# STUDENT DASHBOARD
# =========================================================

def student_progress(user_id):
    conn = db()

    rows = conn.execute(
        """
        SELECT *
        FROM module_progress
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchall()

    conn.close()

    return {
        row["module_id"]: dict(row)
        for row in rows
    }


@app.route("/student")
@login_required
def student_dashboard():
    user = current_user()

    if user["role"] != "student":
        return redirect(url_for("admin_dashboard"))

    progress = student_progress(user["id"])

    complete = sum(
        1
        for module in MODULES
        if progress.get(
            module["id"],
            {},
        ).get("completed_at")
    )

    return render_template(
        "student.html",
        user=user,
        modules=MODULES,
        progress=progress,
        complete=complete,
    )


# =========================================================
# MODULE PAGE
# =========================================================

@app.route("/module/<int:module_id>")
@role_required("student", "reviewer", "admin")
def module_page(module_id):
    module = next(
        (
            item
            for item in MODULES
            if item["id"] == module_id
        ),
        None,
    )

    if not module:
        abort(404)

    user = current_user()
    progress = {}

    if user["role"] == "student":
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
                user["id"],
                module_id,
                "2026.08",
            ),
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
                    user["id"],
                    module_id,
                    "2026.08",
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
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
                    user["id"],
                    module_id,
                    "2026.08",
                ),
            ).fetchone()

        progress = dict(row)
        conn.close()

    return render_template(
        "module.html",
        user=user,
        m=module,
        prog=progress,
    )


# =========================================================
# SAVE MODULE PROGRESS
# =========================================================

@app.route(
    "/api/progress/<int:module_id>",
    methods=["POST"],
)
@role_required("student")
def save_progress(module_id):
    user = current_user()
    payload = request.get_json(force=True)

    allowed = {
        "hunt_response",
        "scenario_responses",
        "comparison_response",
        "exit_ticket",
        "active_seconds",
    }

    sets = []
    values = []

    for key in allowed:
        if key in payload:
            value = payload[key]

            if isinstance(value, (dict, list)):
                value = json.dumps(value)

            sets.append(f"{key}=?")
            values.append(value)

    sets.append("last_seen_at=?")
    values.append(datetime.utcnow().isoformat())

    values += [
        user["id"],
        module_id,
        "2026.08",
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
        values,
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
            user["id"],
            module_id,
            "progress_save",
            json.dumps(payload),
            datetime.utcnow().isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    return jsonify(ok=True)


# =========================================================
# QUIZ
# =========================================================

@app.route(
    "/api/quiz/<int:module_id>",
    methods=["POST"],
)
@role_required("student")
def quiz(module_id):
    user = current_user()

    module = next(
        (
            item
            for item in MODULES
            if item["id"] == module_id
        ),
        None,
    )

    if not module:
        abort(404)

    payload = request.get_json(force=True)

    try:
        answer_index = int(payload.get("answer", -1))
    except (TypeError, ValueError):
        answer_index = -1

    correct = answer_index == module["quiz"]["answer"]

    conn = db()

    conn.execute(
        """
        UPDATE module_progress
        SET
            quiz_attempts = quiz_attempts + 1,
            quiz_passed=?,
            last_seen_at=?
        WHERE user_id=?
        AND module_id=?
        AND module_version=?
        """,
        (
            1 if correct else 0,
            datetime.utcnow().isoformat(),
            user["id"],
            module_id,
            "2026.08",
        ),
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
            user["id"],
            module_id,
            "quiz_attempt",
            json.dumps(
                {
                    "answer": answer_index,
                    "correct": correct,
                }
            ),
            datetime.utcnow().isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    return jsonify(
        ok=correct,
        why=module["quiz"]["why"],
    )


# =========================================================
# COMPLETE MODULE
# =========================================================

@app.route(
    "/api/complete/<int:module_id>",
    methods=["POST"],
)
@role_required("student")
def complete_module(module_id):
    user = current_user()
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
            user["id"],
            module_id,
            "2026.08",
        ),
    ).fetchone()

    if not row:
        conn.close()
        abort(400)

    minimum_seconds = int(
        os.environ.get(
            "MODULE_MIN_ACTIVE_SECONDS",
            "60",
        )
    )

    required = [
        row["hunt_response"],
        row["scenario_responses"],
        row["comparison_response"],
        row["exit_ticket"],
    ]

    if not all(required):
        conn.close()

        return jsonify(
            ok=False,
            error="Required interactions are incomplete.",
        ), 400

    if not row["quiz_passed"]:
        conn.close()

        return jsonify(
            ok=False,
            error="Knowledge check must be passed.",
        ), 400

    if row["active_seconds"] < minimum_seconds:
        conn.close()

        return jsonify(
            ok=False,
            error=(
                "Minimum active time not yet met "
                f"({minimum_seconds} seconds configured)."
            ),
        ), 400

    conn.execute(
        """
        UPDATE module_progress
        SET completed_at=?
        WHERE id=?
        """,
        (
            datetime.utcnow().isoformat(),
            row["id"],
        ),
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
            user["id"],
            module_id,
            "module_complete",
            "{}",
            datetime.utcnow().isoformat(),
        ),
    )

    count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM module_progress
        WHERE user_id=?
        AND completed_at IS NOT NULL
        """,
        (user["id"],),
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
                user["id"],
                "2026.08",
            ),
        )

    conn.commit()
    conn.close()

    return jsonify(ok=True)


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@role_required("admin", "reviewer")
def admin_dashboard():
    user = current_user()
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
            ) AS completed_modules,

            COALESCE(
                SUM(mp.active_seconds),
                0
            ) AS active_seconds

        FROM users u

        LEFT JOIN enrollments e
            ON e.user_id=u.id

        LEFT JOIN module_progress mp
            ON mp.user_id=u.id

        WHERE u.role='student'

        GROUP BY
            u.id,
            u.full_name,
            u.email,
            e.enrolled_at,
            e.completed_at

        ORDER BY u.full_name
        """
    ).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        user=user,
        students=students,
        module_count=len(MODULES),
    )


# =========================================================
# STUDENT DETAIL
# =========================================================

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
        (uid,),
    ).fetchone()

    if not student:
        conn.close()
        abort(404)

    rows = conn.execute(
        """
        SELECT *
        FROM module_progress
        WHERE user_id=?
        ORDER BY module_id
        """,
        (uid,),
    ).fetchall()

    events = conn.execute(
        """
        SELECT *
        FROM activity_events
        WHERE user_id=?
        ORDER BY created_at DESC
        LIMIT 100
        """,
        (uid,),
    ).fetchall()

    conn.close()

    return render_template(
        "student_detail.html",
        user=current_user(),
        student=student,
        rows=rows,
        events=events,
        modules=MODULES,
    )


# =========================================================
# CREATE STUDENT
# =========================================================

@app.route(
    "/admin/create-student",
    methods=["POST"],
)
@role_required("admin")
def create_student():
    name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or not password:
        return redirect(url_for("admin_dashboard"))

    conn = db()

    try:
        cursor = conn.execute(
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
                generate_password_hash(password),
                "student",
                datetime.utcnow().isoformat(),
            ),
        )

        user_id = cursor.lastrowid

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
                user_id,
                "2026.08",
                datetime.utcnow().isoformat(),
            ),
        )

        conn.commit()

    except sqlite3.IntegrityError:
        conn.rollback()

    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))


# =========================================================
# CSV EXPORT
# =========================================================

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

        ORDER BY
            u.full_name,
            mp.module_id
        """
    ).fetchall()

    conn.close()

    text_buffer = io.StringIO()
    writer = csv.writer(text_buffer)

    writer.writerow(
        [
            "Student",
            "Email",
            "Module",
            "Version",
            "Started",
            "Completed",
            "Active Seconds",
            "Quiz Attempts",
            "Quiz Passed",
        ]
    )

    for row in rows:
        writer.writerow(list(row))

    memory_file = io.BytesIO(
        text_buffer.getvalue().encode("utf-8")
    )

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype="text/csv",
        as_attachment=True,
        download_name="rcfe_completion_records.csv",
    )


# =========================================================
# CERTIFICATE
# =========================================================

@app.route("/certificate")
@role_required("student")
def certificate():
    user = current_user()
    conn = db()

    count = conn.execute(
        """
        SELECT COUNT(*) AS n
        FROM module_progress
        WHERE user_id=?
        AND completed_at IS NOT NULL
        """,
        (user["id"],),
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
            user["id"],
            "2026.08",
        ),
    ).fetchone()

    if not cert:
        cert_no = (
            f"RCFE-"
            f"{datetime.utcnow().year}-"
            f"{user['id']:05d}-"
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
                user["id"],
                cert_no,
                datetime.utcnow().isoformat(),
                "2026.08",
            ),
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
                user["id"],
                "2026.08",
            ),
        ).fetchone()

    conn.close()

    memory_file = io.BytesIO()

    pdf = canvas.Canvas(
        memory_file,
        pagesize=letter,
    )

    width, height = letter

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(
        width / 2,
        height - 1.2 * inch,
        "CALIFORNIA RCFE LEADERSHIP ACADEMY",
    )

    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(
        width / 2,
        height - 1.55 * inch,
        "Regulation to Real Life",
    )

    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawCentredString(
        width / 2,
        height - 2.3 * inch,
        "Certificate of Completion",
    )

    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(
        width / 2,
        height - 3.05 * inch,
        "This certifies that",
    )

    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawCentredString(
        width / 2,
        height - 3.45 * inch,
        user["full_name"],
    )

    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(
        width / 2,
        height - 4.05 * inch,
        "completed the 20-Hour Interactive Self-Paced RCFE ICTP Component",
    )

    pdf.drawCentredString(
        width / 2,
        height - 4.35 * inch,
        "Course Version 2026.08",
    )

    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        width / 2,
        height - 5.0 * inch,
        f"Certificate No.: {cert['certificate_no']}",
    )

    pdf.drawCentredString(
        width / 2,
        height - 5.25 * inch,
        f"Issued: {cert['issued_at'][:10]}",
    )

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawCentredString(
        width / 2,
        0.75 * inch,
        "Prototype certificate — vendor/course numbers to be added after ACB approval.",
    )

    pdf.showPage()
    pdf.save()

    memory_file.seek(0)

    return send_file(
        memory_file,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="RCFE_Self_Paced_Certificate.pdf",
    )


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)
