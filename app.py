from flask import Flask, render_template, request, flash, g, redirect, url_for, session
import random
import string
import hashlib
import binascii
import sqlite3
import requests, json

app = Flask(__name__)
app.static_url_path = '/static'
app.config["SECRET_KEY"] = "Something"
app.config['TEMPLATES_AUTO_RELOAD'] = True
app_info = {'db_file': r'data/moviescollections.db'}

def get_db():
    if not hasattr(g, 'sqlite_db'):
        conn = sqlite3.connect(app_info['db_file'])
        conn.row_factory = sqlite3.Row
        g.sqlite_db = conn
    return g.sqlite_db

class UserPass:

    def __init__(self, user="", password=""):
        self.user = user
        self.password = password
        self.email = ''
        self.is_valid = False
        self.is_admin = False

    def hash_password(self):
        # os_urandom_static was generated by os.urandom(60)
        os_urandom_static=b'\x1b\x84w\x95(\x86\xa1\x86-\xe2@\xce\xc0\x8b\x94=\xe7`\x86a\xaf\xe0(k\xa9\xdch\xebr\xc11\xcf\xab\xd9\xbcE\xb9\xa5\x83]\xfc:}mQu\x15\xb1\x9b\xea\x13\x8d\xb6g\x86\xac\xd0\x0b\xf5\x8b'
        salt = hashlib.sha256(os_urandom_static).hexdigest().encode('ascii')
        pwdhash = hashlib.pbkdf2_hmac('sha512', self.password.encode('utf-8'), salt, 100_000)
        pwdhash = binascii.hexlify(pwdhash)
        return (salt + pwdhash).decode('ascii')

    def verify_password(self, stored_password, provided_password):
        salt = stored_password[:64]
        stored_password = stored_password[64:]
        pwdhash = hashlib.pbkdf2_hmac('sha512', provided_password.encode('utf-8'), salt.encode('ascii'), 100_000)
        pwdhash = binascii.hexlify(pwdhash).decode('ascii')
        return pwdhash == stored_password

    def get_random_user(self):
        random_user =''.join(random.choice(string.ascii_lowercase) for i in range (3))
        self.user = random_user

        password_characters = string.ascii_letters #+ string.digits + string.punctuation
        random_password = ''.join(random.choice(password_characters) for i in range (3))
        self.password = random_password

    def login_user(self):
        db = get_db()
        sql_statement = 'select id, name, email, password, is_active, is_admin from users where name = ?;'
        cur = db.execute(sql_statement, [self.user])
        user_record = cur.fetchone()

        if user_record != None and self.verify_password(user_record['password'], self.password):
            return user_record
        else:
            self.user = None
            self.password = None
            return None

    def get_user_info(self):
        db = get_db()
        sql_statement = 'select name, email, is_active, is_admin from users where name = ?;'
        cur = db.execute(sql_statement, [self.user])
        db_user = cur.fetchone()

        if db_user == None:
            self.is_valid = False
            self.is_admin = False
            self.email = ''
        elif db_user['is_active'] != 1:
            self.is_valid = False
            self.is_admin = False
            self.email = db_user['email']
        else:
            self.is_valid = True
            self.is_admin = db_user['is_admin']
            self.email = db_user['email']

@app.teardown_appcontext
def close_db(error):
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

@app.route("/init_app")
def init_app():
    db = get_db()
    sql_statement = 'select count(*) as cnt from users where is_active and is_admin;'
    cur = db.execute(sql_statement)
    active_admins = cur.fetchone()

    if active_admins != None and active_admins['cnt']>0:
        flash("Application is already set-up. Nothing to do")
        return redirect(url_for("index"))

    user_pass = UserPass()
    user_pass.get_random_user()
    sql_statement = '''insert into users(name, email, password, is_active, is_admin) 
                    values (?, ?, ?, True, True);'''
    db.execute(sql_statement, [user_pass.user, 'noone@nowhere.no', user_pass.hash_password()])
    db.commit()
    flash(f"User {user_pass.user} with password {user_pass.password} has been created")
    return redirect(url_for("index"))

#     admin login: 'cjq'
#     user pass: 'Kko'


@app.route('/')
def index():
    login = UserPass(session.get('user'))
    login.get_user_info()
    return render_template("index.html", login=login)

@app.route("/search_movies", methods = ["GET", "POST"])
def search_movies():
    login = UserPass(session.get('user'))
    login.get_user_info()
    if request.method == "GET":
        return render_template('search_movies.html', login=login)
    else:
        title = '' if 'title' not in request.form else request.form['title']
        if not title:
            title = session.get('title')
            if not title:
                message = "Proszę podać tytuł"
                flash(message)
                return render_template("index.html", login=login)
        session['title'] = title
        response = requests.get(f'https://search.imdbot.workers.dev/?q={title}')
        message = None
        if (response.status_code != requests.codes.ok):
            message = f"Nie można połączyć z bazą danych, kod błędu: {response.status_code}"
        if message != None:
            flash(message)
        else:
            data = response.json()
            list_of_searched_films = []
            for movie in data['description']:
                list_of_searched_films.append(movie)
            return render_template("search_movies.html", login=login, list_of_searched_films=list_of_searched_films)

@app.route("/movie_details/<movie_id>")
def movie_details(movie_id):
    login = UserPass(session.get('user'))
    login.get_user_info()
    title = session.get('title')
    if title is None:
        return redirect(url_for('index'))
    response = requests.get(f'https://search.imdbot.workers.dev/?tt={movie_id}')
    message = None
    if (response.status_code != requests.codes.ok):
        message = f"Nie można połączyć z bazą danych, kod błędu: {response.status_code}"
    if message != None:
        flash(message)
    else:
        movie = response.json()
        return render_template("movie_details.html", login=login, movie=movie, title=title)

@app.route("/save_movie/<movie_id>")
def save_movie(movie_id):
    login = UserPass(session.get('user'))
    login.get_user_info()
    db = get_db()
    if not login.is_valid:
        return redirect(url_for('login'))

    cursor = db.execute('select count(*) as cnt from favourites_movies where user_id = ? and movie_id = ?;', [login.user, movie_id])
    record = cursor.fetchone()
    if record['cnt'] != 0:
        flash("Ten film już jest zapisany w bibliotece 'Ulubione'")
        return redirect(url_for('movie_details', movie_id=movie_id))

    sql_statement = '''insert into favourites_movies (user_id, movie_id) 
                                values (?, ?);'''
    db.execute(sql_statement, [login.user, movie_id])
    db.commit()
    flash("Film zapisano pomyślnie w bibliotece 'Ulubione'")
    return redirect(url_for('movie_details', movie_id=movie_id))

@app.route('/favourites')
def favourites ():
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login:
        return redirect(url_for('login'))

    db = get_db()
    sql_command = 'select movie_id from favourites_movies where user_id = ?;'
    cur = db.execute(sql_command, [login.user])
    list_of_film_id = []
    list_rows = cur.fetchall()
    for row in list_rows:
        list_of_film_id.append(row['movie_id'])
    film_collection = []
    for film in list_of_film_id:
        response = requests.get(f'https://search.imdbot.workers.dev/?tt={film}')
        message = None
        if (response.status_code != requests.codes.ok):
            message = f"Nie można połączyć z bazą danych, kod błędu: {response.status_code}"
        if message != None:
            flash(message)
        else:
            movie = response.json()
            film_collection.append(movie)
    return render_template('favourites.html', film_collection=film_collection, login=login)

@app.route('/movie_delete/<movie_id>')
def movie_delete(movie_id):
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login:
        return redirect(url_for('login'))

    db = get_db()
    sql_statement = 'delete from favourites_movies where movie_id = ? and user_id = ?;'
    db.execute(sql_statement, [movie_id, login.user])
    db.commit()
    flash(f"Film został pomyślnie usunięty z ulubionych")
    return redirect(url_for('favourites'))

@app.route("/login", methods=["GET", "POST"])
def login():
    login = UserPass(session.get('user'))
    login.get_user_info()

    if request.method == "GET":
        return render_template('login.html', login = login)
    else:
        user_name = '' if 'user_name' not in request.form else request.form['user_name']
        user_pass = '' if 'user_pass' not in request.form else request.form['user_pass']

        login = UserPass(user_name, user_pass)
        login_record = login.login_user()

        if login_record != None:
            session['user'] = user_name
            flash (f"Witaj {user_name}!")
            return redirect(url_for('index'))
        else:
            flash("Błąd logowania, spróbuj ponownie")
            return render_template('login.html', login = login)

@app.route("/logout")
def logout():
    if 'user' in session:
        session.pop('user', None)
        flash("Wylogowałeś się poprawnie")
    return redirect(url_for('login'))

@app.route('/new_user', methods=['GET', 'POST'])
def new_user():
    login = UserPass(session.get('user'))
    login.get_user_info()

    db = get_db()
    message = None
    user = {}

    if request.method == "GET":
        return render_template('new_user.html', user = user, login=login)
    else:
        user['user_name'] = '' if not 'user_name' in request.form else request.form['user_name']
        user['email'] = '' if not 'email' in request.form else request.form['email']
        user['user_pass'] = '' if not 'user_pass' in request.form else request.form['user_pass']

        cursor = db.execute('select count(*) as cnt from users where name = ?;', [user['user_name']])
        record = cursor.fetchone()
        is_user_name_unique = (record['cnt'] == 0)

        cursor = db.execute('select count(*) as cnt from users where email = ?;', [user['email']])
        record = cursor.fetchone()
        is_user_email_unique = (record['cnt'] == 0)

        if user['user_name'] == '':
            message = 'Pole "nazwa użytkownika" nie może być puste'
        elif user['email'] == '':
            message = 'Pole "email" nie może być puste'
        elif user['user_pass'] == '':
            message = 'Pole "hasło" nie może być puste'
        elif not is_user_name_unique:
            message = f'Użytkownik o nazwie {user["user_name"]} już istnieje'
        elif not is_user_email_unique:
            message = f'Adres email {user["email"]} jest już wykorzystany'

        if not message:
            user_pass = UserPass(user['user_name'], user['user_pass'])
            password_hash = user_pass.hash_password()
            sql_statement = '''insert into users (name, email, password, is_active, is_admin) 
                            values (?, ?, ?, True, False);'''
            db.execute(sql_statement, [user['user_name'], user['email'], password_hash])
            db.commit()
            flash(f"Użytkownik {user['user_name']} został zarejestronwany")
            return redirect(url_for('index'))
        else:
            flash(f"Popraw błąd: {message}")
            return render_template('new_user.html', user = user, login=login)

@app.route('/users')
def users ():
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login.is_valid or not login.is_admin:
        return redirect(url_for('login'))

    db = get_db()
    sql_command = 'select id, name, email, is_admin, is_active from users;'
    cur = db.execute(sql_command)
    users = cur.fetchall()
    return render_template('users.html', users=users, login=login)

@app.route('/user_status_change/<action>/<user_name>')
def user_status_change(action, user_name):
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login.is_valid or not login.is_admin:
        return redirect(url_for('login'))

    db = get_db()
    if action =='active':
        db.execute('''update users set is_active = (is_active + 1) % 2 where name = ? and name <> ?;''', [user_name, login.user])
        db.commit()
    elif action =='admin':
        db.execute('''update users set is_admin = (is_admin + 1) % 2 where name = ? and name <> ?;''',
                   [user_name, login.user])
        db.commit()

    return redirect(url_for('users'))

@app.route('/my_profile/<user_name>', methods=['GET', 'POST'])
def my_profile(user_name):
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login.is_valid:
        return redirect(url_for('login'))

    db = get_db()
    cur = db.execute('select name, email from users where name = ?;', [login.user])
    user = cur.fetchone()
    message = None

    if login.user == None:
        flash("No such user")
        return redirect(url_for('index'))

    if request.method == "GET":
        return render_template('my_profile.html', user=login.user, login=login)
    else:
        new_email = '' if 'email' not in request.form else request.form['email']
        new_password = '' if 'user_pass' not in request.form else request.form['user_pass']
        if new_email != login.email:
            sql_statement = 'update users set email = ? where name = ?;'
            db.execute(sql_statement, [new_email, login.user])
            db.commit()
            flash("Adres email został zmieniony")
        if new_password != '':
            user_pass = UserPass(login.user, new_password)
            sql_statement = 'update users set password = ? where name = ?;'
            db.execute(sql_statement, [user_pass.hash_password(), login.user])
            db.commit()
            flash("Hasło zostało zmienione")

        return redirect(url_for('index'))

@app.route('/edit_user/<user_name>', methods=['GET', 'POST'])
def edit_user(user_name):
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login.is_valid or not login.is_admin:
        return redirect(url_for('login'))

    db = get_db()
    cur = db.execute('select name, email from users where name = ?;', [user_name])
    user = cur.fetchone()
    message = None

    if user == None:
        flash("No such user")
        return redirect(url_for('users'))

    if request.method == "GET":
        return render_template('edit_user.html', user=user, login=login)
    else:
        new_email = '' if 'email' not in request.form else request.form['email']
        new_password = '' if 'user_pass' not in request.form else request.form['user_pass']

        if new_email != user['email']:
            sql_statement = 'update users set email = ? where name = ?;'
            db.execute(sql_statement, [new_email, user_name])
            db.commit()
            flash("Adres email został zmieniony")
        if new_password != '':
            user_pass = UserPass(user_name, new_password)
            sql_statement = 'update users set password = ? where name = ?;'
            db.execute(sql_statement, [user_pass.hash_password(), user_name])
            db.commit()
            flash("Hasło zostało zmienione")

        return redirect(url_for('users'))

@app.route('/user_delete/<user_name>')
def user_delete(user_name):
    login = UserPass(session.get('user'))
    login.get_user_info()
    if not login.is_valid or not login.is_admin:
        return redirect(url_for('login'))

    db = get_db()
    sql_statement = 'delete from users where name = ? and name <> ?;'
    db.execute(sql_statement, [user_name, login.user])
    db.commit()

    return redirect(url_for('users'))

@app.route('/about')
def about():
    login = UserPass(session.get('user'))
    login.get_user_info()
    return render_template("about.html", login=login)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int("3000"), debug=True)