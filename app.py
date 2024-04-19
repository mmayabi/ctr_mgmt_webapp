import os
import docker

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for 
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime
import socket
import random

from helpers import login_required, lookup

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///container_mgmt.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show container connctions"""
    user_id = session["user_id"]

    images_list = list()
    client = docker.from_env()
    images = client.images.list()
    for image in images:
        for tag in image.attrs["RepoTags"]:
            images_list.append({ "tag": tag, "image_sid": image.short_id })
    client.close()

    return render_template("index.html",images_list=images_list)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()
    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash('must provide username')
            return redirect(url_for('login',_method="GET"))

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash('must provide password')
            return redirect(url_for('login',_method="GET"))

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            flash('invalid username and/or password')
            return redirect(url_for('login',_method="GET"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if (not username) or (not password) or (not confirmation):
            flash('Input is blank!')
            return redirect(url_for('register',_method="GET"))

        if password != confirmation:
            flash('Passwords do not match!')
            return redirect(url_for('register',_method="GET"))

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) > 0:
            flash('Username already exists!')
            return redirect(url_for('register',_method="GET"))

        password_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, hash) VALUES (?, ?)", username, password_hash
        )

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    return render_template("register.html")

@app.route("/images", methods=["GET", "POST"])
def images():
    user_id = session["user_id"]

    if request.method == "POST":
        action, i_sid = request.form['action'].split('_')
        if action == 'remove':
            if i_sid is not None:
                client = docker.from_env()
                for container in client.containers.list(all=True):
                    if container.image.short_id == i_sid:
                        client.close()
                        flash('Image belog to one or two containers')
                        return redirect(url_for('images'))
                for image in client.images.list():
                    if image.short_id == i_sid:
                        image.remove(force=True)
                client.close()
    
    images_list = list()
    client = docker.from_env()
    images = client.images.list()
    for image in images:
        for tag in image.attrs["RepoTags"]:
            images_list.append({ "tag": tag, "image_sid": image.short_id })
    client.close()

    return render_template("images.html",images_list=images_list)

@app.route("/add_image", methods=["GET", "POST"])
def add_image():
    user_id = session["user_id"]

    if request.method == "POST":
        action = request.form['action']
        if action == "pull":
            if not request.form.get("repository"):
                flash('no repository defined')
                return redirect(url_for('add_image',_method='GET'))
            elif not request.form.get("tag"):
                repository = request.form.get("repository")
                tag = "latest"
            else:
                repository = request.form.get("repository")
                tag = request.form.get("tag")
            client = docker.from_env()
            try:
               pulled_image = client.images.pull(repository=repository,tag=tag)
               client.close()
               flash('image pulled')
               return redirect(url_for('add_image',_method="GET"))
            except docker.errors.APIError:
                client.close()
                flash('pull image failed')
                return redirect(url_for('add_image',_method="GET"))
            
        if action == 'build':
            if not request.form.get("dockerfile"):
                flash('dockerfile is empty')
                return redirect(url_for('add_image',_method='GET'))
            elif not request.form.get("tag"):
                tag = "latest"
            else:
                tag = request.form.get("tag")

            f = open(__file__, 'a+') 
            f.write(request.form.get("dockerfile"))
            client = docker.from_env()
            try:
                build_image = client.images.build(fileobj=f,tag=tag)
                client.close()
                f.close() 
                flash('Image Built')
                return redirect(url_for('images',_method="GET"))
            except docker.errors.APIError:
                client.close()
                f.close() 
                flash('API Error')
                return redirect(url_for('add_image',_method="GET"))
            except docker.errors.BuildError:
                client.close()
                f.close() 
                flash('Build image failed')
                return redirect(url_for('add_image',_method="GET"))

    return render_template("add_image.html")

@app.route("/containers", methods=["GET", "POST"])
def containers():
    user_id = session["user_id"]

    if request.method == "POST":
        action, c_sid = request.form['action'].split('_')
        if action == 'stop':
            if c_sid is not None:
                client = docker.from_env()
                for container in client.containers.list():
                    if container.short_id == c_sid:
                        container.stop()
                client.close()
        elif action == 'start':
            if c_sid is not None:
                client = docker.from_env()
                for container in client.containers.list(all=True):
                    if container.short_id == c_sid:
                        container.start()
                client.close()
        elif action == 'remove':
            if c_sid is not None:
                client = docker.from_env()
                for container in client.containers.list(all=True):
                    if container.short_id == c_sid:
                        container.remove(force=True)
                        db.execute(
                           " DELETE FROM user_ctr WHERE user_id = ? AND ctr_name = ?", user_id, container.name
                        )    
                client.close()
        elif action == 'attach':
            if c_sid is not None:
                client = docker.from_env()
                for container in client.containers.list(all=True):
                    if container.short_id == c_sid:
                        if len(list(container.ports.values())) != 0:
                            container_port = list(container.ports.values())[0][0]['HostPort']
                            client.close()
                            return render_template("attach.html",container_port=container_port)
                        else:
                            client.close()
                            flash('Container dose not have any active port')
                            return redirect(url_for('containers'))

    containers_list = list()
    client = docker.from_env()
    containers = client.containers.list(all=True)
    rows = db.execute(
        "SELECT ctr_name FROM user_ctr WHERE user_id = ?", user_id
    )
    user_ctr = list()
    for i in range(len(rows)):
        user_ctr.append(rows[i]['ctr_name'])
    for container in containers:
        if container.name in user_ctr:
            containers_list.append({"name": container.name, 
                                "sid": container.short_id, 
                                "status": container.status,
                                "image_name": container.image.tags[0],
                                "image_sid": container.image.short_id})
    client.close()

    return render_template("containers.html", containers_list=containers_list)

@app.route("/create_container", methods=["GET", "POST"])
def create_container():
    user_id = session["user_id"]
    if request.method == "POST":
        
        rows = db.execute(
            "SELECT * FROM users WHERE id = ?", user_id
        )
        user_permit = rows[0]['permit_ctr']
        user_name = rows[0]['username']
        rows = db.execute(
            "SELECT * FROM user_ctr WHERE user_id = ?", user_id
        )
        if len(rows) >= user_permit:
            flash('You do not have enough credit to create container')
            return redirect(url_for('containers',_method="GET"))

        ctrname = request.form.get("ctrname")
        imgname = request.form.get("imgname")
        cport = request.form.get("cport")

        if not ctrname or not imgname or not cport:
            flash('empty fileds')
            return redirect(url_for('create_container',_method="GET"))

        hport = random.randint(1000, 9000)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        while s.connect_ex(('127.0.0.1', hport)) == 0:
            hport = random.randint(1000, 9000)
        s.close()

        container_name = user_name + '_' + ctrname

        rows = db.execute(
            "SELECT * FROM user_ctr WHERE ctr_name = ?", container_name
        )

        if len(rows) == 0:
            client = docker.from_env()
            try:
                containers = client.containers.create(image=imgname,name=container_name,ports={cport: hport},detach=True)
                db.execute(
                   "INSERT INTO user_ctr (user_id, ctr_name) VALUES (?, ?)", user_id, container_name
                )                
                client.close()
                flash('Container Created')
                return redirect(url_for('containers',_method="GET"))
            except docker.errors.APIError:
                client.close()
                flash('API Error')
                return redirect(url_for('create_container',_method="GET"))
            except docker.errors.NotFound:
                client.close()
                flash('Image not found')
                return redirect(url_for('create_container',_method="GET"))
        else:
            flash('Container name exist')
            return redirect(url_for('create_container',_method="GET"))

    return render_template("create_container.html")
