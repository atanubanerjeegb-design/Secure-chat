import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, session, send_from_directory
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)
app.secret_key = "secret123"

socketio = SocketIO(app)

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

online_users = {}

# ---------------- DATABASE ----------------

def get_db():
    return sqlite3.connect("chat.db")

def init_db():

    conn=get_db()
    cur=conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    cipher TEXT,
    iv TEXT,
    room TEXT,
    file TEXT)
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- LOGIN ----------------

@app.route("/",methods=["GET","POST"])
def login():

    if request.method=="POST":

        u=request.form["username"]
        p=request.form["password"]

        conn=get_db()
        cur=conn.cursor()

        cur.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (u,p))

        user=cur.fetchone()
        conn.close()

        if user:
            session["user"]=u
            return redirect("/chat")

        return "Invalid login"

    return render_template("login.html")

# ---------------- SIGNUP ----------------

@app.route("/signup",methods=["GET","POST"])
def signup():

    if request.method=="POST":

        u=request.form["username"]
        p=request.form["password"]

        conn=get_db()
        cur=conn.cursor()

        try:
            cur.execute(
            "INSERT INTO users(username,password) VALUES (?,?)",
            (u,p))
            conn.commit()
        except:
            return "User exists"

        conn.close()

        return redirect("/")

    return render_template("signup.html")

# ---------------- CHAT ----------------

@app.route("/chat")
def chat():

    if "user" not in session:
        return redirect("/")

    return render_template("index.html",user=session["user"])

# ---------------- JOIN ROOM ----------------

@socketio.on("join")
def join(data):

    room=data["room"]
    user=data["user"]

    join_room(room)

    online_users[user]=request.sid

    emit("online_users",list(online_users.keys()),broadcast=True)

    conn=get_db()
    cur=conn.cursor()

    cur.execute("SELECT username,cipher,iv,file FROM messages WHERE room=? ORDER BY id",(room,))

    rows=cur.fetchall()
    conn.close()

    for r in rows:

        filename=r[3]
        original=None

        if filename:
            original=filename.split("_",1)[1]

        emit("message",{
        "user":r[0],
        "cipher":r[1],
        "iv":r[2],
        "file":filename,
        "name":original
        })

# ---------------- DISCONNECT ----------------

@socketio.on("disconnect")
def disconnect():

    remove=None

    for u,sid in online_users.items():
        if sid==request.sid:
            remove=u
            break

    if remove:
        online_users.pop(remove)

    emit("online_users",list(online_users.keys()),broadcast=True)

# ---------------- SEND MESSAGE ----------------

@socketio.on("message")
def message(data):

    user=data["user"]
    room=data["room"]

    cipher=data.get("cipher")
    iv=data.get("iv")

    conn=get_db()
    cur=conn.cursor()

    cur.execute(
    "INSERT INTO messages(username,cipher,iv,room,file) VALUES (?,?,?,?,?)",
    (user,cipher,iv,room,None))

    conn.commit()
    conn.close()

    emit("message",{
    "user":user,
    "cipher":cipher,
    "iv":iv,
    "file":None,
    "name":None
    },room=room)

# ---------------- FILE UPLOAD ----------------

@app.route("/upload",methods=["POST"])
def upload():

    user=request.form["user"]
    msg=request.form["msg"]
    room=request.form["room"]
    file=request.files.get("file")

    filename=None
    original=None

    if file and file.filename!="":

        original=file.filename

        unique=str(uuid.uuid4())+"_"+file.filename

        path=os.path.join(app.config["UPLOAD_FOLDER"],unique)

        file.save(path)

        filename=unique

    conn=get_db()
    cur=conn.cursor()

    cur.execute(
    "INSERT INTO messages(username,cipher,iv,room,file) VALUES (?,?,?,?,?)",
    (user,msg,None,room,filename))

    conn.commit()
    conn.close()

    socketio.emit("message",{
    "user":user,
    "cipher":msg,
    "iv":None,
    "file":filename,
    "name":original
    },room=room)

    return "OK"

# ---------------- FILE DOWNLOAD ----------------

@app.route("/uploads/<filename>")
def files(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"],filename)

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.pop("user",None)
    return redirect("/")

# ---------------- RUN ----------------

if __name__=="__main__":
    socketio.run(app,debug=True)