from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
import urllib.request
import urllib.error
import urllib.parse
import json

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "heara-development-key"
)

DATABASE = "database.db"


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            UNIQUE(user_id, post_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            UNIQUE(follower_id, following_id)
        )
    """)

    conn.commit()
    conn.close()


# IMPORTANT:
# This runs when Gunicorn/Render imports the application.
init_db()


# =========================================================
# VIDEO CATEGORIES
# =========================================================

VIDEO_CATEGORIES = {

    "For You":
        "funny people comedy entertainment",

    "Comedy":
        "funny comedy humor people laughing",

    "Dance":
        "dance dancing people performance",

    "Music":
        "music singer musician performance",

    "Sports":
        "sports football basketball athletic",

    "Africa":
        "Africa African people culture",

    "Nigeria":
        "Nigeria Nigerian people Lagos",

    "Food":
        "food cooking restaurant street food",

    "Animals":
        "funny animals pets dogs cats",

    "Travel":
        "travel adventure vacation people",

    "Fitness":
        "fitness workout exercise people",

    "Lifestyle":
        "lifestyle people fashion daily life"
}


# =========================================================
# PEXELS VIDEO API
# =========================================================

def get_pexels_videos(query, page=1, per_page=20):

    api_key = os.environ.get("PEXELS_API_KEY")

    if not api_key:

        print("======================================")
        print("PEXELS ERROR")
        print("PEXELS_API_KEY is missing")
        print
