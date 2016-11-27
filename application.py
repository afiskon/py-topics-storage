#!/usr/bin/env python3

import postgresql, flask, json, re
import socket, ssl, time
from wtforms import Form, BooleanField, StringField, PasswordField, validators
from wtforms.widgets import TextArea

pgsql_conn_string = 'pq://eax@localhost/eax'
irc_enabled = False
irc_config = { 
    'host': 'irc.gitter.im',
    'port': '6667',
    'nick': 'devzen_ru_twitter',
    'password': 'SECRET',
    'channel': 'DevZenRu/live'
}

app = flask.Flask(__name__)

# disables JSON pretty-printing in flask.jsonify
# app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

link_regexp = '''(?i)(https?://[^\s\"]+)'''

def irc_send(conf, msg_list):
    if msg_list == []:
        return
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ssl_sock = ssl.wrap_socket(tcp_sock)
    ssl_sock.connect( (conf['host'], int(conf['port'])) )

    def ssl_send(cmd):
        ssl_sock.write(cmd.encode() + b'\r\n')

    ssl_send('USER {0} localhost localhost {0}'.format(conf['nick']))
    ssl_send('NICK {}'.format(conf['nick']))
    ssl_send('PASS {}'.format(conf['password']))
    ssl_send('JOIN #{}'.format(conf['channel']))
    for msg in msg_list:
        ssl_send('PRIVMSG #{} :{}'.format(conf['channel'], msg))
        # time.sleep(1.1)
    ssl_send('QUIT')

    while True:
        data = ssl_sock.read()
        if data == b'': # enf of file
            break

    ssl_sock.close()

def html_encode(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") 

def encode_description(desc):
    temp = html_encode(desc).replace("\n", "<br />") 
    temp = re.sub(link_regexp, '''<a href="\\1">\\1</a>''', temp)
    return temp

def extract_links(text):
    urls = []
    for m in re.finditer(link_regexp, text):
        urls.append(m.group(1))
    return urls

app.jinja_env.globals.update(encode_description = encode_description)

class SubmitForm(Form):
    title = StringField('Title', [validators.required(), validators.length(max=128)])
    description = StringField('Description', widget=TextArea())

class SureForm(Form):
    sure = BooleanField('Sure')

def db_conn():
    return postgresql.open(pgsql_conn_string)

@app.route('/')
def root():
    return flask.redirect('/topics')

def report_error(code):
    data = flask.render_template('error.html', message = 'Error code {}'.format(code))
    return (data, code)

@app.errorhandler(400)
def error_400(e):
    return report_error(400)

@app.errorhandler(404)
def error_404(e):
    return report_error(404)

@app.errorhandler(405)
def error_405(e):
    return report_error(405)

@app.route('/static/<path:path>', methods=['GET'])
def get_static(path):
    return send_from_directory('static', path)

@app.route('/recording', methods=['GET', 'POST'])
def get_recording():
    with db_conn() as db:
        form = SureForm(flask.request.form)
        if form.validate() and form.sure.data == True:
            db.query("""UPDATE global SET value = (now() :: text) WHERE key = 'recording_start_time'""")

        rows = db.query("SELECT (value :: timestamp) FROM global WHERE key = 'recording_start_time'")
        return flask.render_template('recording.html', section = "recording", timestamp = rows[0])

@app.route('/topics', methods=['GET'])
def get_topics():
    with db_conn() as db:
        select = "SELECT t.*, u.login FROM topics AS t LEFT JOIN users AS u ON u.id = t.created_by" 
        current = db.query(select + " WHERE t.status = 'c'")
        regular = db.query(select + " WHERE t.status = 'r' ORDER BY t.priority DESC")
        discussed = db.query(select + " WHERE t.status = 'd' ORDER BY t.updated")
        return flask.render_template('topics.html', section = "topics", current = current, regular = regular, discussed = discussed)

@app.route('/submit', methods=['GET', 'POST'])
def get_submit():
    form = SubmitForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
         with db_conn() as db:
            [(uid,)] = db.query("""SELECT id FROM users WHERE login = 'admin'""")
            # app.logger.info("""uid = {}, description = {}""".format(uid, form.description.data))
            insert = db.prepare(
                "INSERT INTO topics (title, description, rev, created, created_by, updated, updated_by, current_at, discussed_at, status, priority) " +
                "VALUES ($1, $2, 1, now(), $3, now(), $3, now(), now(), 'r', 30) ")
            insert(form.title.data, form.description.data, uid)
            return flask.redirect('/topics')

    return flask.render_template('submit.html', section = "submit", form = form)

@app.route('/topics/<int:topic_id>/edit', methods=['GET', 'POST'])
def get_topics_edit(topic_id):
    form = SubmitForm(flask.request.form)
    if flask.request.method == 'POST' and form.validate():
         with db_conn() as db:
            update = db.prepare("""UPDATE topics SET title = $2, description = $3, updated = now(), rev = rev + 1 WHERE id = $1""")
            update(topic_id, form.title.data, form.description.data)
            return flask.redirect('/topics')
    else:
        with db_conn() as db:
            select = db.prepare("""SELECT title, description FROM topics WHERE id = $1""")
            [(title, description)] = select(topic_id)
            form = SubmitForm(title = title, description = description)
            return flask.render_template('edit.html', section = "submit", topic_id = topic_id, form = form)


@app.route('/topics/<int:topic_id>/mark/current', methods=['GET'])
def get_mark_current(topic_id):
    with db_conn() as db:
        update = db.prepare("""UPDATE topics SET status = 'c', updated = now(), current_at = now() WHERE id = $1""")
        update(topic_id)
        if irc_enabled:
            select = db.prepare("""SELECT description FROM topics WHERE id = $1""")
            [(desc,)] = select(topic_id)
            urls = extract_links(desc)
            irc_send(irc_config, urls)
        return flask.redirect('/topics')

@app.route('/topics/<int:topic_id>/mark/regular', methods=['GET'])
def get_mark_regular(topic_id):
    with db_conn() as db:
        update = db.prepare("""UPDATE topics SET status = 'r', updated = now() WHERE id = $1""")
        update(topic_id)
        return flask.redirect('/topics')

@app.route('/topics/<int:topic_id>/mark/discussed', methods=['GET'])
def get_mark_discussed(topic_id):
    with db_conn() as db:
        update = db.prepare("""UPDATE topics SET status = 'd', updated = now(), discussed_at = now() WHERE id = $1""")
        update(topic_id)
        return flask.redirect('/topics')

@app.route('/topics/<int:topic_id>/priority/<string:action>', methods=['GET'])
def get_priority(topic_id, action):
    if not (action == "up" or action == "down"):
        return flask.redirect('/topics')

    delta = 10
    if action == "down":
        delta = -delta

    with db_conn() as db:
        update = db.prepare("""UPDATE topics SET priority = least(50, greatest(10, priority + ($2))), updated = now() WHERE id = $1""")
        update(topic_id, delta)
        return flask.redirect('/topics')

@app.route('/export/classic', methods=['GET'])
def get_export_classic():
    with db_conn() as db:
        desc_list = db.query("""SELECT description FROM topics WHERE status = 'd' ORDER BY updated""")
        urls = []
        for (desc,) in desc_list:
            urls += extract_links(desc)
        return flask.render_template('export_classic.html', section = "topics", urls = urls)

@app.route('/export/advanced', methods=['GET'])
def get_export_advanced():
    with db_conn() as db:
        select = db.prepare("""SELECT (extract (epoch from (value :: timestamp))) :: int """ + 
                            """FROM global WHERE key = 'recording_start_time'""")
        [(start_tstamp,)] = select()
        topics_list = db.query("""SELECT t.*, ((extract (epoch from (current_at :: timestamp))) :: int) AS topic_tstamp """ + 
                               """FROM topics AS t WHERE t.status = 'd' ORDER BY current_at""")
        text = "<ul>\n"
        for topic in topics_list:
            urls = extract_links(topic["description"])
            delta_t = max(0, topic["topic_tstamp"] - start_tstamp)
            # delta = "{:02}:{:02}:{:02}".format(int(delta_t / (60*60)), int(delta_t / 60) % 60, delta_t % 60)
            delta = "{:02}:{:02}".format(int(delta_t / (60*60)), int(delta_t / 60) % 60)
            if len(urls) == 0:
                text += """<li>[{}] {}</li>\n""".format(delta, html_encode(topic["title"]))
            elif len(urls) == 1:
                text += """<li>[{}] <a href="{}">{}</a></li>\n""".format(delta, urls[0], html_encode(topic["title"]))
            else:
                text += """<li>[{}] {}\n""".format(delta, html_encode(topic["title"]))
                text += "<ul>\n"
                for url in urls:
                    text += """  <li><a href="{}">{}</a></li>\n""".format(url, url)
                text += "</ul>\n"
                text += "</li>\n"
        text += "</ul>\n"
        return flask.render_template('export_advanced.html', section = "topics", text = text)


@app.route('/topics/discussed/clear', methods=['POST'])
def post_discussed_clear():
    form = SureForm(flask.request.form)
    if form.validate() and form.sure.data == True:
         with db_conn() as db:
            db.query("""DELETE FROM topics WHERE status = 'd'""")
    return flask.redirect('/topics')

if __name__ == '__main__':
    app.debug = True  # enables auto reload during development
    app.run()
