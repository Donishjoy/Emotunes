from flask import Flask, render_template, Response, request, redirect, url_for, flash
from flask_socketio import SocketIO
from flask_socketio import emit
import base64
from PIL import Image
from io import BytesIO
import numpy as np
import tensorflow as tf
import cv2
import os
import shutil
from werkzeug.utils import secure_filename
from flask import current_app
from flask import send_file
from getmail import send_mail
import warnings
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(16)  # Generate a random secret key
app.config["DEBUG"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///emo.db"  # Replace with your database URI
db = SQLAlchemy(app)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Define a user loader function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
detect_fn = tf.saved_model.load("Models/FaceDetector/saved_model")  # Load the face detector
model = tf.keras.models.load_model("Models/FEC")  # Load the facial emotion classifier

class_names = ['Angry', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}
static_files = ['display.css', 'eye.png', 'Picdetectb.jpg', 'thumbsup.jpg',
                'github.png', 'IU.svg', 'UI.svg', 'RT.svg', 'UV.svg', 'VU.svg', 'feedback.svg']

# User model for the database
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# Define a minimal socketio object
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route('/picdelete')
def picdelete():
    # When this function is called, all the files that are not present in the
    # list static_files will be deleted.
    for file in os.listdir("static"):
        if file not in static_files:
            os.remove(f"static/{file}")
    return ("nothing")

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/webcam')
def webcam():
    return render_template('index.html')

def allowed_file(filename):
    return ('.' in filename and
            filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS)

def bound(boxes, scores, h, w):
    idxs = cv2.dnn.NMSBoxes(boxes, scores, 0.5, 1.5)

    # define an array as a matrix
    signs = []
    for i in range(len(idxs)):
        signs.append(i)
    height, width = h, w
    # ensure at least one detection exists
    if len(idxs) > 0:
        # loop over the indexes we are keeping
        for i in idxs.flatten():
            # extract the bounding box coordinates
            ymin = int((boxes[i][0] * height))
            xmin = int((boxes[i][1] * width))
            ymax = int((boxes[i][2] * height))
            xmax = int((boxes[i][3] * width))
            signs[i] = [ymin, ymax, xmin, xmax]
    return signs



def detectandupdate(img):
    path = "static/" + str(img)
    image = cv2.imread(path)
    coordinates = draw_bounding_box(image, detect_fn)

    # Loop over each bounding box.
    for (y, h, x, w) in coordinates:
        cv2.rectangle(image, (x, y), (w, h), (0, 255, 0), 2)
        img2 = image[y:h, x:w]  # Get the face from the image with this trick.
        img2 = tf.image.resize(img2, size=[128, 128])  # Input for the model should have size-(128,128)
        pred = model.predict(tf.expand_dims(img2, axis=0))
        pred_class = class_names[tf.argmax(pred, axis=1).numpy()[0]]
        # These conditions are just added to draw text clearly when the head is so close to the top of the image.
        if x > 20 and y > 40:
            cv2.putText(image, pred_class, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        else:
            cv2.putText(image, pred_class, (x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    path2 = f"static/pred{img}"
    # Save as predimg_name in static.
    cv2.imwrite(path2, image)

    return [img, "pred" + img]

@app.route('/detectpic', methods=['GET', 'POST'])
@login_required  # Protect this route, requires authentication
def detectpic():
    UPLOAD_FOLDER = 'static'
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    if request.method == 'POST':

        file = request.files['file']

        if file and allowed_file(file.filename):

            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            result = detectandupdate(filename)
            return render_template('showdetect.html', orig=result[0], pred=result[1])




@app.route('/sentsafe', methods=['GET', 'POST'])
@login_required  # Protect this route, requires authentication
def send_sentsafe():
    if request.method == 'POST':
        email = request.form['email']
        comments = request.form['comments']
        name = request.form['name']
        comments = email + "  \n " + name + "  \n " + comments
        send_mail(email, comments)
    return render_template('sentfeed.html')

@socketio.on("message")
def handleMessage(input):
    input = input.split(",")[1]
    image_data = input
    # Since the input frame is in the form of a string, we need to convert it into an array.
    im = Image.open(BytesIO(base64.b64decode(image_data)))
    im = np.asarray(im)
    # Process it.
    coordinates = draw_bounding_box(im, detect_fn)
    for (y, h, x, w) in coordinates:
        cv2.rectangle(im, (x, y), (w, h), (0, 255, 0), 2)
        img = im[y:h, x:w]
        img = tf.image.resize(img, size=[128, 128])
        pred = model.predict(tf.expand_dims(img, axis=0))
        pred_class = class_names[tf.argmax(pred, axis=1).numpy()[0]]
        cv2.putText(im, pred_class, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    # Convert it back into a string.
    im = Image.fromarray(im)
    buff = BytesIO()
    im.save(buff, format="JPEG")
    image_data = base64.b64encode(buff.getvalue()).decode("utf-8")
    image_data = "data:image/jpeg;base64," + image_data
    emit('out-image-event', {'image_data': image_data})

def detectandupdatevideo(video):
    output_path = f"static/pred{video}"
    fourcc = cv2.VideoWriter_fourcc(*'h264')
    out = cv2.VideoWriter(output_path, fourcc, 25.0, (640, 360))
    # Using VideoWriter to save the processed frames as a video.
    vidcap = cv2.VideoCapture(f"static/{video}")

    while True:

        ret, image = vidcap.read()
        if ret == True:
            coordinates = draw_bounding_box(image, detect_fn)

            for (y, h, x, w) in coordinates:
                cv2.rectangle(image, (x, y), (w, h), (0, 255, 0), 2)
                img2 = image[y:h, x:w]
                img2 = tf.image.resize(img2, size=[128, 128])
                pred = model.predict(tf.expand_dims(img2, axis=0))
                pred_class = class_names[tf.argmax(pred, axis=1).numpy()[0]]
                if x > 20 and y > 40:
                    cv2.putText(image, pred_class, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                else:
                    cv2.putText(image, pred_class, (x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            output_file = cv2.resize(image, (640, 360))
            out.write(output_file)
        else:
            break

    vidcap.release()
    out.release()

    return [video, "pred" + video]


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))  # Redirect to a dashboard page after login
        else:
            flash('Login failed. Please check your credentials.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists. Please choose another username.', 'danger')
        else:
            new_user = User(username=username, password=generate_password_hash(password, method='sha256'))
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! You can now login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required  # Protect this route, requires authentication
def dashboard():
    # Add code for the dashboard page here
    return render_template('home.html',user=current_user)

@app.route('/logout')
@login_required  # Protect this route, requires authentication
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

