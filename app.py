# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, IntegerField, FloatField, DateField, SelectField, SubmitField, PasswordField
from wtforms.validators import DataRequired, NumberRange, Email, Length
import os
from datetime import datetime
from collections import defaultdict
from firebase_admin import credentials, initialize_app, auth, firestore
from dotenv import load_dotenv
import secrets
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
csrf = CSRFProtect(app)

# Initialize Firebase
try:
    # Get credentials from environment variable
    firebase_credentials = os.getenv('FIREBASE_CREDENTIALS')
    if not firebase_credentials:
        raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")
    
    # Parse the JSON string from environment variable
    cred_dict = json.loads(firebase_credentials)
    cred = credentials.Certificate(cred_dict)
    firebase_app = initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Firebase initialization error: {str(e)}")
    raise

# ------------------ Forms ------------------ #
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired()])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SalesForm(FlaskForm):
    customerName = StringField('Customer Name', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    pricePerUnit = FloatField('Price per Unit', validators=[DataRequired(), NumberRange(min=0)])
    saleDate = DateField('Sale Date', validators=[DataRequired()])
    saleStatus = SelectField('Status', choices=[('Paid', 'Paid'), ('Pending', 'Pending')], validators=[DataRequired()])
    submit = SubmitField('Submit Sale')

class ExpensesForm(FlaskForm):
    expenseName = StringField('Expense Name', validators=[DataRequired()])
    expenseAmount = FloatField('Expense Amount', validators=[DataRequired(), NumberRange(min=0)])
    expenseDate = DateField('Expense Date', validators=[DataRequired()])
    expenseStatus = SelectField('Status', choices=[('Paid', 'Paid'), ('Pending', 'Pending')], validators=[DataRequired()])
    submit = SubmitField('Submit Expense')

class TaskForm(FlaskForm):
    taskName = StringField('Task Name', validators=[DataRequired()])
    taskDate = DateField('Task Date', validators=[DataRequired()])
    taskTime = StringField('Task Time (optional)')
    taskPriority = SelectField('Priority', choices=[('normal', 'Normal'), ('high', 'High')], validators=[DataRequired()])
    taskPrice = FloatField('Price (THB)', validators=[NumberRange(min=0)], default=0)
    submit = SubmitField('Add Task')

# ------------------ Routes ------------------ #

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html', form=LoginForm())

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.password.data != form.confirm_password.data:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
        try:
            user = auth.create_user(
                email=form.email.data,
                password=form.password.data,
                display_name=form.username.data,
                email_verified=False
            )
            db.collection('users').document(user.uid).set({
                'username': form.username.data,
                'email': form.email.data,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'role': 'user'
            })
            flash('Registration successful. Please login.', 'success')
            return redirect(url_for('index'))
        except auth.EmailAlreadyExistsError:
            flash('Email already registered.', 'error')
        except Exception as e:
            flash(f'Registration error: {str(e)}', 'error')
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = auth.get_user_by_email(form.email.data)
            user_doc = db.collection('users').document(user.uid).get()
            if user_doc.exists:
                session['username'] = user.display_name
                session['email'] = user.email
                session['user_id'] = user.uid
                flash('Login successful.', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('User data missing in Firestore.', 'error')
        except auth.UserNotFoundError:
            flash('User not found. Please register.', 'error')
        except Exception:
            flash('Invalid credentials.', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))

    sales = [doc.to_dict() for doc in db.collection('sales').stream()]
    total_sales = sum(s.get('sale_amount', 0) for s in sales)

    expenses = [doc.to_dict() for doc in db.collection('expenses').stream()]
    paid = sum(e.get('amount', 0) for e in expenses if e.get('status') == 'Paid')
    pending = sum(e.get('amount', 0) for e in expenses if e.get('status') == 'Pending')

    net_income = total_sales - paid

    return render_template('dashboard.html', username=session['username'], total_sales=total_sales,
                           paid_expenses=paid, pending_expenses=pending, net_income=net_income)

# ------------------ Sales ------------------ #
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if 'username' not in session:
        return redirect(url_for('index'))
    form = SalesForm()
    if form.validate_on_submit():
        data = {
            'customer_name': form.customerName.data,
            'quantity': form.quantity.data,
            'price_per_unit': form.pricePerUnit.data,
            'sale_date': form.saleDate.data.strftime('%Y-%m-%d'),
            'sale_amount': form.quantity.data * form.pricePerUnit.data,
            'status': form.saleStatus.data
        }
        db.collection('sales').add(data)
        flash('Sale added.', 'success')
        return redirect(url_for('sales'))

    sales_docs = db.collection('sales').stream()
    sales_data = []
    monthly_sales = defaultdict(float)
    for doc in sales_docs:
        sale = doc.to_dict()
        sale['id'] = doc.id
        sales_data.append(sale)
        # Only count paid sales in the monthly total
        if sale.get('status') == 'Paid':
            dt = datetime.strptime(sale['sale_date'], '%Y-%m-%d')
            monthly_sales[dt.strftime('%b %Y')] += sale.get('sale_amount', 0)
    
    sorted_data = sorted(monthly_sales.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))
    chart_labels = [k for k, _ in sorted_data]
    chart_data = [v for _, v in sorted_data]

    return render_template('sales.html', username=session['username'], sales=sales_data,
                           form=form, chart_labels=chart_labels, chart_data=chart_data)

@app.route('/sales/delete/<string:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    try:
        if not sale_id:
            flash('Invalid sale ID.', 'error')
            return redirect(url_for('sales'))
            
        # Check if the sale exists before deleting
        sale_ref = db.collection('sales').document(sale_id)
        sale = sale_ref.get()
        
        if not sale.exists:
            flash('Sale not found.', 'error')
            return redirect(url_for('sales'))
            
        sale_ref.delete()
        flash('Sale deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting sale: {str(e)}', 'error')
        print(f"Error deleting sale: {str(e)}")  # For server-side logging
        
    return redirect(url_for('sales'))

@app.route('/sales/update_status/<string:sale_id>', methods=['POST'])
def update_sale_status(sale_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    
    ref = db.collection('sales').document(sale_id)
    sale = ref.get()
    if not sale.exists:
        flash('Sale not found.', 'error')
        return redirect(url_for('sales'))
    
    new_status = request.form.get('status')
    if new_status not in ['Paid', 'Pending']:
        flash('Invalid status.', 'error')
        return redirect(url_for('sales'))
    
    ref.update({'status': new_status})
    flash('Sale status updated.', 'success')
    return redirect(url_for('sales'))

# ------------------ Expenses ------------------ #
@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if 'username' not in session:
        return redirect(url_for('index'))
    form = ExpensesForm()
    if form.validate_on_submit():
        db.collection('expenses').add({
            'name': form.expenseName.data,
            'amount': form.expenseAmount.data,
            'date': form.expenseDate.data.strftime('%Y-%m-%d'),
            'status': form.expenseStatus.data
        })
        flash('Expense added.', 'success')
        return redirect(url_for('expenses'))

    docs = db.collection('expenses').stream()
    expenses_data = []
    monthly = defaultdict(float)
    for doc in docs:
        e = doc.to_dict()
        e['id'] = doc.id
        expenses_data.append(e)
        dt = datetime.strptime(e['date'], '%Y-%m-%d')
        monthly[dt.strftime('%b %Y')] += e.get('amount', 0)

    sorted_data = sorted(monthly.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))
    labels = [k for k, _ in sorted_data]
    data = [v for _, v in sorted_data]

    return render_template('expenses.html', username=session['username'], expenses=expenses_data,
                           form=form, chart_labels=labels, chart_data=data)

@app.route('/expenses/delete/<string:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    db.collection('expenses').document(expense_id).delete()
    flash('Expense deleted.', 'success')
    return redirect(url_for('expenses'))

# ------------------ Calendar / Tasks ------------------ #
@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    if 'username' not in session:
        return redirect(url_for('index'))
    form = TaskForm()
    if form.validate_on_submit():
        try:
            dt_str = f"{form.taskDate.data.strftime('%Y-%m-%d')} {form.taskTime.data.strip()}" if form.taskTime.data else form.taskDate.data.strftime('%Y-%m-%d')
            task_data = {
                'name': form.taskName.data,
                'datetime': dt_str,
                'priority': form.taskPriority.data,
                'done': False,
                'price': float(form.taskPrice.data or 0)
            }
            db.collection('calendar_tasks').add(task_data)
            flash('Task added.', 'success')
        except Exception as e:
            flash(f'Error adding task: {str(e)}', 'error')
        return redirect(url_for('calendar'))

    try:
        docs = db.collection('calendar_tasks').stream()
        tasks = []
        for doc in docs:
            task = doc.to_dict()
            task['id'] = doc.id
            # Ensure all required fields exist with default values
            task['name'] = task.get('name', '')
            task['datetime'] = task.get('datetime', '')
            task['priority'] = task.get('priority', 'normal')
            task['done'] = task.get('done', False)
            task['price'] = float(task.get('price', 0))
            tasks.append(task)
        return render_template('calendar.html', username=session['username'], tasks=tasks, form=form)
    except Exception as e:
        flash(f'Error loading tasks: {str(e)}', 'error')
        return render_template('calendar.html', username=session['username'], tasks=[], form=form)

@app.route('/calendar/update_task_status', methods=['POST'])
def update_task_status():
    task_id = request.form.get('task_id')
    if not task_id:
        flash('Task ID missing.', 'error')
        return redirect(url_for('calendar'))

    ref = db.collection('calendar_tasks').document(task_id)
    task = ref.get()
    if not task.exists:
        flash('Task not found.', 'error')
        return redirect(url_for('calendar'))
    
    current_status = task.to_dict().get('done', False)
    ref.update({'done': not current_status})
    flash('Task status updated.', 'success')
    return redirect(url_for('calendar'))

@app.route('/calendar/delete/<string:task_id>', methods=['POST'])
def delete_task(task_id):
    db.collection('calendar_tasks').document(task_id).delete()
    flash('Task deleted.', 'success')
    return redirect(url_for('calendar'))

@app.route('/calendar/edit/<string:task_id>', methods=['POST'])
def edit_task(task_id):
    ref = db.collection('calendar_tasks').document(task_id)
    if not ref.get().exists:
        flash('Task not found.', 'error')
        return redirect(url_for('calendar'))

    name = request.form.get('taskName')
    date = request.form.get('taskDate')
    time = request.form.get('taskTime', '').strip()
    priority = request.form.get('taskPriority')
    price = float(request.form.get('taskPrice', 0))

    if not name or not date or not priority:
        flash('Missing required fields.', 'error')
        return redirect(url_for('calendar'))

    dt_str = f"{date} {time}" if time else date
    ref.update({
        'name': name,
        'datetime': dt_str,
        'priority': priority,
        'price': price
    })
    flash('Task updated.', 'success')
    return redirect(url_for('calendar'))

# ------------------ Run App ------------------ #
if __name__ == '__main__':
    app.run(debug=False)
