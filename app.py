# app.py

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, IntegerField, FloatField, DateField, SelectField, SubmitField, PasswordField
from wtforms.validators import DataRequired, NumberRange, Email, Length
import os
from datetime import datetime, timedelta
from collections import defaultdict
from firebase_admin import credentials, initialize_app, auth, firestore
from dotenv import load_dotenv
import secrets
import json
import logging
import traceback
import time
from functools import wraps
import sys
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
csrf = CSRFProtect(app)

# Initialize Firebase with retry mechanism
def initialize_firebase(max_retries=3, delay=1):
    for attempt in range(max_retries):
        try:
            firebase_credentials = os.getenv('FIREBASE_CREDENTIALS')
            if not firebase_credentials:
                logger.error("FIREBASE_CREDENTIALS environment variable is not set")
                raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")
            
            try:
                cred_dict = json.loads(firebase_credentials)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in FIREBASE_CREDENTIALS: {str(e)}")
                raise ValueError("Invalid JSON in FIREBASE_CREDENTIALS")
            
            cred = credentials.Certificate(cred_dict)
            firebase_app = initialize_app(cred)
            db = firestore.client()
            logger.info("Firebase initialized successfully")
            return db
        except Exception as e:
            logger.error(f"Firebase initialization attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                logger.error("All Firebase initialization attempts failed")
                raise

# Initialize Firebase
try:
    db = initialize_firebase()
except Exception as e:
    logger.error(f"Critical error: Could not initialize Firebase: {str(e)}")
    logger.error(traceback.format_exc())
    raise

# Database connection decorator
def with_db_connection(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Database error in {f.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            flash('A database error occurred. Please try again later.', 'error')
            return render_template('error.html', error="Database connection error. Please try again later."), 500
    return decorated_function

# Session management
@app.before_request
def before_request():
    if 'username' in session:
        # Check if the session is still valid
        try:
            user = auth.get_user_by_email(session.get('email'))
            if not user:
                session.clear()
                flash('Session expired. Please login again.', 'error')
                return redirect(url_for('index'))
        except Exception as e:
            logger.error(f"Session validation error: {str(e)}")
            session.clear()
            flash('Session error. Please login again.', 'error')
            return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal Server Error: {str(error)}")
    logger.error(traceback.format_exc())
    return render_template('error.html', error="An internal server error occurred. Please try again later."), 500

@app.errorhandler(404)
def not_found_error(error):
    logger.error(f"Not Found Error: {str(error)}")
    return render_template('error.html', error="The requested page was not found."), 404

@app.errorhandler(502)
def bad_gateway_error(error):
    logger.error(f"Bad Gateway Error: {str(error)}")
    return render_template('error.html', error="Service temporarily unavailable. Please try again later."), 502

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
    customerName = StringField('Customer Name', validators=[DataRequired(), Length(min=2, max=100)])
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
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            logger.error(traceback.format_exc())
            flash('Invalid credentials.', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/dashboard')
@with_db_connection
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))

    try:
        # Initialize default values
        total_sales = 0
        paid_expenses = 0
        pending_expenses = 0
        net_income = 0

        # Get sales data
        try:
            sales = [doc.to_dict() for doc in db.collection('sales').stream()]
            total_sales = sum(float(s.get('sale_amount', 0) or 0) for s in sales)
        except Exception as e:
            logger.error(f"Error getting sales data: {str(e)}")
            sales = []

        # Get expenses data
        try:
            expenses = [doc.to_dict() for doc in db.collection('expenses').stream()]
            paid_expenses = sum(float(e.get('amount', 0) or 0) for e in expenses if e.get('status') == 'Paid')
            pending_expenses = sum(float(e.get('amount', 0) or 0) for e in expenses if e.get('status') == 'Pending')
        except Exception as e:
            logger.error(f"Error getting expenses data: {str(e)}")
            expenses = []

        # Calculate net income
        net_income = total_sales - paid_expenses

        # Format numbers to ensure they are valid
        total_sales = float(total_sales or 0)
        paid_expenses = float(paid_expenses or 0)
        pending_expenses = float(pending_expenses or 0)
        net_income = float(net_income or 0)

        return render_template('dashboard.html', 
                             username=session['username'],
                             total_sales=total_sales,
                             paid_expenses=paid_expenses,
                             pending_expenses=pending_expenses,
                             net_income=net_income)
    except Exception as e:
        logger.error(f"Error in dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error loading dashboard data. Please try again later.', 'error')
        return render_template('error.html', error="Error loading dashboard data. Please try again later."), 500

# ------------------ Sales ------------------ #
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if 'username' not in session:
        return redirect(url_for('index'))
    form = SalesForm()
    if form.validate_on_submit():
        try:
            sale_amount = float(form.quantity.data) * float(form.pricePerUnit.data)
            data = {
                'customer_name': form.customerName.data,
                'quantity': int(form.quantity.data),
                'price_per_unit': float(form.pricePerUnit.data),
                'sale_date': form.saleDate.data.strftime('%Y-%m-%d'),
                'sale_amount': sale_amount,
                'status': form.saleStatus.data
            }
            db.collection('sales').add(data)
            flash('Sale added successfully.', 'success')
            return redirect(url_for('sales'))
        except Exception as e:
            logger.error(f"Error adding sale: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f'Error adding sale: {str(e)}', 'error')
            return redirect(url_for('sales'))

    try:
        sales_docs = db.collection('sales').stream()
        sales_data = []
        monthly_sales = defaultdict(float)
        for doc in sales_docs:
            sale = doc.to_dict()
            sale['id'] = doc.id
            # Ensure all required fields exist with default values
            sale['customer_name'] = sale.get('customer_name', '')
            sale['quantity'] = sale.get('quantity', 0)
            sale['price_per_unit'] = float(sale.get('price_per_unit', 0))
            sale['sale_amount'] = float(sale.get('sale_amount', 0))
            sale['sale_date'] = sale.get('sale_date', '')
            sale['status'] = sale.get('status', 'Pending')
            sales_data.append(sale)
            # Only count paid sales in the monthly total
            if sale['status'] == 'Paid':
                dt = datetime.strptime(sale['sale_date'], '%Y-%m-%d')
                monthly_sales[dt.strftime('%b %Y')] += sale['sale_amount']
        
        sorted_data = sorted(monthly_sales.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))
        chart_labels = [k for k, _ in sorted_data]
        chart_data = [v for _, v in sorted_data]

        return render_template('sales.html', username=session['username'], sales=sales_data,
                            form=form, chart_labels=chart_labels, chart_data=chart_data)
    except Exception as e:
        logger.error(f"Error loading sales: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error loading sales: {str(e)}', 'error')
        return render_template('sales.html', username=session['username'], sales=[],
                            form=form, chart_labels=[], chart_data=[])

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
        try:
            data = {
                'name': form.expenseName.data,
                'amount': float(form.expenseAmount.data),
                'date': form.expenseDate.data.strftime('%Y-%m-%d'),
                'status': form.expenseStatus.data
            }
            db.collection('expenses').add(data)
            flash('Expense added successfully.', 'success')
            return redirect(url_for('expenses'))
        except Exception as e:
            logger.error(f"Error adding expense: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f'Error adding expense: {str(e)}', 'error')
            return redirect(url_for('expenses'))

    try:
        docs = db.collection('expenses').stream()
        expenses_data = []
        monthly = defaultdict(float)
        for doc in docs:
            e = doc.to_dict()
            e['id'] = doc.id
            # Ensure all required fields exist with default values
            e['name'] = e.get('name', '')
            e['amount'] = float(e.get('amount', 0))
            e['date'] = e.get('date', '')
            e['status'] = e.get('status', 'Pending')
            expenses_data.append(e)
            dt = datetime.strptime(e['date'], '%Y-%m-%d')
            monthly[dt.strftime('%b %Y')] += e['amount']

        sorted_data = sorted(monthly.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))
        labels = [k for k, _ in sorted_data]
        data = [v for _, v in sorted_data]

        return render_template('expenses.html', username=session['username'], expenses=expenses_data,
                            form=form, chart_labels=labels, chart_data=data)
    except Exception as e:
        logger.error(f"Error loading expenses: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error loading expenses: {str(e)}', 'error')
        return render_template('expenses.html', username=session['username'], expenses=[],
                            form=form, chart_labels=[], chart_data=[])

@app.route('/expenses/delete/<string:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'username' not in session:
        return redirect(url_for('index'))
    try:
        if not expense_id:
            flash('Invalid expense ID.', 'error')
            return redirect(url_for('expenses'))
            
        # Check if the expense exists before deleting
        expense_ref = db.collection('expenses').document(expense_id)
        expense = expense_ref.get()
        
        if not expense.exists:
            flash('Expense not found.', 'error')
            return redirect(url_for('expenses'))
            
        expense_ref.delete()
        flash('Expense deleted successfully.', 'success')
    except Exception as e:
        logger.error(f"Error deleting expense: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error deleting expense: {str(e)}', 'error')
        
    return redirect(url_for('expenses'))

# ------------------ Calendar / Tasks ------------------ #
@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    try:
        if 'username' not in session:
            logger.warning("Unauthorized access attempt to calendar")
            return redirect(url_for('index'))
        
        form = TaskForm()
        if form.validate_on_submit():
            try:
                # Safely handle datetime
                date_str = form.taskDate.data.strftime('%Y-%m-%d')
                time_str = form.taskTime.data.strip() if form.taskTime.data else ''
                dt_str = f"{date_str} {time_str}" if time_str else date_str
                
                # Safely handle price
                try:
                    price = float(form.taskPrice.data or 0)
                except (ValueError, TypeError):
                    price = 0.0
                
                task_data = {
                    'name': form.taskName.data,
                    'datetime': dt_str,
                    'priority': form.taskPriority.data,
                    'done': False,
                    'price': price
                }
                db.collection('calendar_tasks').add(task_data)
                logger.info(f"Task added successfully: {task_data['name']}")
                flash('Task added.', 'success')
            except Exception as e:
                logger.error(f"Error adding task: {str(e)}")
                logger.error(traceback.format_exc())
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
                try:
                    task['price'] = float(task.get('price', 0))
                except (ValueError, TypeError):
                    task['price'] = 0.0
                tasks.append(task)
            logger.info(f"Successfully loaded {len(tasks)} tasks")
            return render_template('calendar.html', username=session['username'], tasks=tasks, form=form)
        except Exception as e:
            logger.error(f"Error loading tasks: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f'Error loading tasks: {str(e)}', 'error')
            return render_template('calendar.html', username=session['username'], tasks=[], form=form)
    except Exception as e:
        logger.error(f"Unexpected error in calendar route: {str(e)}")
        logger.error(traceback.format_exc())
        flash('An unexpected error occurred.', 'error')
        return redirect(url_for('dashboard'))

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
    try:
        ref = db.collection('calendar_tasks').document(task_id)
        task = ref.get()
        if not task.exists:
            flash('Task not found.', 'error')
            return redirect(url_for('calendar'))

        name = request.form.get('taskName')
        date = request.form.get('taskDate')
        time = request.form.get('taskTime', '').strip()
        priority = request.form.get('taskPriority')
        
        # Safely handle price
        try:
            price = float(request.form.get('taskPrice', 0))
        except (ValueError, TypeError):
            price = 0.0

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
    except Exception as e:
        logger.error(f"Error updating task: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f'Error updating task: {str(e)}', 'error')
    return redirect(url_for('calendar'))

@app.route('/api/chart-data')
@with_db_connection
def get_chart_data():
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({'error': 'Start date and end date are required'}), 400
            
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
        end_date = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Get sales data
        sales = [doc.to_dict() for doc in db.collection('sales').stream()]
        expenses = [doc.to_dict() for doc in db.collection('expenses').stream()]
        
        # Initialize data structures
        daily_sales = defaultdict(float)
        daily_pending = defaultdict(float)
        daily_expenses_paid = defaultdict(float)
        daily_expenses_pending = defaultdict(float)
        
        # Process sales data
        for sale in sales:
            try:
                sale_date = datetime.strptime(sale.get('sale_date', ''), '%Y-%m-%d')
                if start_date <= sale_date <= end_date:
                    amount = float(sale.get('sale_amount', 0) or 0)
                    if sale.get('status') == 'Paid':
                        daily_sales[sale_date.strftime('%Y-%m-%d')] += amount
                    else:
                        daily_pending[sale_date.strftime('%Y-%m-%d')] += amount
            except (ValueError, TypeError) as e:
                logger.error(f"Error processing sale data: {str(e)}")
                continue
        
        # Process expenses data
        for expense in expenses:
            try:
                expense_date = datetime.strptime(expense.get('date', ''), '%Y-%m-%d')
                if start_date <= expense_date <= end_date:
                    amount = float(expense.get('amount', 0) or 0)
                    if expense.get('status') == 'Paid':
                        daily_expenses_paid[expense_date.strftime('%Y-%m-%d')] += amount
                    else:
                        daily_expenses_pending[expense_date.strftime('%Y-%m-%d')] += amount
            except (ValueError, TypeError) as e:
                logger.error(f"Error processing expense data: {str(e)}")
                continue
        
        # Generate date range
        date_range = []
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            date_range.append(date_str)
            current_date += timedelta(days=1)
        
        # Prepare response data
        response_data = {
            'labels': date_range,
            'daily_sales': [daily_sales.get(date, 0) for date in date_range],
            'daily_pending': [daily_pending.get(date, 0) for date in date_range],
            'daily_expenses_paid': [daily_expenses_paid.get(date, 0) for date in date_range],
            'daily_expenses_pending': [daily_expenses_pending.get(date, 0) for date in date_range]
        }
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Error generating chart data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': 'Error generating chart data'}), 500

# ------------------ Run App ------------------ #
if __name__ == '__main__':
    # Set up proper logging for production
    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
    app.run(debug=False)
