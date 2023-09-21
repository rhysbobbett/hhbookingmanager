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

app = Flask(__name__, static_folder="hhbookingmanager/assets",
            static_url_path="/assets")


app.config["MONGO_DBNAME"] = os.environ.get("MONGO_DBNAME")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
app.secret_key = os.environ.get("SECRET_KEY")

mongo = PyMongo(app)

# Initialize Flask-Login
login_manager = LoginManager(app)


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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Check if username exists in db
        user = mongo.db.users.find_one(
            {"username": request.form.get("username").lower()})

        if user:
            # Ensure hashed password matches user input
            if check_password_hash(user["password"], request.form.get("password")):
                user_object = User(user)  # Create a User instance
                login_user(user_object)  # Login the user
                session["user"] = user["username"].lower()
                flash("Welcome, {}".format(user["username"]))

                # Check if the user is an admin (userId 1 or 2)
                if user["userId"] == 1 or user["userId"] ==  2:
                    return redirect(url_for("admin"))
                else:
                    return redirect(url_for("my_appointments"))

        flash("Username and/or Password incorrect!")
        return redirect(url_for("login"))

    return render_template("login.html")


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

@app.route("/my_appointments")
@login_required
def my_appointments():
    user_id = current_user.id
    appointments = mongo.db.appointments.find({"userId": user_id})
    return render_template("my_appointments.html", appointments=appointments)


@app.route("/")
def base():
    return render_template("base.html")


@app.route("/logo")
def serve_logo():
    return send_from_directory("assets/img/logovector.webp")


@app.route("/logo-clicked")
def logo_clicked():
    return redirect(url_for("homepage"))


@app.route("/")
def homepage():
    # Determine if a user is logged in (replace with your own logic)
    is_user_logged_in = current_user.is_authenticated if hasattr(
        current_user, 'is_authenticated') else False

    # Determine if a user is an admin (replace with your own logic)
    is_admin = current_user.is_admin if hasattr(
        current_user, 'is_admin') else False

    return render_template("homepage.html", is_user_logged_in=is_user_logged_in, is_admin=is_admin)


# REGISTRATION 
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
