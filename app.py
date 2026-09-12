from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
import urllib.request
import urllib.error
import urllib.parse
import json

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "heara-development-key")

DATABASE = "database.db"

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

VIDEO_CATEGORIES = {
    "For You": "funny people comedy entertainment",
    "Comedy": "funny comedy humor people laughing",
    "Dance": "dance dancing people performance",
    "Music": "music singer musician performance",
    "Sports": "sports football basketball athletic",
    "Africa": "Africa African people culture",
    "Nigeria": "Nigeria Nigerian people Lagos",
    "Food": "food cooking restaurant street food",
    "Animals": "funny animals pets dogs cats",
    "Travel": "travel adventure vacation people",
    "Fitness": "fitness workout exercise people",
    "Lifestyle": "lifestyle people fashion daily life"
}

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True)
