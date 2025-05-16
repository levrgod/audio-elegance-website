import os
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, flash
from werkzeug.utils import secure_filename
import datetime
import sqlite3

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_fallback_secret_key_please_change_in_production')
app.config['UPLOAD_FOLDER'] = '/home/ubuntu/audio_website/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}

# --- Database Setup ---
def get_db_connection():
    conn = sqlite3.connect('/home/ubuntu/audio_website/database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            filename TEXT NOT NULL UNIQUE,
            upload_date TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

ADMIN_USERNAME = "123456789"
ADMIN_PASSWORD = "123456789"

# --- Routes ---
@app.route('/')
def index():
    conn = get_db_connection()
    audios_cursor = conn.execute('SELECT * FROM audios ORDER BY upload_date DESC')
    audios = audios_cursor.fetchall()
    conn.close()
    return render_template('index.html', audios=audios)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('登录成功!', 'message')
            return redirect(url_for('admin_dashboard'))
        else:
            error = '无效的账户或密码。请重试。'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('您已成功登出。', 'message')
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    audios_cursor = conn.execute('SELECT * FROM audios ORDER BY upload_date DESC')
    audios = audios_cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', audios=audios)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if not session.get('logged_in'):
        flash('请先登录。', 'error')
        return redirect(url_for('login'))

    if 'audiofile' not in request.files:
        flash('未检测到文件部分。', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['audiofile']
    title = request.form.get('title')
    description = request.form.get('description', '')

    if not title:
        flash('音频标题不能为空。', 'error')
        return redirect(url_for('admin_dashboard'))

    if file.filename == '':
        flash('未选择任何文件。', 'error')
        return redirect(url_for('admin_dashboard'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Prevent filename collisions by prepending a timestamp or UUID if necessary
        # For now, we assume unique filenames or overwrite, but secure_filename helps.
        # A more robust solution would be to check if filename exists or add unique prefix.
        
        # Check if file with the same name already exists in DB
        conn_check = get_db_connection()
        existing_file = conn_check.execute('SELECT id FROM audios WHERE filename = ?', (filename,)).fetchone()
        conn_check.close()
        
        if existing_file:
            flash(f'文件名 "{filename}" 已存在。请重命名文件或删除现有条目。', 'error')
            return redirect(url_for('admin_dashboard'))
            
        try:
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            upload_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            conn = get_db_connection()
            conn.execute('INSERT INTO audios (title, description, filename, upload_date) VALUES (?, ?, ?, ?)',
                         (title, description, filename, upload_date))
            conn.commit()
            conn.close()
            flash('音频 "' + title + '" 上传成功!', 'message')
        except Exception as e:
            flash(f'文件上传或数据库操作失败: {str(e)}', 'error')
            # Potentially remove partially saved file if error occurs
            if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
                 try:
                     os.remove(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                 except OSError as oe:
                     app.logger.error(f"Error deleting partially uploaded file {filename}: {oe}")

    else:
        flash('不允许的文件类型。请上传 MP3, WAV, OGG, M4A, 或 FLAC 文件。', 'error')
        
    return redirect(url_for('admin_dashboard'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/delete/<int:audio_id>', methods=['POST'])
def delete_audio(audio_id):
    if not session.get('logged_in'):
        flash('请先登录以执行此操作。', 'error')
        return redirect(url_for('login'))

    conn = get_db_connection()
    audio = conn.execute('SELECT filename FROM audios WHERE id = ?', (audio_id,)).fetchone()
    
    if audio:
        try:
            # Delete from database
            conn.execute('DELETE FROM audios WHERE id = ?', (audio_id,))
            conn.commit()
            
            # Delete file from filesystem
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], audio['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            flash('音频删除成功。', 'message')
        except Exception as e:
            conn.rollback() # Rollback DB changes if file deletion fails or other error
            flash(f'删除音频时出错: {str(e)}', 'error')
        finally:
            conn.close()
    else:
        flash('未找到要删除的音频。', 'error')
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    init_db() # Initialize the database and create tables if they don't exist
    # For development, Werkzeug's run_simple is fine. 
    # For production, use a proper WSGI server like Gunicorn or uWSGI.    app.run(host=\'0.0.0.0\', port=5000) # debug=True for development
