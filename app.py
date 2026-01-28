# Drive Ezzy – AWS Powered Cab Management System
# LOCAL VERSION (Milestone 1 – No AWS)

from flask import Flask, render_template, request, redirect, url_for, session
import os
import uuid
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'drive_ezzy_secret_key'

# ---------------- FILE UPLOAD CONFIG ----------------
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- IN-MEMORY STORAGE ----------------
users = {}            # username -> password
admin_users = {}      # admin -> password
vehicles = []         # list of vehicles
bookings = {}         # username -> list of bookings

# ---------------- PUBLIC ROUTES ----------------
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

# ---------------- USER AUTH ----------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        if request.form['username'] in users:
            return "User already exists!"
        users[request.form['username']] = request.form['password']
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if users.get(request.form['username']) == request.form['password']:
            session['username'] = request.form['username']
            return redirect(url_for('home'))
        return "Invalid credentials!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

# ---------------- USER DASHBOARD ----------------
@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))

    return render_template(
        'home.html',
        username=session['username'],
        my_bookings=bookings.get(session['username'], [])
    )

# ---------------- VEHICLE LIST ----------------
@app.route('/vehicles')
def vehicles_list():
    if 'username' not in session:
        return redirect(url_for('login'))

    booked = [
        b['vehicle_id']
        for b in bookings.get(session['username'], [])
    ]

    return render_template(
        'vehicles.html',
        vehicles=vehicles,
        user_bookings=booked
    )

# ---------------- BOOK VEHICLE ----------------
@app.route('/book/<vehicle_id>')
def book_vehicle(vehicle_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    vehicle = next(v for v in vehicles if v['id'] == vehicle_id)

    start = datetime.now().date()
    end = start + timedelta(days=2)

    booking = {
        'booking_id': str(uuid.uuid4()),
        'vehicle_id': vehicle_id,
        'vehicle_name': vehicle['name'],
        'vehicle_type': vehicle['type'],
        'vehicle_image': vehicle['image'],
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'total_cost': vehicle['price'] * 2
    }

    bookings.setdefault(session['username'], []).append(booking)
    return redirect(url_for('home'))

# ---------------- EXTEND BOOKING ----------------
@app.route('/extend/<booking_id>')
def extend_booking(booking_id):
    for b in bookings.get(session['username'], []):
        if b['booking_id'] == booking_id:
            old_end = datetime.fromisoformat(b['end_date'])
            b['end_date'] = (old_end + timedelta(days=2)).date().isoformat()
            vehicle = next(v for v in vehicles if v['id'] == b['vehicle_id'])
            b['total_cost'] += vehicle['price'] * 2
    return redirect(url_for('home'))

# ---------------- CANCEL BOOKING ----------------
@app.route('/cancel/<booking_id>')
def cancel_booking(booking_id):
    bookings[session['username']] = [
        b for b in bookings.get(session['username'], [])
        if b['booking_id'] != booking_id
    ]
    return redirect(url_for('home'))

# ---------------- ADMIN AUTH ----------------
@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        if request.form['username'] in admin_users:
            return "Admin already exists!"
        admin_users[request.form['username']] = request.form['password']
        return redirect(url_for('admin_login'))
    return render_template('admin_signup.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if admin_users.get(request.form['username']) == request.form['password']:
            session['admin'] = request.form['username']
            return redirect(url_for('admin_dashboard'))
        return "Invalid admin credentials!"
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

# ---------------- ADMIN DASHBOARD ----------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    return render_template(
        'admin_dashboard.html',
        username=session['admin'],
        vehicles=vehicles,
        users=users.keys(),
        bookings={u: [b['booking_id'] for b in bookings.get(u, [])] for u in bookings}
    )

# ---------------- ADD VEHICLE ----------------
@app.route('/admin/add-vehicle', methods=['GET', 'POST'])
def admin_add_vehicle():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        image = request.files['image']
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        vehicles.append({
            'id': str(uuid.uuid4()),
            'name': request.form['vehicle_name'],
            'type': request.form['vehicle_type'],
            'description': request.form['description'],
            'price': int(request.form['price_per_day']),
            'image': filename
        })

        return redirect(url_for('admin_dashboard'))

    return render_template('admin_add_vehicle.html')

# ---------------- EDIT VEHICLE ----------------
@app.route('/admin/edit-vehicle/<vehicle_id>', methods=['GET', 'POST'])
def admin_edit_vehicle(vehicle_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    vehicle = next(v for v in vehicles if v['id'] == vehicle_id)

    if request.method == 'POST':
        vehicle['name'] = request.form['vehicle_name']
        vehicle['type'] = request.form['vehicle_type']
        vehicle['price'] = int(request.form['price'])
        vehicle['description'] = request.form['description']
        return redirect(url_for('admin_dashboard'))

    return render_template('admin_edit_vehicle.html', vehicle=vehicle)

# ---------------- DELETE VEHICLE ----------------
@app.route('/admin/delete-vehicle/<vehicle_id>')
def admin_delete_vehicle(vehicle_id):
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    global vehicles
    vehicles = [v for v in vehicles if v['id'] != vehicle_id]
    return redirect(url_for('admin_dashboard'))

# ---------------- RUN APP ----------------
if __name__ == '__main__':
    app.run(debug=True, port=5000)
