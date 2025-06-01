from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, IntegerField, FloatField, DateField, SelectField, SubmitField, PasswordField
from wtforms.validators import DataRequired, NumberRange, Email, Length
import os
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.secret_key = os.urandom(24)
csrf = CSRFProtect(app)

import firebase_admin
from firebase_admin import credentials, firestore, auth

# Initialize Firebase Admin SDK
cred = credentials.Certificate('firebase/amornratice-43410-firebase-adminsdk-fbsvc-765820c7a6.json')
firebase_admin.initialize_app(cred)

db = firestore.client()

# Add User Registration Form
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired()])
    submit = SubmitField('Register')

# Add Login Form
class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

# WTForms (unchanged)
class SalesForm(FlaskForm):
    customerName = StringField('Customer Name', validators=[DataRequired()])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    pricePerUnit = FloatField('Price per Unit', validators=[DataRequired(), NumberRange(min=0)])
    saleDate = DateField('Sale Date', validators=[DataRequired()])
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
    submit = SubmitField('Add Task')

@app.route('/')
def index():
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        if form.password.data != form.confirm_password.data:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
        
        try:
            # Create user in Firebase Authentication
            user = auth.create_user(
                email=form.email.data,
                password=form.password.data,
                display_name=form.username.data,
                email_verified=False
            )
            
            # Store additional user data in Firestore
            user_data = {
                'username': form.username.data,
                'email': form.email.data,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'role': 'user'
            }
            
            # Add user data to Firestore
            db.collection('users').document(user.uid).set(user_data)
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('index'))
            
        except auth.EmailAlreadyExistsError:
            flash('This email is already registered. Please login instead.', 'error')
            return redirect(url_for('index'))
        except auth.InvalidPasswordError:
            flash('Password is too weak. Please use a stronger password.', 'error')
            return redirect(url_for('register'))
        except Exception as e:
            print(f"Registration error: {str(e)}")  # For debugging
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('register'))
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            # Get user by email
            user = auth.get_user_by_email(form.email.data)
            
            # Get user data from Firestore
            user_doc = db.collection('users').document(user.uid).get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                # Store user info in session
                session['username'] = user_data['username']
                session['user_id'] = user.uid
                session['email'] = user_data['email']
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('User data not found. Please contact support.', 'error')
                return redirect(url_for('index'))
                
        except auth.UserNotFoundError:
            flash('No account found with this email. Please register first.', 'error')
            return redirect(url_for('register'))
        except Exception as e:
            print(f"Login error: {str(e)}")  # For debugging
            flash('Invalid email or password.', 'error')
            return redirect(url_for('index'))
    
    return render_template('login.html', form=form)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('index'))

    # Fetch and calculate sales data
    sales_docs = db.collection('sales').stream()
    sales_data = [doc.to_dict() for doc in sales_docs]
    total_sales = sum(sale.get('sale_amount', 0) for sale in sales_data)

    # Fetch and calculate expense data
    expenses_docs = db.collection('expenses').stream()
    expenses_data = [doc.to_dict() for doc in expenses_docs]

    paid_expenses = sum(exp.get('amount', 0) for exp in expenses_data if exp.get('status') == 'Paid')
    pending_expenses = sum(exp.get('amount', 0) for exp in expenses_data if exp.get('status') == 'Pending')

    # Calculate net profit or net income
    net_income = total_sales - paid_expenses

    return render_template('dashboard.html',
                           username=session['username'],
                           total_sales=total_sales,
                           paid_expenses=paid_expenses,
                           pending_expenses=pending_expenses,
                           net_income=net_income)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

# --- Sales Routes ---
@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if 'username' not in session:
        return redirect(url_for('index'))

    form = SalesForm()
    if form.validate_on_submit():
        customer_name = form.customerName.data
        quantity = form.quantity.data
        price_per_unit = form.pricePerUnit.data
        sale_date = form.saleDate.data.strftime('%Y-%m-%d')
        sale_amount = quantity * price_per_unit

        sale_doc = {
            'customer_name': customer_name,
            'quantity': quantity,
            'price_per_unit': price_per_unit,
            'sale_amount': sale_amount,
            'sale_date': sale_date
        }

        db.collection('sales').add(sale_doc)
        flash('Sale added successfully.', 'success')
        return redirect(url_for('sales'))

    # Get all sales from Firestore
    sales_docs = db.collection('sales').stream()
    sales_data = []
    monthly_sales = defaultdict(float)  # For aggregating sales by month

    for doc in sales_docs:
        sale = doc.to_dict()
        sale['id'] = doc.id  # Add document ID for deletion
        sales_data.append(sale)

        # Aggregate sales amount per month-year
        dt = datetime.strptime(sale['sale_date'], '%Y-%m-%d')
        month_year = dt.strftime('%b %Y')  # e.g. 'May 2025'
        monthly_sales[month_year] += sale.get('sale_amount', 0)

    # Sort monthly sales by datetime ascending
    sorted_monthly_sales = sorted(monthly_sales.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))

    # Separate labels and values for Chart.js
    chart_labels = [item[0] for item in sorted_monthly_sales]
    chart_data = [item[1] for item in sorted_monthly_sales]

    return render_template('sales.html', username=session['username'], sales=sales_data, form=form,
                           chart_labels=chart_labels, chart_data=chart_data)

@app.route('/sales/delete/<string:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    if 'username' not in session:
        return redirect(url_for('index'))

    try:
        db.collection('sales').document(sale_id).delete()
        flash('Sale deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting sale: {str(e)}', 'error')

    return redirect(url_for('sales'))

# --- Expenses Routes ---
@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if 'username' not in session:
        return redirect(url_for('index'))

    form = ExpensesForm()
    if form.validate_on_submit():
        expense_doc = {
            'name': form.expenseName.data,
            'amount': form.expenseAmount.data,
            'date': form.expenseDate.data.strftime('%Y-%m-%d'),
            'status': form.expenseStatus.data
        }

        db.collection('expenses').add(expense_doc)
        flash('Expense added successfully.', 'success')
        return redirect(url_for('expenses'))

    # Get all expenses from Firestore
    expenses_docs = db.collection('expenses').stream()
    expenses_data = []
    monthly_expenses = defaultdict(float)  # For aggregating expenses by month

    for doc in expenses_docs:
        expense = doc.to_dict()
        expense['id'] = doc.id
        expenses_data.append(expense)

        # Aggregate expenses amount per month-year
        dt = datetime.strptime(expense['date'], '%Y-%m-%d')
        month_year = dt.strftime('%b %Y')  # e.g. 'May 2025'
        monthly_expenses[month_year] += expense.get('amount', 0)

    # Sort monthly expenses by datetime ascending
    sorted_monthly_expenses = sorted(monthly_expenses.items(), key=lambda x: datetime.strptime(x[0], '%b %Y'))

    # Separate labels and values for Chart.js
    chart_labels = [item[0] for item in sorted_monthly_expenses]
    chart_data = [item[1] for item in sorted_monthly_expenses]

    return render_template('expenses.html', 
                         username=session['username'], 
                         expenses=expenses_data, 
                         form=form,
                         chart_labels=chart_labels, 
                         chart_data=chart_data)

@app.route('/expenses/delete/<string:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'username' not in session:
        return redirect(url_for('index'))

    try:
        db.collection('expenses').document(expense_id).delete()
        flash('Expense deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting expense: {str(e)}', 'error')

    return redirect(url_for('expenses'))

# --- Calendar / Tasks Routes ---
@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    if 'username' not in session:
        return redirect(url_for('index'))

    form = TaskForm()
    if form.validate_on_submit():
        name = form.taskName.data
        date = form.taskDate.data.strftime('%Y-%m-%d')
        time = form.taskTime.data.strip()
        priority = form.taskPriority.data

        dt_str = f"{date} {time}" if time else date

        task_doc = {
            'name': name,
            'datetime': dt_str,
            'priority': priority,
            'done': False
        }

        db.collection('calendar_tasks').add(task_doc)
        flash('Task added successfully.', 'success')
        return redirect(url_for('calendar'))

    tasks_docs = db.collection('calendar_tasks').stream()
    calendar_tasks = []
    for doc in tasks_docs:
        task = doc.to_dict()
        task['id'] = doc.id
        calendar_tasks.append(task)

    return render_template('calendar.html', username=session['username'], tasks=calendar_tasks, form=form)

@app.route('/calendar/update_task_status', methods=['POST'])
def update_task_status():
    if 'username' not in session:
        flash('Please login first.', 'error')
        return redirect(url_for('index'))

    task_id = request.form.get('task_id')
    if not task_id:
        flash('Task ID is missing.', 'error')
        return redirect(url_for('calendar'))

    try:
        task_ref = db.collection('calendar_tasks').document(task_id)
        task_doc = task_ref.get()
        
        if not task_doc.exists:
            flash('Task not found.', 'error')
            return redirect(url_for('calendar'))

        task_data = task_doc.to_dict()
        new_done_status = not task_data.get('done', False)
        
        task_ref.update({
            'done': new_done_status
        })
        
        flash('Task status updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating task: {str(e)}', 'error')
    
    return redirect(url_for('calendar'))

@app.route('/calendar/delete/<string:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'username' not in session:
        flash('Please login first.', 'error')
        return redirect(url_for('index'))

    try:
        task_ref = db.collection('calendar_tasks').document(task_id)
        task_doc = task_ref.get()
        
        if not task_doc.exists:
            flash('Task not found.', 'error')
            return redirect(url_for('calendar'))
            
        task_ref.delete()
        flash('Task deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting task: {str(e)}', 'error')
    
    return redirect(url_for('calendar'))

@app.route('/calendar/edit/<string:task_id>', methods=['POST'])
def edit_task(task_id):
    if 'username' not in session:
        flash('Please login first.', 'error')
        return redirect(url_for('index'))

    try:
        task_ref = db.collection('calendar_tasks').document(task_id)
        task_doc = task_ref.get()
        
        if not task_doc.exists:
            flash('Task not found.', 'error')
            return redirect(url_for('calendar'))

        # Get form data
        name = request.form.get('taskName')
        date = request.form.get('taskDate')
        time = request.form.get('taskTime', '').strip()
        priority = request.form.get('taskPriority')

        if not name or not date or not priority:
            flash('Required fields are missing.', 'error')
            return redirect(url_for('calendar'))

        # Format datetime
        dt_str = f"{date} {time}" if time else date

        # Update task
        task_ref.update({
            'name': name,
            'datetime': dt_str,
            'priority': priority
        })
        
        flash('Task updated successfully.', 'success')
    except Exception as e:
        flash(f'Error updating task: {str(e)}', 'error')
    
    return redirect(url_for('calendar'))

if __name__ == '__main__':
    app.run(debug=True)
