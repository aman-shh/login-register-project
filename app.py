from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "mysite_secret_key_2024"

UPLOAD_FOLDER = "uploads"
PROFILE_FOLDER = "static/profile_pics"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "txt", "pdf", "doc", "docx",
    "png", "jpg", "jpeg", "gif",
    "mp4", "avi", "mov",
    "zip", "rar"
}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db():
    conn = sqlite3.connect('database.db', timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def create_database():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            profile_pic TEXT,
            password TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            category TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT,
            action TEXT,
            status TEXT,
            timestamp TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')

    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and \
           filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def log_activity(user_id, email, action, status):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity (user_id, email, action, status) VALUES (?,?,?,?)",
            (user_id, email, action, status)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Log error: {e}")


@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            session['profile_pic'] = user['profile_pic']

            log_activity(user['id'], email, 'login', 'success')
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('home'))
        else:
            log_activity(None, email, 'login', 'failed')
            flash("Invalid email or password.", 'error')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        name = request.form['name'].strip()
        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip()
        blood_group = request.form['blood_group']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # ── BUG FIX 4: validate BEFORE touching the filesystem ──
        if password != confirm_password:
            flash("Passwords do not match!", 'error')
            return redirect(url_for('register'))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", 'error')
            return redirect(url_for('register'))

        # Save profile pic only after validation passes
        profile_pic = request.files.get('profile_pic')
        profile_filename = None

        if profile_pic and profile_pic.filename:
            profile_filename = secure_filename(profile_pic.filename)
            profile_pic.save(os.path.join(PROFILE_FOLDER, profile_filename))

        hashed = generate_password_hash(password)

        conn = None  # ensure conn is always defined before except block
        try:
            conn = get_db()
            conn.execute('''
                INSERT INTO users (name, email, phone, blood_group, profile_pic, password)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, email, phone, blood_group, profile_filename, hashed))
            conn.commit()

            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
            new_user = cursor.fetchone()
            conn.close()

            log_activity(new_user['id'], email, 'register', 'success')
            flash("Account created successfully!", 'success')
            return redirect(url_for('login'))

        # ── BUG FIX 2: safe conn.close() even if conn assignment failed ──
        except sqlite3.IntegrityError:
            if conn:
                conn.close()
            flash("Email already exists.", 'error')
            return redirect(url_for('register'))

        except Exception as e:
            if conn:
                conn.close()
            flash(f"Registration error: {e}", 'error')
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/home')
def home():
    if 'user_id' not in session:
        flash("Please login first.", 'error')
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM files
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
    ''', (session['user_id'],))
    files = cursor.fetchall()
    conn.close()

    return render_template('home.html', files=files, username=session['user_name'])


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user_id' not in session:
        flash("Please login first.", 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        category = request.form.get('fileCategory', '')
        file = request.files.get('fileUpload')

        if not file or file.filename == '':
            flash("No file selected.", 'error')
            return redirect(url_for('upload'))

        if not allowed_file(file.filename):
            flash("File type not allowed.", 'error')
            return redirect(url_for('upload'))

        safe_name = secure_filename(file.filename)
        file_ext = safe_name.rsplit('.', 1)[1].lower()
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        file.save(save_path)

        conn = get_db()
        conn.execute('''
            INSERT INTO files (user_id, username, file_name, file_type, category)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], session['user_name'], safe_name, file_ext, category))
        conn.commit()
        conn.close()

        log_activity(session['user_id'], session['user_email'], 'upload', 'success')
        flash(f"{safe_name} uploaded successfully!", 'success')
        return redirect(url_for('home'))

    return render_template('upload.html')


# ── BUG FIX 3: accept POST (form in home.html uses method="POST") ──
@app.route('/delete/<int:file_id>', methods=['GET', 'POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    file = conn.execute(
        'SELECT * FROM files WHERE id = ? AND user_id = ?',
        (file_id, session['user_id'])
    ).fetchone()

    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file['file_name'])
        if os.path.exists(file_path):
            os.remove(file_path)
        conn.execute('DELETE FROM files WHERE id = ?', (file_id,))
        conn.commit()

    conn.close()
    flash("File deleted successfully!", "success")
    return redirect(url_for('home'))


@app.route('/upload_folder', methods=['POST'])
def upload_folder():
    if 'user_id' not in session:
        flash("Please login first.", 'error')
        return redirect(url_for('login'))

    category = request.form.get('fileCategory', '')
    files = request.files.getlist('fileUpload[]')

    if not files or all(f.filename == '' for f in files):
        flash("No folder selected.", 'error')
        return redirect(url_for('upload'))

    uploaded_count = 0
    skipped_count = 0
    conn = get_db()

    for file in files:
        if file.filename == '':
            continue
        if not allowed_file(file.filename):
            skipped_count += 1
            continue

        safe_name = secure_filename(file.filename.replace('/', '_').replace('\\', '_'))
        file_ext = safe_name.rsplit('.', 1)[1].lower() if '.' in safe_name else 'unknown'
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        file.save(save_path)

        conn.execute('''
            INSERT INTO files (user_id, username, file_name, file_type, category)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], session['user_name'], safe_name, file_ext, category))
        uploaded_count += 1

    conn.commit()
    conn.close()

    msg = f"{uploaded_count} file(s) uploaded successfully!"
    if skipped_count:
        msg += f" ({skipped_count} skipped — file type not allowed)"
    flash(msg, 'success')
    return redirect(url_for('home'))


@app.route('/logout')
def logout():
    if 'user_id' in session:
        log_activity(session['user_id'], session.get('user_email'), 'logout', 'success')

    session.clear()
    flash("Logged out successfully.", 'success')
    return redirect(url_for('login'))


if __name__ == '__main__':
    create_database()
    app.run(debug=True)