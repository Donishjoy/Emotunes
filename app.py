from flask import Flask, render_template, request, jsonify, redirect, url_for, flash,session
from flask_sqlalchemy import SQLAlchemy
from PIL import Image
import UTILS
import numpy as np
import pandas as pd
import os
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import re
import secrets
from mutagen import File
import eyed3
import sys

app = Flask(__name__, static_url_path='/static')
app.config["SECRET_KEY"] = secrets.token_hex(16)   # Replace 'your_secret_key' with your actual secret key

# Configure the SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///emotune.db'
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
# Define a database model for songs
class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    singer = db.Column(db.String(100), nullable=False)
    emotion = db.Column(db.String(50), nullable=True)
    song_path = db.Column(db.String(255), nullable=False)
    rating = db.Column(db.Float, default=0.0)
    email = db.Column(db.String(128), nullable=False)
# Define a database model for users
class User(UserMixin, db.Model):
    email = db.Column(db.String(128), primary_key=True)
    username = db.Column(db.String(128), nullable=False)
    password = db.Column(db.String(128), nullable=False)

    def get_id(self):
        return self.email

# Login manager setup
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(email):
    return User.query.get(email)


# @app.route("/", methods=["GET", "POST"])
# def index():
#     top_data = []  # Initialize top data array
#     home_data = []  # Initialize home data array

#     if request.method == "POST":
#         try:
#             if "picture" in request.files:
#                 picture = request.files["picture"]
#                 image = Image.open(picture)
#                 pixels = np.array(image)
#                 emotion = UTILS.detect_emotion(pixels)

#                 if emotion:
#                     # Fetch dataset data for "top" array
#                     top_data = UTILS.get_top_k(emotion)
#                     emotion_html = populate_emotion(emotion)
#                     track_html = populate_tracks(top_data)
                    
#                     # Fetch and populate database data for "home" array
#                     home_data = fetch_songs_and_populate_tracks(emotion)
#                     session['songs_data'] = home_data
#                     print("home", home_data)
#                     print("top", top_data)
                    
#                     return jsonify(emotion_html=emotion_html, track_html=track_html, top=top_data, home=home_data)

#         except Exception as e:
#             print(f"Error processing image: {str(e)}")
#     print("home", home_data)
#     return render_template("home.html", user=current_user, top=top_data, home=home_data)


@app.route("/", methods=["GET", "POST"])
def index():
    top_data = []  # Initialize top data array
    home_data = []  # Initialize home data array

    if request.method == "POST":
        try:
            if "picture" in request.files:
                picture = request.files["picture"]
                image = Image.open(picture)
                pixels = np.array(image)
                emotion = UTILS.detect_emotion(pixels)

                if emotion:
                    # Fetch dataset data for "top" array
                    top_data = UTILS.get_top_k(emotion)
                    emotion_html = populate_emotion(emotion)
                    track_html = populate_tracks(top_data)
                    
                    # Fetch and populate database data for "home" array
                    home_data = fetch_songs_and_populate_tracks(emotion)
                    session['songs_data'] = home_data
                    print("track",track_html)
                    print("top", top_data)
                    print("home", home_data)
                    home_html ="<div><p>help</p></div>"
                    
                    # Generate HTML for each song in the 'home' data
                    song_html_list = [generate_song_html(song) for song in home_data]
                    print("html",song_html_list)
                    return jsonify(emotion_html=emotion_html, track_html=track_html, top=top_data, song_html_list=song_html_list)

        except Exception as e:
            print(f"Error processing image: {str(e)}")

    return render_template("home.html", user=current_user, top=top_data, home=home_data)

def generate_song_html(song):
    # ... Your existing code ...
    song_html = f"""
    <div class="track">
        <img class="track-image" src="../static/cd.gif" alt="{song['title']}">
        <h3 class="track-title">{song['title']}</h3>
        <p class="track-artist">{song['singer']}</p>
        <p class="track-artist">{song['emotion']}</p>
        <!-- Rating Icons -->
        <div class="rating-icons">
            {''.join(['<i class="fas fa-star" style="color: gold;"></i>' for _ in range(int(song['rating']))])}
            <br>
           
        </div> <button type="button" class="play-button"  data-song-path="{song['song_path']}">
                <i class="fas fa-play"></i>
            </button>
        
        <!-- You can add more content as needed -->
    </div>
    """
    return song_html




def populate_tracks(tracks: list) -> str:
    track_html = ""
    for i, track in enumerate(tracks):
        if i % 3 == 0:
            track_html += f'<div class="col-md-4">{UTILS.frame.format(track)}</div>'
        elif i % 3 == 1:
            track_html += f'<div class="col-md-4">{UTILS.frame.format(track)}</div>'
        else:
            track_html += f'<div class="col-md-4">{UTILS.frame.format(track)}</div>'
    return track_html

def populate_emotion(emotion: str) -> str:
    left_color = UTILS.constants["colors"]["left"]
    left_span = f'<span style="color: {left_color}">Identified Emotion: </span>'

    emotion_color = UTILS.constants["colors"][emotion]
    right_span = f'<span style="color: {emotion_color}">{emotion.capitalize()}</span>'
    emotion_html = f'<h2 style="text-align: center;">{left_span} {right_span}</h2>'
    return emotion_html

@app.route("/add_song", methods=["GET", "POST"])
@login_required 
def add_song():
    if request.method == "POST":
        try:
            title = request.form["title"]
            singer = request.form["singer"]
            emotion = request.form["emotion"]
            rating = float(request.form["rating"])
            song_file = request.files["song_file"]
            
            if song_file and allowed_file(song_file.filename):
                filename = secure_filename(song_file.filename)
                song_path = os.path.join("static", filename)
                song_file.save(song_path)
                
                # Extract album cover image
                audiofile = eyed3.load(song_path)
                
                if audiofile.tag and audiofile.tag.images:
                    for image in audiofile.tag.images:
                        if "image/jpeg" in image.description:
                            album_cover_data = image.image_data
                            album_covers_path = os.path.join(app.root_path, "static", "album_covers", filename + '.jpg')

                            with open(album_covers_path, 'wb') as f:
                                f.write(album_cover_data)

                            print("JPEG album cover saved successfully")
                        else:
                            # Handle other image formats or print their descriptions
                            print(f"Unsupported album cover format: {image.description}")

                new_song = Song(title=title, singer=singer, emotion=emotion, song_path=song_path, rating=rating,email=current_user.email)
                db.session.add(new_song)
                db.session.commit()
                return redirect(url_for("songs"))
        except Exception as e:
            print(f"Error adding song to the database: {str(e)}")
    
    return render_template("add_song.html",user=current_user)
    

def fetch_songs_and_populate_tracks(emotion: str):
    emo = emotion.capitalize()
    songs = Song.query.filter_by(emotion=emo,email=current_user.email).all()
    
    # Convert songs to a list of dictionaries
    songs_data = [{'title': song.title, 'singer': song.singer, 'song_path': song.song_path, 'rating': song.rating, 'emotion': song.emotion} for song in songs]
    return songs_data






def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {"mp3", "wav", "ogg", "flac"}

@app.route("/songs")
@login_required 
def songs():
    try:
        songs = Song.query.all()
        return render_template("songs.html", songs=songs,user=current_user)
    except Exception as e:
        print(f"Error retrieving songs: {str(e)}")
        return "An error occurred while retrieving songs."
    
# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed. Please check your credentials.', 'danger')
    return render_template('login.html')

# Registration route
email_pattern = r'^[\w\.-]+@[\w\.-]+(\.[\w]+)+$'
password_pattern = r'^(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        if not re.match(email_pattern, email):
            flash('Invalid email format. Please provide a valid email address.', 'danger')
        elif not re.match(password_pattern, password):
            flash('Password must be at least 8 characters long and contain one capital letter, one number, and one special character.', 'danger')
        else:
            user = User.query.filter_by(email=email).first()
            if user:
                flash('Email already exists. Please choose another email address.', 'danger')
            else:
                new_user = User(email=email, username=username, password=generate_password_hash(password, method='sha256'))
                db.session.add(new_user)
                db.session.commit()
                flash('Registration successful! You can now login.', 'success')
                return redirect(url_for('login'))
    return render_template('register.html')



# Logout route (protected, requires login)
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required  # Protect this route, requires authentication
def dashboard():
    # Add code for the dashboard page here
    return render_template('home.html',user=current_user)

@app.route('/home')
  # Protect this route, requires authentication
def home():
    # Add code for the dashboard page here
    return render_template('home.html',user=current_user)

# Delete songs
@app.route("/delete/<int:song_id>", methods=["POST"])
def delete_song(song_id):
    song = Song.query.get(song_id)
    if song:
        # Delete the song from the database
        db.session.delete(song)
        db.session.commit()
        # Return a response to the client
        return jsonify({"message": f"Song '{song.title}' has been deleted."})
    return jsonify({"message": "Song not found."})



if __name__ == "__main__":
    app.run(debug=True)
