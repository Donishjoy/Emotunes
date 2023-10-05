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
import warnings
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import re
from flask_migrate import Migrate
from flask_login import login_required,current_user


warnings.filterwarnings('ignore')

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(16)  # Generate a random secret key
app.config["DEBUG"] = True
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///emot.db"  # Replace with your database URI
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Define a user loader function
@login_manager.user_loader
def load_user(email):
    # Load the user based on the email address
    return User.query.get(email)

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
detect_fn = tf.saved_model.load("Models/FaceDetector/saved_model")  # Load the face detector
model = tf.keras.models.load_model("Models/FEC")  # Load the facial emotion classifier

class_names = ['Angry', 'Disgust', 'Fear', 'Happy', 'Neutral', 'Sad', 'Surprise']
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4'}
static_files = ['display.css', 'eye.png', 'Picdetectb.jpg', 'thumbsup.jpg',
                'github.png', 'IU.svg', 'UI.svg', 'RT.svg', 'UV.svg', 'VU.svg', 'feedback.svg']

class User(UserMixin, db.Model):
    email = db.Column(db.String(128), primary_key=True)  # This should be the primary key
    username = db.Column(db.String(128), nullable=False)
    password = db.Column(db.String(128), nullable=False)
    def get_id(self):
        return self.email




# Create database tables
with app.app_context():
    db.create_all()

# Define a minimal socketio object
socketio = SocketIO(app, cors_allowed_origins="*")



@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/webcam')
def webcam():
    return render_template('index.html')

@app.route('/webcam_capture')
@login_required
def webcam_capture():
    return render_template('capture_image.html')

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

def draw_bounding_box(frame, detect_fn):
    # Returns the coordinates of the bounding boxes.
    input_tensor = tf.convert_to_tensor(frame)
    input_tensor = input_tensor[tf.newaxis, ...]
    detections = detect_fn(input_tensor)
    num_detections = int(detections.pop('num_detections'))
    detections = {key: value[0, :num_detections].numpy() for key, value in detections.items()}
    detections['num_detections'] = num_detections
    boxes = detections['detection_boxes']
    scores = detections['detection_scores']
    h, w = frame.shape[:2]
    boxes = boxes.tolist()
    scores = scores.tolist()
    coordinates = bound(boxes, scores, h, w)
    return coordinates

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
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))  # Redirect to a dashboard page after login
        else:
            flash('Login failed. Please check your credentials.', 'danger')
    return render_template('login.html')

email_pattern = r'^[\w\.-]+@[\w\.-]+(\.[\w]+)+$'
password_pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email=request.form['email']
        username = request.form['username']
        password = request.form['password']

        # Check if the provided username is a valid email address
        if not re.match(email_pattern, email):
            flash('Invalid email format. Please provide a valid email address.', 'danger')
        elif not re.match(password_pattern, password):
            flash('Password must be at least 8 characters long and contain one capital letter, one number, and one special character.', 'danger')
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                flash('Email already exists. Please choose another email address.', 'danger')
            else:
                new_user = User(email=email,username=username, password=generate_password_hash(password, method='sha256'))
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

if __name__ == "__main__":
    socketio.run(app)
