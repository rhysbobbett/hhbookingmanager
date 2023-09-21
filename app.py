import os
from flask import (
    Flask, render_template, request, flash, redirect, url_for, session, send_from_directory)
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_login import LoginManager, current_user, login_required, UserMixin, login_user, logout_user
from bson import ObjectId
from datetime import datetime


if os.path.exists("env.py"):
    import env

app = Flask(__name__, static_folder="/hhbookingmanager/assets",
            static_url_path="/assets")


app.config["MONGO_DBNAME"] = os.environ.get("MONGO_DBNAME")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
app.secret_key = os.environ.get("SECRET_KEY")

mongo = PyMongo(app)

login_manager = LoginManager(app)

# Admin required routing
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if the user is an admin
        if current_user.is_admin:
            redirect(url_for("admin"))
            return f(*args, **kwargs)
        else:
            # User is not an admin, redirect to the homepage
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("homepage"))
    return decorated_function


class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["userId"])
        self.fname = user_data["fname"]
        self.lname = user_data["lname"]

    @property
    def is_admin(self):
        return self.id in ("1", "2")


@login_manager.user_loader
def load_user(user_id):
    # Load and return the user from your user database or storage
    user_doc = mongo.db.users.find_one({"userId": int(user_id)})
    if user_doc:
        user = User(user_doc)  # Create a User instance with user data
        return user
    return None

# Login routing
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Check if username exists in db
        user = mongo.db.users.find_one(
            {"username": request.form.get("username").lower()})

        if user:
            # Ensure hashed password matches user input
            if check_password_hash(user["password"], request.form.get("password")):
                user_object = User(user)  
                login_user(user_object)
                session["user"] = user["username"].lower()
                flash("Welcome, {}".format(user["username"]))

                # Check if the user is an admin
                if user["userId"] == 1 or user["userId"] ==  2:
                    return redirect(url_for("admin"))
                else:
                    return redirect(url_for("my_appointments"))

        flash("Username and/or Password incorrect!")
        return redirect(url_for("login"))

    return render_template("login.html")

# Administration page routing
@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin():
    if request.method == "POST":
        # Handle the form submission for deleting an appointment
        session_id_to_delete = request.form.get("sessionId")
        if session_id_to_delete:
            # Delete the appointment from the MongoDB collection
            mongo.db.appointments.delete_one(
                {"sessionId": int(session_id_to_delete)})
            flash("Appointment deleted successfully.", "success")

    # Retrieve appointments data from MongoDB
    appointments = mongo.db.appointments.find()

    # Retrieve user data for all users from the 'users' collection
    users_data = mongo.db.users.find()

    # Convert users_data to a list to pass to the template
    users = list(users_data)

    return render_template("admin.html", appointments=appointments, users=users)

# User Appointments landing page
@app.route("/my_appointments")
@login_required
def my_appointments():
    user_id = current_user.id
    appointments = mongo.db.appointments.find({"userId": user_id})
    return render_template("my_appointments.html", appointments=appointments)


@app.route("/")
def base():
    return render_template("base.html")

# Logo routing
@app.route("/logo")
def serve_logo():
    return send_from_directory("assets/img/logovector.webp")


@app.route("/logo-clicked")
def logo_clicked():
    return redirect(url_for("homepage"))


@app.route("/")
def base():
    # Determine if a user is logged in (replace with your own logic)
    is_user_logged_in = current_user.is_authenticated if hasattr(
        current_user, 'is_authenticated') else False

    # Determine if a user is an admin (replace with your own logic)
    is_admin = current_user.is_admin if hasattr(
        current_user, 'is_admin') else False

    return render_template("homepage.html", is_user_logged_in=is_user_logged_in, is_admin=is_admin)


# Registration Routing
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Check if user exists in the 'users' collection
        existing_user = mongo.db.users.find_one(
            {"username": request.form.get("username").lower()})

        if existing_user:
            flash("Username already exists", "error")
            return redirect(url_for("register"))

        # Generate a unique numerical userId (e.g., incrementing)
        latest_user = mongo.db.users.find_one(sort=[("userId", -1)])
        if latest_user:
            latest_user_id = latest_user["userId"]
        else:
            latest_user_id = 0
        new_user_id = latest_user_id + 1

        # Create a new user document with the generated userId
        register = {
            "userId": new_user_id,
            "username": request.form.get("username").lower(),
            "fname": request.form.get("fname").lower(),
            "lname": request.form.get("lname").lower(),
            "password": generate_password_hash(request.form.get("password"))
        }

        # Insert the new user document into the 'users' collection
        mongo.db.users.insert_one(register)

        session["user"] = request.form.get("username").lower()
        flash("Registration Successful", "success")

        # Redirect to the same page to clear the flash message upon refresh
        return redirect(url_for("register"))

    return render_template("register.html")


# BOOKING MANAGEMENT
@app.route('/bookappointment', methods=['GET', 'POST'])
@login_required
def bookappointment():
    if request.method == 'POST':
        date = request.form.get('date')
        session_length = request.form.get('sessionLength')
        session_desc = request.form.get('description')
        session_id = request.form.get('sessionId')

        # Find the last used sessionId
        last_session = mongo.db.appointments.find_one(
            {}, sort=[("sessionId", -1)])
        if last_session:
            last_session_id = last_session["sessionId"]
        else:
            last_session_id = 0

        # Increment the last_session_id to generate a new sessionId
        new_session_id = last_session_id + 1
        # Check if the chosen date is a holiday
        is_holiday = mongo.db.holidays.find_one(
            {'date': datetime.strptime(date, '%Y-%m-%d')})

        if is_holiday:
            flash('The selected date is a holiday and cannot be booked.', 'error')
        else:
            # Count the number of existing "half day" appointments for the selected date
            half_day_appointments_count = mongo.db.appointments.count_documents({
                'date': datetime.strptime(date, '%Y-%m-%d'),
                'sessionLength': 'half day'
            })

            # Check if there are already two "half day" appointments for the selected date
            if half_day_appointments_count >= 2 and session_length == 'half day':
                flash(
                    'Two "half day" appointments are already booked for the selected date. You cannot book another.', 'error')
            else:
                # Create a new appointment document
                appointment = {
                    'userId': current_user.id,
                    'fname': getattr(current_user, 'fname', ''),
                    'lname': getattr(current_user, 'lname', ''),
                    'date': datetime.strptime(date, '%Y-%m-%d'),
                    'sessionLength': session_length,
                    'description': session_desc,
                    'sessionId': new_session_id,
                }

                # Insert the new appointment document into the MongoDB collection
                mongo.db.appointments.insert_one(appointment)

                flash('Appointment created successfully', 'success')

                # Determine the redirect destination based on user role
                if current_user.is_admin:
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('my_appointments'))

        # Handle cases where current_user doesn't have the required attributes
        flash("User data is incomplete.", "error")
        return redirect(url_for("homepage"))

    # Get the current user's first name and last name
    fname = getattr(current_user, 'fname', '')
    lname = getattr(current_user, 'lname', '')

    # Render the template with the user's first name and last name
    return render_template("bookappointment.html", fname=fname, lname=lname)


@app.route('/manage_sessions', methods=['GET', 'POST'])
@login_required
def manage_sessions():
    if request.method == 'POST':
        # Retrieve form data
        user_id = request.form.get('userId')
        fname = request.form.get('fname')
        lname = request.form.get('lname')
        session_date_str = request.form.get('date')
        session_length = request.form.get('sessionLength')
        description = request.form.get('description')

        # Convert session_date_str to a datetime object
        session_date = datetime.strptime(session_date_str, '%Y-%m-%d')

        # Find the last used sessionId
        last_session = mongo.db.appointments.find_one(
            {}, sort=[("sessionId", -1)])
        if last_session:
            last_session_id = last_session["sessionId"]
        else:
            last_session_id = 0

        # Increment the last_session_id to generate a new sessionId
        new_session_id = last_session_id + 1

        # Create a new appointment document with the new sessionId
        appointment = {
            'userId': user_id,
            'fname': fname,
            'lname': lname,
            'date': session_date,
            'sessionLength': session_length,
            'description': description,
            'sessionId': new_session_id
        }

        # Insert the new appointment document into the 'appointments' collection
        mongo.db.appointments.insert_one(appointment)

        flash('Appointment created successfully!', 'success')

        # Determine the redirect destination based on user role
        if current_user.is_admin:
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('my_appointments'))

    # Retrieve and pass all appointments data to the template
    all_appointments = mongo.db.appointments.find()
    return render_template('my_appointments.html', all_appointments=all_appointments)


@app.route('/edit_appointment/<int:sessionId>', methods=['GET', 'POST'])
@login_required
def edit_appointment(sessionId):
    if request.method == "POST":
        # Get the updated data from the form
        updated_data = {
            "date": request.form.get("date"),
            "sessionLength": request.form.get("sessionLength"),
            "description": request.form.get("description")
        }

        # Update the appointment document in the MongoDB collection
        result = mongo.db.appointments.update_one(
            {"sessionId": sessionId},
            {"$set": updated_data}
        )

        if result.modified_count == 1:
            flash("Appointment updated successfully", "success")
        else:
            flash("Failed to update appointment", "error")

        if current_user.is_admin:
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('my_appointments'))

    # Retrieve the appointment with the given sessionId for editing
    appointment = mongo.db.appointments.find_one({"sessionId": sessionId})

    if appointment:
        return render_template("edit_appointment.html", appointment=appointment)
    else:
        flash("Appointment not found", "error")
        return redirect(url_for("admin"))


@app.route("/delete_appointment/<int:sessionId>", methods=["POST"])
@login_required
def delete_appointment(sessionId):
    
    appointment = mongo.db.appointments.find_one({"sessionId": sessionId})

    if not appointment:
        flash("Appointment not found.", "error")
    else:
        if current_user.is_admin or str(current_user.id) == appointment['userId']:
            mongo.db.appointments.delete_one({"sessionId": sessionId})
            flash("Appointment deleted successfully.", "success")
        else:
            flash("You do not have permission to delete this appointment.", "error")

        if current_user.is_admin:
            return redirect(url_for('admin'))
        else:
            return redirect(url_for('my_appointments'))


# HOLIDAY MANAGEMENT
@app.route('/holidays')
@login_required
@admin_required
def holidays():
    holidays = mongo.db.holidays.find()

    return render_template("holidays.html", holidays=holidays)


@app.route('/add_holiday', methods=['GET', 'POST'])
@login_required
@admin_required
def add_holiday():
    if request.method == 'POST':
        date = request.form.get('date')
        description = request.form.get('description')
        new_holiday = {
            'date': date,
            'description': description
        }
        mongo.db.holidays.insert_one(new_holiday)
        flash('Holiday added successfully!', 'success')
        return redirect(url_for('holidays'))

    return render_template('holidays.html')


@app.route('/edit_holiday/<string:holidayId>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_holiday(holidayId):
    holiday = mongo.db.holidays.find_one({"_id": ObjectId(holidayId)})
    if request.method == 'POST':
        date = request.form.get('date')
        description = request.form.get('description')
        mongo.db.holidays.update_one(
            {"_id": ObjectId(holidayId)},
            {"$set": {"date": date, "description": description}}
        )
        flash('Holiday updated successfully!', 'success')
        return redirect(url_for('holidays'))

    return render_template('edit_holiday.html', holiday=holiday)


@app.route('/delete_holiday/<string:holidayId>', methods=['GET', 'POST'])
@login_required
@admin_required
def delete_holiday(holidayId):
    holiday = mongo.db.holidays.find_one({"_id": ObjectId(holidayId)})
    if not holiday:
        flash("Holiday not found.", "error")
        return redirect(url_for("holidays"))
    if request.method == 'POST':
        mongo.db.holidays.delete_one({"_id": ObjectId(holidayId)})
        flash("Holiday deleted successfully.", "success")
        return redirect(url_for("holidays"))

    return render_template('delete_holiday.html', holiday=holiday)


# USER MANAGEMENT
@app.route("/delete_user/<string:username>", methods=["POST"])
@login_required
@admin_required
def delete_user(username):
    user_to_delete = mongo.db.users.find_one({"username": username})
    if request.method == "POST":
        mongo.db.users.delete_one({"username": username})
        flash("User deleted successfully.", "success")
        return redirect(url_for("admin"))

    return render_template("admin.html", user_to_delete=user_to_delete)


@app.route("/confirm_delete_user/<string:username>", methods=["GET", "POST"])
@login_required
@admin_required
def confirm_delete_user(username):
    user_to_delete = mongo.db.users.find_one({"username": username})
    if request.method == "POST":
        mongo.db.users.delete_one({"username": username})
        flash("User deleted successfully.", "success")
        return redirect(url_for("admin"))

    return render_template("delete_user.html", user_to_delete=user_to_delete)


# LOGOUT LOGIC
@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    # Log the user out using Flask-Login's logout_user() function
    logout_user()
    # Clear the session data
    session.pop("user", None)

    # Flash a message to inform the user they have been logged out
    flash("You have been logged out.", "success")

    # Redirect the user to the login page (or any other desired page)
    return redirect(url_for("login"))


# ERROR HANDLERS
@app.errorhandler(404)
def not_found_error(e):
    return render_template('error404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error500.html'), 500


if __name__ == "__main__":
    app.run(
        host=os.environ.get("IP", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )