from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, jsonify
import mysql.connector
from datetime import datetime
import math
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import io
import csv

# --- NEW IMPORT ---
from flask_socketio import SocketIO

# ===================== Flask Setup =====================
app = Flask(__name__)
app.secret_key = 'smart_parking_secret_key_2024'

# --- NEW SETUP ---
# Wrap the app with SocketIO
socketio = SocketIO(app)

# ===================== Database Config =====================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '50060010',
    'database': 'smart_parking'
}

# ===================== Utility Functions =====================
def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ===================== Authentication Routes =====================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                flash(f"Welcome back, {user['username']}!", 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password', 'danger')
        else:
            flash('Database connection error', 'danger')

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')

        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, email, password, phone, role) VALUES (%s, %s, %s, %s, 'user')",
                    (username, email, hashed_password, phone)
                )
                conn.commit()
                flash('Account created successfully! Please login.', 'success')
                return redirect(url_for('login'))
            except mysql.connector.Error as err:
                if err.errno == 1062:
                     flash('That email address is already in use.', 'danger')
                else:
                     flash(f"Error: {err}", 'danger')
            finally:
                cursor.close()
                conn.close()
        else:
            flash('Database connection error', 'danger')
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully!', 'info')
    return redirect(url_for('login'))

# ===================== Dashboard =====================
@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return render_template('user_dashboard.html')

    cursor = conn.cursor(dictionary=True)

    if session.get('role') == 'admin':
        cursor.execute("SELECT COUNT(*) as total FROM parking_slots")
        total_slots = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) as occupied FROM parking_slots WHERE status='occupied'")
        occupied_slots = cursor.fetchone()['occupied']

        empty_slots = total_slots - occupied_slots

        cursor.execute("SELECT COUNT(*) as today_count FROM vehicles WHERE DATE(entry_time)=CURDATE() AND exit_time IS NULL")
        today_vehicles = cursor.fetchone()['today_count']

        cursor.execute("SELECT COALESCE(SUM(parking_fee), 0) as revenue FROM vehicles WHERE DATE(exit_time)=CURDATE()")
        today_revenue = cursor.fetchone()['revenue']

        cursor.execute("SELECT * FROM parking_slots ORDER BY slot_number")
        slots = cursor.fetchall()

        cursor.execute("""
            SELECT v.*, ps.slot_number 
            FROM vehicles v 
            LEFT JOIN parking_slots ps ON v.slot_id = ps.id 
            WHERE v.exit_time IS NULL
            ORDER BY v.entry_time DESC
        """)
        recent_vehicles = cursor.fetchall()

        cursor.execute("SELECT v.vehicle_number, v.owner_name, v.entry_time, v.slot_id FROM vehicles v WHERE v.exit_time IS NULL")
        parked_vehicles = cursor.fetchall()
        
        parked_vehicles_map = {v['slot_id']: v for v in parked_vehicles}

        cursor.close()
        conn.close()

        return render_template('admin_dashboard.html',
                               total_slots=total_slots,
                               occupied_slots=occupied_slots,
                               empty_slots=empty_slots,
                               today_vehicles=today_vehicles,
                               today_revenue=today_revenue,
                               slots=slots,
                               recent_vehicles=recent_vehicles,
                               parked_vehicles_map=parked_vehicles_map)
    else:
        cursor.execute("""
            SELECT v.*, ps.slot_number 
            FROM vehicles v 
            LEFT JOIN parking_slots ps ON v.slot_id = ps.id 
            WHERE v.user_id=%s 
            ORDER BY v.entry_time DESC
        """, (session['user_id'],))
        user_vehicles = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('user_dashboard.html', vehicles=user_vehicles)

# ===================== Vehicle Entry =====================
@app.route('/add_vehicle', methods=['GET', 'POST'])
@login_required
def add_vehicle():
    if request.method == 'POST':
        vehicle_number = request.form.get('vehicle_number').upper()
        owner_name = request.form.get('owner_name')
        contact = request.form.get('contact')
        vehicle_type = request.form.get('vehicle_type')

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT * FROM parking_slots WHERE status='empty' AND slot_type=%s LIMIT 1", (vehicle_type,))
            available_slot = cursor.fetchone()

            if available_slot:
                cursor.execute("""
                    INSERT INTO vehicles 
                    (vehicle_number, owner_name, contact, vehicle_type, slot_id, user_id, entry_time) 
                    VALUES (%s,%s,%s,%s,%s,%s,NOW())
                """, (vehicle_number, owner_name, contact, vehicle_type, available_slot['id'], session['user_id']))
                
                cursor.execute("UPDATE parking_slots SET status='occupied' WHERE id=%s", (available_slot['id'],))
                
                conn.commit()
                
                # --- NEW: EMIT SOCKET EVENT ---
                socketio.emit('parking_updated', {'message': f'Vehicle {vehicle_number} parked.'})
                
                flash(f'Vehicle {vehicle_number} parked at {available_slot["slot_number"]} ({vehicle_type} slot)', 'success')
            else:
                flash(f'No available slots for vehicle type: {vehicle_type}!', 'warning')
            
            cursor.close()
            conn.close()
        else:
            flash('Database connection error', 'danger')

    return render_template('add_vehicle.html')

# ===================== Vehicle Exit (Old route) =====================
@app.route('/vehicle_exit/<int:vehicle_id>', methods=['POST'])
@login_required
def vehicle_exit(vehicle_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM vehicles WHERE id=%s", (vehicle_id,))
        vehicle = cursor.fetchone()

        if vehicle and vehicle['exit_time'] is None:
            vehicle_type = vehicle['vehicle_type']
            fare_key = f"parking_fee_{vehicle_type}"
            cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = %s", (fare_key,))
            fare_row = cursor.fetchone()
            fare_per_hour = int(fare_row['setting_value']) if fare_row else 20
            
            entry_time = vehicle['entry_time']
            exit_time = datetime.now()
            duration = exit_time - entry_time
            hours = duration.total_seconds() / 3600
            hours = int(hours) + (1 if hours % 1 > 0 else 0)
            if hours < 1: hours = 1
            parking_fee = hours * fare_per_hour

            cursor.execute("UPDATE vehicles SET exit_time=%s, parking_fee=%s WHERE id=%s",
                           (exit_time, parking_fee, vehicle_id))
            cursor.execute("UPDATE parking_slots SET status='empty' WHERE id=%s", (vehicle['slot_id'],))
            conn.commit()
            
            # --- NEW: EMIT SOCKET EVENT ---
            socketio.emit('parking_updated', {'message': 'Vehicle exited.'})
            
            flash(f'Vehicle exited. Fee: ₹{parking_fee}', 'success')

        cursor.close()
        conn.close()
    return redirect(url_for('dashboard'))

# ===================== AJAX: Calculate fare =====================
@app.route('/calculate_fare', methods=['POST'])
@login_required
def calculate_fare():
    data = request.get_json() or request.form
    vehicle_id = data.get('vehicle_id')

    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'DB connection error'}), 500
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM vehicles WHERE id = %s", (vehicle_id,))
        vehicle = cursor.fetchone()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404
        
        entry_time = vehicle['entry_time']
        exit_time = datetime.now()

        vehicle_type = vehicle['vehicle_type']
        fare_key = f"parking_fee_{vehicle_type}"
        cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = %s", (fare_key,))
        fare_row = cursor.fetchone()
        fare_per_hour = int(fare_row['setting_value']) if fare_row else 20
        
        duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
        if duration_hours <= 0:
            hours = 1
        else:
            hours = math.ceil(duration_hours)
        total_fare = hours * fare_per_hour

        return jsonify({
            'hours': hours,
            'fare_per_hour': fare_per_hour,
            'total_fare': float(total_fare),
            'entry_time': entry_time.isoformat(),
            'exit_time': exit_time.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ===================== Receipt and Finalize Exit =====================
@app.route('/receipt/<int:vehicle_id>')
@login_required
def receipt(vehicle_id):
    exit_time_str = request.args.get('exit_time')
    finalize = request.args.get('finalize', '0') == '1'

    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('dashboard'))
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT v.*, ps.slot_number FROM vehicles v LEFT JOIN parking_slots ps ON v.slot_id = ps.id WHERE v.id = %s", (vehicle_id,))
        vehicle = cursor.fetchone()
        
        if not vehicle:
            flash('Vehicle not found', 'warning')
            cursor.close()
            conn.close()
            return redirect(url_for('dashboard'))

        # Determine exit_time: if finalized, use that. If not, use now()
        if vehicle['exit_time'] and not exit_time_str:
            exit_time = vehicle['exit_time']
            total_fare = vehicle['parking_fee']
        elif exit_time_str:
            exit_time = datetime.fromisoformat(exit_time_str)
        else:
            exit_time = datetime.now()
        
        entry_time = vehicle['entry_time']
        
        # Calculate fare if it's not already set
        if not vehicle['exit_time']:
            vehicle_type = vehicle['vehicle_type']
            fare_key = f"parking_fee_{vehicle_type}"
            cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = %s", (fare_key,))
            fare_row = cursor.fetchone()
            fare_per_hour = int(fare_row['setting_value']) if fare_row else 20
            
            duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
            hours = math.ceil(duration_hours) if duration_hours > 0 else 1
            total_fare = hours * fare_per_hour
        else:
            # If already finalized, use stored values
            duration_hours = (exit_time - entry_time).total_seconds() / 3600.0
            hours = math.ceil(duration_hours) if duration_hours > 0 else 1
            total_fare = vehicle['parking_fee']
            fare_per_hour = total_fare / hours if hours > 0 else 0


        # If finalizing, update the database
        if finalize and vehicle['exit_time'] is None:
            cursor.execute("UPDATE vehicles SET exit_time=%s, parking_fee=%s WHERE id=%s",
                           (exit_time, total_fare, vehicle_id))
            if vehicle['slot_id']:
                cursor.execute("UPDATE parking_slots SET status='empty' WHERE id=%s", (vehicle['slot_id'],))
            conn.commit()
            
            # --- NEW: EMIT SOCKET EVENT ---
            socketio.emit('parking_updated', {'message': 'Vehicle finalized exit.'})

        display_entry = entry_time.strftime('%d %b, %I:%M %p')
        display_exit = exit_time.strftime('%d %b, %I:%M %p')

        receipt_data = {
            'vehicle': vehicle,
            'slot_number': vehicle.get('slot_number') or 'N/A',
            'entry_time': display_entry,
            'exit_time': display_exit,
            'hours': int(hours),
            'fare_per_hour': fare_per_hour,
            'total_fare': total_fare
        }

        return render_template('receipt.html', **receipt_data)
    except Exception as e:
        flash(f'Error generating receipt: {e}', 'danger')
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()


# ===================== Search Vehicle =====================
@app.route('/search_vehicle', methods=['GET', 'POST'])
@login_required
def search_vehicle():
    vehicles = []
    search_query = request.form.get('search_query', '').strip()
    search_type = request.form.get('search_type', 'vehicle_number')
        
    if request.method == 'POST' and search_query:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query_base = "SELECT v.*, ps.slot_number FROM vehicles v LEFT JOIN parking_slots ps ON v.slot_id = ps.id "
        
        if search_type == 'vehicle_number':
            query = query_base + "WHERE v.vehicle_number LIKE %s ORDER BY v.entry_time DESC"
            params = (f"%{search_query}%",)
        elif search_type == 'owner_name':
            query = query_base + "WHERE v.owner_name LIKE %s ORDER BY v.entry_time DESC"
            params = (f"%{search_query}%",)
        elif search_type == 'contact':
            query = query_base + "WHERE v.contact LIKE %s ORDER BY v.entry_time DESC"
            params = (f"%{search_query}%",)
        elif search_type == 'vehicle_type':
            query = query_base + "WHERE v.vehicle_type = %s ORDER BY v.entry_time DESC"
            params = (search_query,)
        elif search_type == 'date':
            query = query_base + "WHERE DATE(v.entry_time)=%s ORDER BY v.entry_time DESC"
            params = (search_query,)
            
        cursor.execute(query, params)
        vehicles = cursor.fetchall()
        cursor.close()
        conn.close()

    return render_template('search_vehicle.html', 
                           vehicles=vehicles, 
                           searched_query=search_query, 
                           searched_type=search_type)

# ===================== Search by Slot =====================
@app.route('/search_slot', methods=['GET', 'POST'])
@login_required
def search_slot():
    vehicles = []
    slot_number = request.form.get('slot_number', '').strip().upper()
    
    if request.method == 'POST' and slot_number:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT v.*, ps.slot_number 
            FROM vehicles v
            JOIN parking_slots ps ON v.slot_id = ps.id
            WHERE ps.slot_number=%s
            ORDER BY v.entry_time DESC
        """, (slot_number,))
        vehicles = cursor.fetchall()
        cursor.close()
        conn.close()

    return render_template('search_slot.html', vehicles=vehicles, searched_slot=slot_number)

# ===================== Admin Manage Slots =====================
@app.route('/manage_slots', methods=['GET', 'POST'])
@admin_required
def manage_slots():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        action = request.form.get('action')
        slot_number = request.form.get('slot_number').strip().upper()
        slot_type = request.form.get('slot_type') 
        changed = False

        if action == 'add':
            try:
                cursor.execute(
                    "INSERT INTO parking_slots (slot_number, slot_type, status) VALUES (%s, %s, 'empty')", 
                    (slot_number, slot_type)
                )
                conn.commit()
                flash(f'Slot {slot_number} ({slot_type}) added!', 'success')
                changed = True
            except mysql.connector.Error as err:
                conn.rollback()
                if err.errno == 1062:
                    flash(f'Error: Slot number "{slot_number}" already exists.', 'danger')
                else:
                    flash(f'Error: {err}', 'danger')
                        
        elif action == 'delete':
            cursor.execute("SELECT status FROM parking_slots WHERE slot_number=%s", (slot_number,))
            slot = cursor.fetchone()
            
            if not slot:
                flash(f'Error: Slot {slot_number} not found.', 'danger')
            elif slot['status'] == 'occupied':
                flash(f'Error: Cannot delete occupied slot {slot_number}. Vehicle must exit first.', 'warning')
            else:
                cursor.execute("DELETE FROM parking_slots WHERE slot_number=%s", (slot_number,))
                conn.commit()
                flash(f'Slot {slot_number} deleted!', 'success')
                changed = True
        
        if changed:
            # --- NEW: EMIT SOCKET EVENT ---
            socketio.emit('parking_updated', {'message': 'Parking slots modified.'})

    cursor.execute("SELECT * FROM parking_slots ORDER BY slot_number")
    slots = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('manage_slots.html', slots=slots)

# ===================== Admin Set Fare =====================
@app.route('/set_fare', methods=['GET', 'POST'])
@admin_required
def set_fare():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        fares_to_save = [
            ('parking_fee_Car', request.form.get('fare_Car')),
            ('parking_fee_Bike', request.form.get('fare_Bike')),
            ('parking_fee_SUV', request.form.get('fare_SUV')),
            ('parking_fee_Van', request.form.get('fare_Van')),
        ]
        
        for key, value in fares_to_save:
            cursor.execute("""
                INSERT INTO system_settings (setting_key, setting_value)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
            """, (key, value))
        
        conn.commit()
        flash(f'Parking fares updated!', 'success')

    cursor.execute("SELECT * FROM system_settings WHERE setting_key LIKE 'parking_fee_%'")
    db_fares = cursor.fetchall()
    
    fares = { 'Car': '20', 'Bike': '10', 'SUV': '25', 'Van': '30' }
    for f in db_fares:
        key_name = f['setting_key'].replace('parking_fee_', '')
        fares[key_name] = f['setting_value']
        
    cursor.close()
    conn.close()
    return render_template('set_fare.html', fares=fares)

# ===================== Admin Reports =====================
@app.route('/reports')
@admin_required
def reports_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT v.vehicle_number, v.owner_name, ps.slot_number, 
               v.entry_time, v.exit_time, v.parking_fee
        FROM vehicles v
        LEFT JOIN parking_slots ps ON v.slot_id = ps.id
        ORDER BY v.entry_time DESC
    """)
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('reports.html', records=records)

# ===================== NEW: Analytics Page Route =====================
@app.route('/analytics')
@admin_required
def analytics_page():
    # This route just renders the template.
    # The template will fetch data from the API endpoints.
    return render_template('analytics.html')

# ===================== API: Export CSV Report =====================
@app.route('/api/export_report')
@admin_required
def export_report():
    conn = get_db_connection()
    if not conn:
        flash('Database connection error', 'danger')
        return redirect(url_for('reports_page'))
        
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT v.vehicle_number, v.owner_name, v.contact, v.vehicle_type, 
               ps.slot_number, v.entry_time, v.exit_time, v.parking_fee
        FROM vehicles v
        LEFT JOIN parking_slots ps ON v.slot_id = ps.id
        WHERE v.exit_time IS NOT NULL
        ORDER BY v.exit_time DESC
    """)
    records = cursor.fetchall()
    cursor.close()
    conn.close()

    si = io.StringIO()
    headers = ['VehicleNumber', 'Owner', 'Contact', 'VehicleType', 'Slot', 
               'EntryTime', 'ExitTime', 'Fee']
               
    writer = csv.DictWriter(si, fieldnames=headers)
    writer.writeheader()
    
    for row in records:
        writer.writerow({
            'VehicleNumber': row['vehicle_number'],
            'Owner': row['owner_name'],
            'Contact': row['contact'],
            'VehicleType': row['vehicle_type'],
            'Slot': row['slot_number'],
            'EntryTime': row['entry_time'],
            'ExitTime': row['exit_time'],
            'Fee': row['parking_fee']
        })
    
    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=parking_report.csv"}
    )

# ===================== API: Revenue Data for Chart =====================
@app.route('/api/revenue_data/<period>')
@login_required
def revenue_data(period):
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    labels = []
    values = []

    if period == "today":
        query = "SELECT HOUR(exit_time) AS hour, SUM(parking_fee) AS revenue FROM vehicles WHERE DATE(exit_time) = CURDATE() GROUP BY HOUR(exit_time) ORDER BY hour"
        title = "Today's Revenue (by hour)"
    elif period == "week":
        query = "SELECT DATE(exit_time) AS day, SUM(parking_fee) AS revenue FROM vehicles WHERE exit_time >= CURDATE() - INTERVAL 7 DAY GROUP BY day ORDER BY day"
        title = "Last 7 Days Revenue"
    else: # Default to month
        query = "SELECT DATE(exit_time) AS day, SUM(parking_fee) AS revenue FROM vehicles WHERE MONTH(exit_time) = MONTH(CURDATE()) AND YEAR(exit_time) = YEAR(CURDATE()) GROUP BY day ORDER BY day"
        title = "This Month's Revenue"

    cursor.execute(query)
    results = cursor.fetchall()

    for row in results:
        label = (f"{row['hour']}:00" if 'hour' in row else row['day'].strftime("%d %b"))
        labels.append(label)
        values.append(float(row['revenue']) if row['revenue'] else 0)

    cursor.close()
    conn.close() 
    return jsonify({"labels": labels, "values": values, "title": title})

# ===================== NEW: API for Analytics Page =====================
@app.route('/api/analytics_data')
@admin_required
def analytics_data():
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "DB connection error"}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Peak Occupancy Hours
        cursor.execute("""
            SELECT HOUR(entry_time) AS hour, COUNT(id) AS vehicle_count
            FROM vehicles
            GROUP BY HOUR(entry_time)
            ORDER BY hour
        """)
        peak_hours_data = cursor.fetchall()
        
        # 2. Revenue by Vehicle Type
        cursor.execute("""
            SELECT vehicle_type, COALESCE(SUM(parking_fee), 0) AS total_revenue
            FROM vehicles
            WHERE exit_time IS NOT NULL
            GROUP BY vehicle_type
        """)
        revenue_by_type_data = cursor.fetchall()
        
        # 3. Average Parking Duration
        cursor.execute("""
            SELECT AVG(TIMESTAMPDIFF(MINUTE, entry_time, exit_time)) AS avg_minutes
            FROM vehicles
            WHERE exit_time IS NOT NULL
        """)
        avg_duration_data = cursor.fetchone()
        
        # Format for Chart.js
        
        # Peak hours
        peak_hours_labels = [f"{h['hour']}:00" for h in peak_hours_data]
        peak_hours_values = [h['vehicle_count'] for h in peak_hours_data]
        
        # Revenue by type
        revenue_labels = [r['vehicle_type'] for r in revenue_by_type_data]
        revenue_values = [float(r['total_revenue']) for r in revenue_by_type_data]
        
        # Avg duration
        avg_minutes = float(avg_duration_data['avg_minutes']) if avg_duration_data['avg_minutes'] else 0
        
        return jsonify({
            "peak_hours": {
                "labels": peak_hours_labels,
                "values": peak_hours_values
            },
            "revenue_by_type": {
                "labels": revenue_labels,
                "values": revenue_values
            },
            "average_duration_minutes": round(avg_minutes, 2)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ===================== Run App =====================
if __name__ == '__main__':
    # --- MODIFIED: Run with SocketIO ---
    print("Starting Flask-SocketIO server...")
    # Use allow_unsafe_werkzeug=True for newer Werkzeug versions with Flask reloader
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)

