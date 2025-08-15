from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loan_applications.db'
app.config['UPLOAD_FOLDER'] = 'documents'
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.example.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@example.com'
app.config['MAIL_PASSWORD'] = 'your-password'
app.config['MAIL_DEFAULT_SENDER'] = 'loans@example.com'

db = SQLAlchemy(app)
mail = Mail(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    applicant_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    loan_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='New')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='application', lazy=True)
    documents = db.relationship('Document', backref='application', lazy=True)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    due_date = db.Column(db.DateTime)
    completed = db.Column(db.Boolean, default=False)
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'))

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50))
    application_id = db.Column(db.Integer, db.ForeignKey('application.id'))
    signed = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def send_status_email(application, new_status):
    try:
        msg = Message(f"Loan Application #{application.id} Status Update",
                      recipients=[application.email])
        msg.body = f"Hello {application.applicant_name},\n\n" \
                   f"Your loan application (ID: {application.id}) status has been updated to: {new_status}.\n\n" \
                   f"Thank you,\nLoan Management Team"
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Failed to send email: {str(e)}")

@app.route('/')
def home():
    return redirect(url_for('application_form'))

@app.route('/apply')
def application_form():
    return render_template('application.html')

@app.route('/submit', methods=['POST'])
def submit_application():
    applicant_name = request.form['name']
    email = request.form['email']
    loan_amount = float(request.form['amount'])
    
    new_app = Application(
        applicant_name=applicant_name,
        email=email,
        loan_amount=loan_amount
    )
    
    db.session.add(new_app)
    db.session.commit()
    create_standard_tasks(new_app)
    return redirect(url_for('dashboard'))

def create_standard_tasks(application):
    tasks = [
        ("Initial Review", 1),
        ("Document Verification", 2),
        ("Credit Check", 3),
        ("Approval Meeting", 5),
        ("Funds Disbursement", 7)
    ]
    
    for task_name, days_delta in tasks:
        new_task = Task(
            name=task_name,
            due_date=datetime.utcnow() + timedelta(days=days_delta),
            application_id=application.id
        )
        db.session.add(new_task)
    db.session.commit()

@app.route('/dashboard')
def dashboard():
    applications = Application.query.all()
    return render_template('dashboard.html', applications=applications)

@app.route('/update_status/<int:app_id>/<status>')
def update_status(app_id, status):
    app = Application.query.get(app_id)
    if app:
        app.status = status
        db.session.commit()
        send_status_email(app, status)
    return redirect(url_for('dashboard'))

@app.route('/application/<int:app_id>')
def application_detail(app_id):
    app = Application.query.get_or_404(app_id)
    return render_template('application_detail.html', application=app)

@app.route('/upload/<int:app_id>', methods=['POST'])
def upload_document(app_id):
    if 'document' not in request.files:
        return 'No file part', 400
        
    file = request.files['document']
    if file.filename == '':
        return 'No selected file', 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        new_doc = Document(
            filename=filename,
            application_id=app_id,
            category=request.form.get('category', 'Other')
        )
        db.session.add(new_doc)
        db.session.commit()
        return redirect(url_for('application_detail', app_id=app_id))
    
    return 'Invalid file type', 400

@app.route('/documents/<filename>')
def download_document(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/sign_document/<int:doc_id>')
def sign_document(doc_id):
    doc = Document.query.get(doc_id)
    if doc:
        doc.signed = True
        db.session.commit()
    return redirect(url_for('application_detail', app_id=doc.application_id))

@app.route('/complete_task/<int:task_id>')
def complete_task(task_id):
    task = Task.query.get(task_id)
    if task:
        task.completed = True
        db.session.commit()
    return redirect(url_for('application_detail', app_id=task.application_id))

if __name__ == '__main__':
    app.run(debug=True, port=5001)