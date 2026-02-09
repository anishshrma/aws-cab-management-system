from flask import Flask, render_template, request, redirect, url_for, session
import boto3
import uuid
import os
from decimal import Decimal
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

app = Flask(__name__)
app.secret_key = "drive_ezzy_secret_key"

# ================= AWS CONFIG =================
REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

users_table = dynamodb.Table("Users")
admin_table = dynamodb.Table("AdminUsers")
vehicles_table = dynamodb.Table("Vehicles")
bookings_table = dynamodb.Table("Bookings")

SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:715841344567:BookingNotification:cbf35fb7-09a0-4dd6-823b-5b1d692bee78"

# ================= FILE UPLOAD =================
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ================= HELPERS =================
def notify(subject, message):
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
    except ClientError as e:
        print("SNS Error:", e)

# ================= PUBLIC =================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")

# ================= USER AUTH =================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        users_table.put_item(Item={
            "username": request.form["username"],
            "password": request.form["password"]
        })
        notify("User Signup", request.form["username"])
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        res = users_table.get_item(Key={"username": request.form["username"]})
        if "Item" in res and res["Item"]["password"] == request.form["password"]:
            session["username"] = request.form["username"]
            return redirect(url_for("home"))
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ================= USER DASHBOARD =================
@app.route("/home")
def home():
    if "username" not in session:
        return redirect(url_for("login"))

    res = bookings_table.query(
        IndexName="username-index",
        KeyConditionExpression=Key("username").eq(session["username"])
    )
    return render_template("home.html", username=session["username"], my_bookings=res.get("Items", []))

# ================= VEHICLES =================
@app.route("/vehicles")
def vehicles():
    if "username" not in session:
        return redirect(url_for("login"))

    vehicles = vehicles_table.scan().get("Items", [])
    res = bookings_table.query(
        IndexName="username-index",
        KeyConditionExpression=Key("username").eq(session["username"])
    )
    booked = [b["vehicle_id"] for b in res.get("Items", [])]

    return render_template("vehicles.html", vehicles=vehicles, user_bookings=booked)

@app.route("/book/<vehicle_id>")
def book(vehicle_id):
    vehicle = vehicles_table.get_item(Key={"id": vehicle_id})["Item"]

    booking = {
        "booking_id": str(uuid.uuid4()),
        "username": session["username"],
        "vehicle_id": vehicle_id,
        "vehicle_name": vehicle["name"],
        "vehicle_type": vehicle["type"],
        "vehicle_image": vehicle["image"],
        "start_date": datetime.now().date().isoformat(),
        "end_date": (datetime.now().date() + timedelta(days=2)).isoformat(),
        "total_cost": Decimal(vehicle["price"]) * 2
    }

    bookings_table.put_item(Item=booking)
    notify("Vehicle Booked", vehicle["name"])
    return redirect(url_for("home"))

@app.route("/extend/<booking_id>")
def extend_booking(booking_id):
    booking = bookings_table.get_item(Key={"booking_id": booking_id})["Item"]
    vehicle = vehicles_table.get_item(Key={"id": booking["vehicle_id"]})["Item"]

    bookings_table.update_item(
        Key={"booking_id": booking_id},
        UpdateExpression="SET end_date=:e, total_cost=:c",
        ExpressionAttributeValues={
            ":e": (datetime.fromisoformat(booking["end_date"]) + timedelta(days=2)).date().isoformat(),
            ":c": booking["total_cost"] + Decimal(vehicle["price"]) * 2
        }
    )
    return redirect(url_for("home"))

@app.route("/cancel/<booking_id>")
def cancel_booking(booking_id):
    bookings_table.delete_item(Key={"booking_id": booking_id})
    return redirect(url_for("home"))

# ================= ADMIN =================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        res = admin_table.get_item(Key={"username": request.form["username"]})
        if "Item" in res and res["Item"]["password"] == request.form["password"]:
            session["admin"] = request.form["username"]
            return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    vehicles = vehicles_table.scan().get("Items", [])
    users = users_table.scan().get("Items", [])
    bookings = bookings_table.scan().get("Items", [])

    booking_map = {}
    for b in bookings:
        booking_map.setdefault(b["username"], []).append(b["booking_id"])

    return render_template(
        "admin_dashboard.html",
        username=session["admin"],
        vehicles=vehicles,
        users=[u["username"] for u in users],
        bookings=booking_map
    )

# ================= ADD VEHICLE =================
@app.route("/admin/add-vehicle", methods=["GET", "POST"])
def admin_add_vehicle():
    if request.method == "POST":
        image = request.files["image"]
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        vehicles_table.put_item(Item={
            "id": str(uuid.uuid4()),
            "name": request.form["vehicle_name"],
            "type": request.form["vehicle_type"],
            "price": Decimal(request.form["price_per_day"]),
            "description": request.form["description"],
            "image": filename
        })
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add_vehicle.html")

# ================= UPDATE VEHICLE =================
@app.route("/admin/edit-vehicle/<vehicle_id>", methods=["GET", "POST"])
def admin_edit_vehicle(vehicle_id):
    if request.method == "POST":
        vehicles_table.update_item(
            Key={"id": vehicle_id},
            UpdateExpression="SET #n=:n, #t=:t, price=:p, description=:d",
            ExpressionAttributeNames={"#n": "name", "#t": "type"},
            ExpressionAttributeValues={
                ":n": request.form["vehicle_name"],
                ":t": request.form["vehicle_type"],
                ":p": Decimal(request.form["price"]),
                ":d": request.form["description"]
            }
        )
        return redirect(url_for("admin_dashboard"))

    vehicle = vehicles_table.get_item(Key={"id": vehicle_id})["Item"]
    return render_template("admin_edit_vehicle.html", vehicle=vehicle)

# ================= DELETE VEHICLE =================
@app.route("/admin/delete-vehicle/<vehicle_id>")
def admin_delete_vehicle(vehicle_id):
    vehicles_table.delete_item(Key={"id": vehicle_id})
    return redirect(url_for("admin_dashboard"))

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True, port=5000)
