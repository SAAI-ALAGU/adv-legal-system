"""
Advocate Case Management System with Personal AI Assistant
A comprehensive legal case management web application
"""

import os
import sqlite3
import datetime
import uuid
import json
import google.generativeai as genai
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'advocate_case_management_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directories exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'advocates'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'clients'), exist_ok=True)

# Database initialization
def init_db():
    conn = sqlite3.connect('advocate_system.db')
    c = conn.cursor()
    
    # Advocates table
    c.execute('''CREATE TABLE IF NOT EXISTS advocates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advocate_id TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        address TEXT,
        bar_registration TEXT,
        specialization TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Clients table
    c.execute('''CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone TEXT,
        address TEXT,
        aadhar_number TEXT,
        profile_image TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Cases table
    c.execute('''CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_number TEXT UNIQUE NOT NULL,
        client_id INTEGER NOT NULL,
        advocate_id INTEGER NOT NULL,
        court_name TEXT NOT NULL,
        case_type TEXT NOT NULL,
        hiring_date DATE NOT NULL,
        hearing_date DATE,
        case_result TEXT DEFAULT 'pending',
        description TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id),
        FOREIGN KEY (advocate_id) REFERENCES advocates(id)
    )''')
    
    # Messages table
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_type TEXT NOT NULL,
        sender_id INTEGER NOT NULL,
        receiver_type TEXT NOT NULL,
        receiver_id INTEGER NOT NULL,
        case_id INTEGER,
        message_text TEXT NOT NULL,
        message_type TEXT DEFAULT 'text',
        file_path TEXT,
        is_read BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )''')
    
    # Documents table
    c.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id INTEGER NOT NULL,
        uploaded_by_type TEXT NOT NULL,
        uploaded_by_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (case_id) REFERENCES cases(id)
    )''')
    
    # Notifications table
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_type TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        notification_type TEXT DEFAULT 'general',
        is_read BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # AI Chat History table
    c.execute('''CREATE TABLE IF NOT EXISTS ai_chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        advocate_id INTEGER NOT NULL,
        user_message TEXT NOT NULL,
        ai_response TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (advocate_id) REFERENCES advocates(id)
    )''')
    
    conn.commit()
    
    # Add new columns if they don't exist (for existing databases)
    try:
        c.execute('ALTER TABLE clients ADD COLUMN aadhar_number TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE clients ADD COLUMN profile_image TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE advocates ADD COLUMN address TEXT')
    except:
        pass
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# Helper functions
def get_db_connection():
    conn = sqlite3.connect('advocate_system.db')
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or 'user_type' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Allowed file extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# AI Legal Assistant responses
# GOOGLE_API_KEY = "AIzaSyCCA9SdQmRaQYnLLTjGY2EPZ1S8RXpC4gg"  # Google API Key

def get_ai_response(user_message):
    """Generate AI legal assistant responses using pre-defined responses"""
    return get_fallback_response(user_message)

def get_fallback_response(user_message):
    """Fallback pre-defined legal responses"""
    user_message = user_message.lower()
    
    # Legal research responses
    if any(word in user_message for word in ['research', 'search', 'find law', 'legal research', 'law']):
        return """Based on your query, here are some key legal research points:\n\n1. **Constitutional Law**: The Indian Constitution provides fundamental rights under Part III (Articles 14-32).\n\n2. **Criminal Procedure**: CrPC governs criminal trials in India. Key sections include Section 164 (confession recording), Section 378 (appeal rights).\n\n3. **Civil Procedure**: CPC (Code of Civil Procedure) governs civil litigation. Order XXXIX covers temporary injunctions.\n\n4. **Contract Law**: Indian Contract Act, 1872 defines valid contracts under Section 10.\n\nWould you like me to elaborate on any specific area?"""
    
    # Law sections explanations
    elif any(word in user_message for word in ['section', 'ipc', 'crpc', 'cpc', 'explain', 'explain']):
        return """Here are important law sections commonly used:\n\n**IPC Section 302**: Punishment for murder - Death or life imprisonment.\n\n**IPC Section 420**: Cheating and dishonestly inducing delivery of property.\n\n**CrPC Section 125**: Maintenance of wives, children, and parents.\n\n**CPC Order 7 Rule 1**: Contents of plaint.\n\n**Section 138 NI Act**: Dishonour of cheque.\n\nWould you like detailed explanation of any specific section?"""
    
    # Case document summaries
    elif any(word in user_message for word in ['summarize', 'summary', 'case brief', 'case']):
        return """To summarize a case document, I need the following structure:\n\n**Case Citation**: [Year] SCC [Volume] Page\n\n**Facts**: Brief description of relevant facts\n\n**Issues**: Legal questions raised\n\n**Judgment**: Court's decision and reasoning\n\n**Ratio Decidendi**: Legal principle established\n\nPlease provide the case details or tell me which famous case you'd like summarized (e.g., Kesavananda Bharati, Maneka Gandhi)."""
    
    # Drafting legal documents
    elif any(word in user_message for word in ['draft', 'notice', 'affidavit', 'petition', 'document']):
        return """I can help draft the following legal documents:\n\n**Legal Notice**: Under Section 80 CPC, before filing suit against government - Should state facts, cause of action, relief sought - Give 2 months notice period\n\n**Affidavit**: Personal details of deponent, Statement of facts in numbered paragraphs, Declaration of truth\n\n**Petition**: Heading with court name, Parties' details, Grounds of petition, Prayer clause\n\nWhich document would you like to draft? Please provide the specific details."""
    
    else:
        return """Hello! I'm your AI Legal Assistant. I can help you with:\n\n1. **Legal Research** - Information on various laws and statutes\n2. **Law Section Explanations** - Detailed explanations of IPC, CrPC, CPC, etc.\n3. **Case Summaries** - Brief important case laws\n4. **Document Drafting** - Legal notices, affidavits, petitions, contracts\n\nHow may I assist you today? Please type your legal question or request."""

# Routes

@app.route('/')
def index():
    if 'user_id' in session and 'user_type' in session:
        if session['user_type'] == 'advocate':
            return redirect(url_for('advocate_dashboard'))
        else:
            return redirect(url_for('client_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['user_id']
        password = request.form['password']
        user_type = request.form['user_type']
        
        conn = get_db_connection()
         
        if user_type == 'advocate':
            user = conn.execute('SELECT * FROM advocates WHERE advocate_id = ? OR email = ?', (user_id, user_id)).fetchone()
        else:
            user = conn.execute('SELECT * FROM clients WHERE client_id = ? OR email = ?', (user_id, user_id)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_type'] = user_type
            session['user_name'] = user['name']
            
            if user_type == 'advocate':
                return redirect(url_for('advocate_dashboard'))
            else:
                return redirect(url_for('client_dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html', registered=request.args.get('registered'), user_id=request.args.get('user_id'), user_type=request.args.get('user_type'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_type = request.form['user_type']
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = generate_password_hash(request.form['password'])
        
        conn = get_db_connection()
        
        if user_type == 'advocate':
            advocate_id = 'ADV' + str(uuid.uuid4())[:8].upper()
            bar_reg = request.form.get('bar_registration')
            specialization = request.form.get('specialization')
            
            try:
                conn.execute('''INSERT INTO advocates 
                    (advocate_id, password, name, email, phone, bar_registration, specialization) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (advocate_id, password, name, email, phone, bar_reg, specialization))
                conn.commit()
                conn.close()
                return redirect(url_for('login', registered=True, user_id=advocate_id, user_type='advocate'))
            except:
                conn.close()
                return render_template('register.html', error='Email or ID already exists')
        else:
            client_id = 'CLI' + str(uuid.uuid4())[:8].upper()
            address = request.form.get('address')
            
            try:
                conn.execute('''INSERT INTO clients 
                    (client_id, password, name, email, phone, address) 
                    VALUES (?, ?, ?, ?, ?, ?)''',
                    (client_id, password, name, email, phone, address))
                conn.commit()
                conn.close()
                return redirect(url_for('login', registered=True, user_id=client_id, user_type='client'))
            except:
                conn.close()
                return render_template('register.html', error='Email or ID already exists')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/advocate/create-client', methods=['GET', 'POST'])
@login_required
def advocate_create_client():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form.get('phone', '')
        address = request.form.get('address', '')
        aadhar_number = request.form.get('aadhar_number', '')
        password = generate_password_hash(request.form['password'])
        
        # Generate client ID
        client_id = 'CLI' + str(uuid.uuid4())[:8].upper()
        
        # Handle profile image upload
        profile_image = None
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', 'temp')
                os.makedirs(folder_path, exist_ok=True)
                profile_image = filename
                file.save(os.path.join(folder_path, filename))
        
        conn = get_db_connection()
        
        try:
            conn.execute('''INSERT INTO clients 
                (client_id, password, name, email, phone, address, aadhar_number, profile_image)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (client_id, password, name, email, phone, address, aadhar_number, profile_image))
            conn.commit()
            conn.close()
            
            # Notify the advocate that client was created
            conn = get_db_connection()
            conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
                VALUES (?, ?, ?, ?, ?)''',
                ('advocate', session['user_id'], 'Client Created', 
                 f'Client {name} ({client_id}) has been created successfully', 'system'))
            conn.commit()
            conn.close()
            
            return render_template('advocate_create_client.html', 
                                 success=True, 
                                 client_id=client_id, 
                                 password=request.form['password'],
                                 client_name=name)
        except Exception as e:
            conn.close()
            return render_template('advocate_create_client.html', 
                                 error='Failed to create client. Email or ID might already exist.')
    
    return render_template('advocate_create_client.html')

@app.route('/advocate/client/<int:client_id>')
@login_required
def advocate_view_client(client_id):
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
    
    if not client:
        conn.close()
        return redirect(url_for('advocate_clients'))
    
    # Get client's cases with this advocate
    cases = conn.execute('''SELECT * FROM cases 
        WHERE client_id = ? AND advocate_id = ? 
        ORDER BY created_at DESC''', 
        (client_id, session['user_id'])).fetchall()
    
    conn.close()
    
    return render_template('advocate_view_client.html', client=client, cases=cases)

# Advocate Routes

@app.route('/advocate/dashboard')
@login_required
def advocate_dashboard():
    if session['user_type'] != 'advocate':
        return redirect(url_for('client_dashboard'))
    
    conn = get_db_connection()
    
    # Get statistics
    total_cases = conn.execute('SELECT COUNT(*) FROM cases WHERE advocate_id = ?', (session['user_id'],)).fetchone()[0]
    upcoming_hirings = conn.execute('''SELECT * FROM cases 
        WHERE advocate_id = ? AND hiring_date >= date('now') 
        ORDER BY hiring_date LIMIT 5''', (session['user_id'],)).fetchall()
    
    unread_messages = conn.execute('''SELECT COUNT(*) FROM messages 
        WHERE receiver_type = 'advocate' AND receiver_id = ? AND is_read = 0''', 
        (session['user_id'],)).fetchone()[0]
    
    recent_messages = conn.execute('''SELECT m.*, c.name as client_name 
        FROM messages m JOIN clients c ON m.sender_id = c.id 
        WHERE m.receiver_type = 'advocate' AND m.receiver_id = ? 
        ORDER BY m.created_at DESC LIMIT 5''', (session['user_id'],)).fetchall()
    
    notifications = conn.execute('''SELECT * FROM notifications 
        WHERE user_type = 'advocate' AND user_id = ? AND is_read = 0 
        ORDER BY created_at DESC LIMIT 5''', (session['user_id'],)).fetchall()
    
    clients = conn.execute('SELECT * FROM clients').fetchall()
    
    conn.close()
    
    return render_template('advocate_dashboard.html',
        total_cases=total_cases,
        upcoming_hirings=upcoming_hirings,
        unread_messages=unread_messages,
        recent_messages=recent_messages,
        notifications=notifications,
        clients=clients)

@app.route('/advocate/cases', methods=['GET', 'POST'])
@login_required
def advocate_cases():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        case_number = 'CASE' + str(uuid.uuid4())[:8].upper()
        client_id = request.form['client_id']
        court_name = request.form['court_name']
        case_type = request.form['case_type']
        hiring_date = request.form['hiring_date']
        hearing_date = request.form['hearing_date']
        description = request.form['description']
        
        conn.execute('''INSERT INTO cases 
            (case_number, client_id, advocate_id, court_name, case_type, hiring_date, hearing_date, description) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (case_number, client_id, session['user_id'], court_name, case_type, hiring_date, hearing_date, description))
        
        # Create notification for client
        client = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,)).fetchone()
        conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
            VALUES (?, ?, ?, ?, ?)''',
            ('client', client_id, 'New Case Created', 
             f'Your case {case_number} has been created by {session["user_name"]}', 'case'))
        
        conn.commit()
    
    cases = conn.execute('''SELECT c.*, cl.name as client_name 
        FROM cases c JOIN clients cl ON c.client_id = cl.id 
        WHERE c.advocate_id = ? ORDER BY c.created_at DESC''', (session['user_id'],)).fetchall()
    clients = conn.execute('SELECT * FROM clients').fetchall()
    
    conn.close()
    
    return render_template('advocate_cases.html', cases=cases, clients=clients)

@app.route('/advocate/case/<int:case_id>', methods=['GET', 'POST'])
@login_required
def advocate_case_detail(case_id):
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        # Update case details
        if 'update_case' in request.form:
            court_name = request.form['court_name']
            case_type = request.form['case_type']
            hearing_date = request.form['hearing_date']
            case_result = request.form['case_result']
            
            conn.execute('''UPDATE cases SET court_name = ?, case_type = ?, 
                hearing_date = ?, case_result = ? WHERE id = ?''',
                (court_name, case_type, hearing_date, case_result, case_id))
            
            # Notify client
            case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
            conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
                VALUES (?, ?, ?, ?, ?)''',
                ('client', case['client_id'], 'Case Updated', 
                 f'Your case {case["case_number"]} has been updated', 'case'))
            conn.commit()
        
        # Upload document
        elif 'upload_document' in request.form:
            if 'file' in request.files:
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    case = conn.execute('SELECT case_number FROM cases WHERE id = ?', (case_id,)).fetchone()
                    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'advocates', str(case_id))
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    file.save(file_path)
                    
                    description = request.form.get('description', '')
                    conn.execute('''INSERT INTO documents 
                        (case_id, uploaded_by_type, uploaded_by_id, file_name, file_path, file_type, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (case_id, 'advocate', session['user_id'], filename, file_path, 
                         filename.rsplit('.', 1)[1].lower(), description))
                    conn.commit()
    
    case = conn.execute('''SELECT c.*, cl.name as client_name, cl.email as client_email, cl.phone as client_phone
        FROM cases c JOIN clients cl ON c.client_id = cl.id 
        WHERE c.id = ? AND c.advocate_id = ?''', (case_id, session['user_id'])).fetchone()
    
    documents = conn.execute('SELECT * FROM documents WHERE case_id = ?', (case_id,)).fetchall()
    messages = conn.execute('''SELECT * FROM messages WHERE case_id = ? ORDER BY created_at DESC''', (case_id,)).fetchall()
    
    conn.close()
    
    return render_template('advocate_case_detail.html', case=case, documents=documents, messages=messages)

@app.route('/advocate/clients')
@login_required
def advocate_clients():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    clients = conn.execute('SELECT * FROM clients').fetchall()
    
    # Get case count for each client
    client_cases = {}
    for client in clients:
        case_count = conn.execute('SELECT COUNT(*) FROM cases WHERE client_id = ? AND advocate_id = ?', 
            (client['id'], session['user_id'])).fetchone()[0]
        client_cases[client['id']] = case_count
    
    conn.close()
    
    return render_template('advocate_clients.html', clients=clients, client_cases=client_cases)

@app.route('/advocate/messages', methods=['GET', 'POST'])
@login_required
def advocate_messages():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        receiver_id = request.form['receiver_id']
        message_text = request.form.get('message_text', '')
        case_id = request.form.get('case_id')
        
        # Handle file upload
        file_path = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'advocates', str(session['user_id']))
                os.makedirs(folder_path, exist_ok=True)
                file_path = os.path.join(folder_path, filename)
                file.save(file_path)
        
        # If no message text but file uploaded, set default message
        if not message_text and file_path:
            message_text = f'Sent file: {os.path.basename(file_path)}'
        
        conn.execute('''INSERT INTO messages 
            (sender_type, sender_id, receiver_type, receiver_id, case_id, message_text, message_type, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            ('advocate', session['user_id'], 'client', receiver_id, case_id, message_text, 
             'file' if file_path else 'text', file_path))
        
        # Create notification for client
        conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
            VALUES (?, ?, ?, ?, ?)''',
            ('client', receiver_id, 'New Message', 
             f'You have a new message from Advocate {session["user_name"]}', 'message'))
        
        conn.commit()
    
    messages = conn.execute('''SELECT m.*, c.name as client_name, cl.name as advocate_name
        FROM messages m 
        LEFT JOIN clients c ON m.sender_id = c.id AND m.sender_type = 'client'
        LEFT JOIN advocates cl ON m.sender_id = cl.id AND m.sender_type = 'advocate'
        WHERE (m.receiver_type = 'advocate' AND m.receiver_id = ?) OR (m.sender_type = 'advocate' AND m.sender_id = ?)
        ORDER BY m.created_at DESC''', (session['user_id'], session['user_id'])).fetchall()
    
    clients = conn.execute('SELECT * FROM clients').fetchall()
    cases = conn.execute('''SELECT * FROM cases WHERE advocate_id = ?''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('advocate_messages.html', messages=messages, clients=clients, cases=cases)

@app.route('/advocate/documents')
@login_required
def advocate_documents():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    documents = conn.execute('''SELECT d.*, c.case_number, c.case_type
        FROM documents d JOIN cases c ON d.case_id = c.id
        WHERE c.advocate_id = ?
        ORDER BY d.created_at DESC''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('advocate_documents.html', documents=documents)

@app.route('/advocate/ai-assistant', methods=['GET', 'POST'])
@login_required
def ai_assistant():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        user_message = request.form['message']
        ai_response = get_ai_response(user_message)
        
        # Save chat to database
        conn.execute('''INSERT INTO ai_chats (advocate_id, user_message, ai_response)
            VALUES (?, ?, ?)''',
            (session['user_id'], user_message, ai_response))
        conn.commit()
    
    # Get chat history
    chat_history = conn.execute('''SELECT * FROM ai_chats 
        WHERE advocate_id = ? ORDER BY created_at DESC LIMIT 50''', 
        (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('ai_assistant.html', chat_history=chat_history)

@app.route('/advocate/notifications')
@login_required
def advocate_notifications():
    if session['user_type'] != 'advocate':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    notifications = conn.execute('''SELECT * FROM notifications 
        WHERE user_type = 'advocate' AND user_id = ?
        ORDER BY created_at DESC''', (session['user_id'],)).fetchall()
    
    # Mark as read
    conn.execute('''UPDATE notifications SET is_read = 1 
        WHERE user_type = 'advocate' AND user_id = ?''', (session['user_id'],))
    conn.commit()
    conn.close()
    
    return render_template('advocate_notifications.html', notifications=notifications)

# Client Routes

@app.route('/client/dashboard')
@login_required
def client_dashboard():
    if session['user_type'] != 'client':
        return redirect(url_for('advocate_dashboard'))
    
    conn = get_db_connection()
    
    # Get client's cases
    my_cases = conn.execute('''SELECT * FROM cases WHERE client_id = ? ORDER BY created_at DESC''', 
        (session['user_id'],)).fetchall()
    
    # Get client details for profile
    client = conn.execute('SELECT * FROM clients WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Get advocate details for the client (limited info)
    # First get the advocate_id from any of the client's cases
    case = conn.execute('SELECT DISTINCT advocate_id FROM cases WHERE client_id = ? LIMIT 1', (session['user_id'],)).fetchone()
    advocate = None
    if case:
        advocate = conn.execute('SELECT name, email, phone, address FROM advocates WHERE id = ?', (case['advocate_id'],)).fetchone()
    
    unread_messages = conn.execute('''SELECT COUNT(*) FROM messages 
        WHERE receiver_type = 'client' AND receiver_id = ? AND is_read = 0''', 
        (session['user_id'],)).fetchone()[0]
    
    recent_messages = conn.execute('''SELECT m.*, a.name as advocate_name 
        FROM messages m JOIN advocates a ON m.sender_id = a.id 
        WHERE m.receiver_type = 'client' AND m.receiver_id = ? 
        ORDER BY m.created_at DESC LIMIT 5''', (session['user_id'],)).fetchall()
    
    notifications = conn.execute('''SELECT * FROM notifications 
        WHERE user_type = 'client' AND user_id = ? AND is_read = 0 
        ORDER BY created_at DESC LIMIT 5''', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('client_dashboard.html',
        my_cases=my_cases,
        unread_messages=unread_messages,
        recent_messages=recent_messages,
        notifications=notifications,
        client=client,
        advocate=advocate)

@app.route('/client/messages', methods=['GET', 'POST'])
@login_required
def client_messages():
    if session['user_type'] != 'client':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        message_text = request.form.get('message_text', '')
        case_id = request.form.get('case_id')
        
        # Handle file upload
        file_path = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', str(session['user_id']))
                os.makedirs(folder_path, exist_ok=True)
                file_path = os.path.join(folder_path, filename)
                file.save(file_path)
        
        # If no message text but file uploaded, set default message
        if not message_text and file_path:
            message_text = f'Sent file: {os.path.basename(file_path)}'
        
        # Get advocate ID
        if case_id:
            case = conn.execute('SELECT advocate_id FROM cases WHERE id = ?', (case_id,)).fetchone()
            advocate_id = case['advocate_id'] if case else None
        else:
            advocate_id = 1  # Default advocate
        
        if advocate_id:
            conn.execute('''INSERT INTO messages 
                (sender_type, sender_id, receiver_type, receiver_id, case_id, message_text, message_type, file_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                ('client', session['user_id'], 'advocate', advocate_id, case_id, message_text, 
                 'file' if file_path else 'text', file_path))
            
            # Create notification for advocate
            conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
                VALUES (?, ?, ?, ?, ?)''',
                ('advocate', advocate_id, 'New Message', 
                 f'You have a new message from client {session["user_name"]}', 'message'))
            
            conn.commit()
    
    messages = conn.execute('''SELECT m.*, a.name as advocate_name
        FROM messages m 
        LEFT JOIN advocates a ON m.sender_id = a.id AND m.sender_type = 'advocate'
        WHERE (m.receiver_type = 'client' AND m.receiver_id = ?) OR (m.sender_type = 'client' AND m.sender_id = ?)
        ORDER BY m.created_at DESC''', (session['user_id'], session['user_id'])).fetchall()
    
    cases = conn.execute('SELECT * FROM cases WHERE client_id = ?', (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template('client_messages.html', messages=messages, cases=cases)

@app.route('/client/case/<int:case_id>', methods=['GET', 'POST'])
@login_required
def client_case_detail(case_id):
    if session['user_type'] != 'client':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    case = conn.execute('''SELECT * FROM cases WHERE id = ? AND client_id = ?''', 
        (case_id, session['user_id'])).fetchone()
    
    if not case:
        conn.close()
        return redirect(url_for('client_dashboard'))
    
    if request.method == 'POST':
        # Upload document
        if 'upload_document' in request.form:
            if 'file' in request.files:
                file = request.files['file']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', str(case_id))
                    os.makedirs(folder_path, exist_ok=True)
                    file_path = os.path.join(folder_path, filename)
                    file.save(file_path)
                    
                    description = request.form.get('description', '')
                    conn.execute('''INSERT INTO documents 
                        (case_id, uploaded_by_type, uploaded_by_id, file_name, file_path, file_type, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                        (case_id, 'client', session['user_id'], filename, file_path, 
                         filename.rsplit('.', 1)[1].lower(), description))
                    
                    # Notify advocate
                    conn.execute('''INSERT INTO notifications (user_type, user_id, title, message, notification_type)
                        VALUES (?, ?, ?, ?, ?)''',
                        ('advocate', case['advocate_id'], 'Document Uploaded', 
                         f'Client {session["user_name"]} uploaded document for case {case["case_number"]}', 'document'))
                    
                    conn.commit()
    
    documents = conn.execute('SELECT * FROM documents WHERE case_id = ?', (case_id,)).fetchall()
    messages = conn.execute('''SELECT * FROM messages WHERE case_id = ? ORDER BY created_at DESC''', (case_id,)).fetchall()
    
    conn.close()
    
    return render_template('client_case_detail.html', case=case, documents=documents, messages=messages)

@app.route('/client/notifications')
@login_required
def client_notifications():
    if session['user_type'] != 'client':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    notifications = conn.execute('''SELECT * FROM notifications 
        WHERE user_type = 'client' AND user_id = ?
        ORDER BY created_at DESC''', (session['user_id'],)).fetchall()
    
    # Mark as read
    conn.execute('''UPDATE notifications SET is_read = 1 
        WHERE user_type = 'client' AND user_id = ?''', (session['user_id'],))
    conn.commit()
    conn.close()
    
    return render_template('client_notifications.html', notifications=notifications)

@app.route('/update_client_profile', methods=['POST'])
@login_required
def update_client_profile():
    if session['user_type'] != 'client':
        return redirect(url_for('login'))
    
    name = request.form['name']
    email = request.form['email']
    phone = request.form.get('phone', '')
    address = request.form.get('address', '')
    aadhar_number = request.form.get('aadhar_number', '')
    
    # Handle profile image upload
    profile_image = None
    if 'profile_image' in request.files:
        file = request.files['profile_image']
        if file and file.filename != '' and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            folder_path = os.path.join(app.config['UPLOAD_FOLDER'], 'clients', str(session['user_id']))
            os.makedirs(folder_path, exist_ok=True)
            profile_image = filename
            file.save(os.path.join(folder_path, filename))
    
    conn = get_db_connection()
    
    # Build update query dynamically
    update_fields = ['name = ?', 'email = ?', 'phone = ?', 'address = ?', 'aadhar_number = ?']
    values = [name, email, phone, address, aadhar_number]
    
    if profile_image:
        update_fields.append('profile_image = ?')
        values.append(profile_image)
    
    values.append(session['user_id'])  # for WHERE clause
    
    query = f'''UPDATE clients SET {', '.join(update_fields)} WHERE id = ?'''
    conn.execute(query, values)
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('client_dashboard'))

# API Routes for real-time features

@app.route('/api/mark-message-read/<int:message_id>')
@login_required
def mark_message_read(message_id):
    conn = get_db_connection()
    conn.execute('UPDATE messages SET is_read = 1 WHERE id = ?', (message_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/upload-message-file', methods=['POST'])
@login_required
def upload_message_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'})
    
    file = request.files['file']
    receiver_id = request.form['receiver_id']
    case_id = request.form.get('case_id')
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        folder = 'clients' if session['user_type'] == 'client' else 'advocates'
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder, str(session['user_id']))
        os.makedirs(folder_path, exist_ok=True)
        file_path = os.path.join(folder_path, filename)
        file.save(file_path)
        
        conn = get_db_connection()
        receiver_type = 'client' if session['user_type'] == 'advocate' else 'advocate'
        
        conn.execute('''INSERT INTO messages 
            (sender_type, sender_id, receiver_type, receiver_id, case_id, message_text, message_type, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (session['user_type'], session['user_id'], receiver_type, receiver_id, case_id, 
             f'Sent file: {filename}', 'file', file_path))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'file_path': file_path})
    
    return jsonify({'error': 'Invalid file'})

# Download document
@app.route('/download/<int:doc_id>')
@login_required
def download_document(doc_id):
    conn = get_db_connection()
    doc = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    conn.close()
    
    if doc:
        return send_file(doc['file_path'], as_attachment=True)
    return 'Document not found'

if __name__ == '__main__':
    app.run(debug=True)
