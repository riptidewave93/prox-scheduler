#!/usr/bin/env python3
#
# prox-scheduler Frontend API
#
# Copyright (C) 2017 Chris Blake <chris@servernetworktech.com>
#
from flask import Flask, jsonify, abort, make_response, send_from_directory
from flask_restful import Api, Resource, reqparse, fields, marshal
from flask_uuid import FlaskUUID
from flask_httpauth import HTTPBasicAuth
from flask_mysqldb import MySQL
import ast
import hashlib
import uuid
import os
import sys

try:
    from options import *
except ImportError:
    print('Error importing options.py. Did you rename and edit options.py.example?', file=sys.stderr)
    sys.exit(1)

app = Flask(__name__, static_url_path="")
api = Api(app)
auth = HTTPBasicAuth()

# Define MySQL stuff
mysql = MySQL()
app.config['MYSQL_HOST'] = sql_host
app.config['MYSQL_USER'] = sql_user
app.config['MYSQL_PASSWORD'] = sql_pass
app.config['MYSQL_DB'] = sql_db
mysql.init_app(app)

# Are we in debug mode?
app_debug_mode = True
if os.environ.get('DEBUG', 'false') == 'false':
    app_debug_mode = False

# 404 should be in JSON
@app.errorhandler(404)
def not_found(error):
    return make_response(jsonify({'error': 'Not found'}), 404)

# Used to verify our login info which uses a sha1 hash.
def login_verification(usr, passwd):
    # Hash that pass!
    passwd = hashlib.sha1(passwd.encode('utf-8')).hexdigest()
    # MySQL Fun
    dbconn = mysql.connect
    cur = dbconn.cursor()
    query = 'SELECT count(username) from users WHERE username = %s AND password = %s AND is_active = 0 LIMIT 1;'
    param = (usr, passwd)
    cur.execute(query, param)
    rv = cur.fetchone()[0]
    # Cleanup connections
    cur.close()
    dbconn.close()
    # Dirty, but nest in to get our result
    if rv != 0:
        return True
    else:
        return False

# Custom PW auth due to us using SHA1 stuff
@auth.verify_password
def verify_pw(username, password):
    return login_verification(username, password)

@auth.error_handler
def unauthorized():
    # return 403 instead of 401 to prevent browsers from displaying the default
    # auth dialog
    return make_response(jsonify({'message': 'Unauthorized access'}), 403)

# Add declaration for instance list
class InstanceListAPI(Resource):
    decorators = [auth.login_required]

    def __init__(self):
        # We use these for POSTS ONLY!
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(
            'hostname', type=str, required=True, help='No hostname provided', location='json')
        self.reqparse.add_argument(
            'memory', type=int, required=True, help='Memory size in GB not provided', location='json')
        self.reqparse.add_argument(
            'cpu', type=int, required=True, help='CPU count not provided', location='json')
        self.reqparse.add_argument(
            'disk', type=int, required=True, help='Disk size in GB not provided', location='json')
        self.reqparse.add_argument(
            'userdata', type=str, required=True, help="Userdata not provided", location='json')
        self.reqparse.add_argument(
            'backend_storage', type=str, required=False, location='json', default=None)
        self.reqparse.add_argument(
            'backend_hypervisor', type=str, required=False, location='json', default=None)
        self.reqparse.add_argument(
            'template_id', type=int, required=False, location='json', default=default_template_id)
        self.reqparse.add_argument(
            'downloads', type=list, location='json', default=None)
        super(InstanceListAPI, self).__init__()

    def get(self):
        # Do MySQL con, get values we care about
        dbconn = mysql.connect
        cur = dbconn.cursor()
        query = 'SELECT `uuid`, `hostname`, `state` FROM `v_instances`;'
        cur.execute(query)
        rv = cur.fetchall()

        # Close DB
        cur.close()
        dbconn.close()

        # Format instances
        instances = []
        for row in rv:
            inst = {
                'uuid': row[0],
                'hostname': row[1],
                'state': row[2]
            }
            instances.append(inst)

        # Return to user
        return jsonify(instances=instances)

    def post(self):
        args = self.reqparse.parse_args()
        unique_inst_uuid = str(uuid.uuid4())
        dbconn = mysql.connect
        cur = dbconn.cursor()
        # First, put our Userdata up so we can get our ID from the DB
        query = 'INSERT INTO `instance_userdata` (`instance_uuid`,`userdata`) VALUES (%s, %s);'
        cur.execute(query, (unique_inst_uuid, args['userdata']))

        # Now, get back our ID
        query = 'SELECT `id` FROM `instance_userdata` WHERE `instance_uuid` = %(uuid)s;'
        cur.execute(query, {'uuid': unique_inst_uuid})
        ud_id = cur.fetchone()[0]  # Get our ID

        # Were downloads defined?
        build_downloads = None
        if args['downloads'] is not None:
            build_downloads = str(args['downloads'])

        # Post our shit to the DB
        query = 'INSERT INTO `instances` (`uuid`,`state`,`hostname`,`memory`,`cpu`,`disk`,`backend_storage`,`backend_hypervisor`,`template_id`,`userdata_id`,`downloads`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);'
        param = (unique_inst_uuid, 1, args['hostname'], args['memory'], args['cpu'], args['disk'], args[
                 'backend_storage'], args['backend_hypervisor'], args['template_id'], ud_id, build_downloads)
        try:
            cur.execute(query, param)
        except Exception as e:
            # Failed in insert, nuke our instance_data insert
            print("ERROR: Error on adding instance, error of " + str(e), file=sys.stderr)
            print("DEBUG: Last MySQL CMD was " +
                  str(cur._last_executed), file=sys.stderr)
            dbconn.revert()
            cur.close()
            dbconn.close()
            return {"error": "We encountered an issue adding your instance. Please try again."}, 500

        # Cleanup connections
        dbconn.commit()
        cur.close()
        dbconn.close()

        # Format our reply to the user
        instance = {
            'uuid': unique_inst_uuid,
            'hostname': args['hostname'],
            'state': "Create Submitted",
            'cpu': args['cpu'],
            'memory': args['memory'],
            'disk': args['disk'],
            'userdata': args['userdata'],
            'downloads': args['downloads']
        }
        return make_response(jsonify(instance=instance), 201)

# Add decleration for individual instances
class InstanceAPI(Resource):
    decorators = [auth.login_required]

    def __init__(self):
        self.reqparse = reqparse.RequestParser()
        self.reqparse.add_argument(
            'force', type=bool, required=False, location='json', default=False)
        super(InstanceAPI, self).__init__()

    def get(self, id):
        # DB Connection
        dbconn = mysql.connect
        cur = dbconn.cursor()
        query = 'SELECT `id`,`uuid`,`hostname`,`state`,`memory`,`cpu`,`disk`,`ip`,`backend_storage`,`backend_hypervisor`,`backend_instance_id`,`backend_build_state`,`template_id`,`userdata`,`downloads`,`created` FROM `v_instances` WHERE `uuid` = %(uuid)s LIMIT 1;'
        cur.execute(query, {'uuid': id})
        if cur.rowcount == 0:
            abort(404)
        else:
            resp = cur.fetchone()
        # Close DB
        cur.close()
        dbconn.close()

        # Format instance
        if app_debug_mode == False:
            inst = {
                'uuid': resp[1],
                'hostname': resp[2],
                'state': resp[3],
                'memory': resp[4],
                'cpu': resp[5],
                'disk': resp[6],
                'ip': resp[7],
                'userdata': resp[13],
                'downloads': ast.literal_eval(resp[14]),
                'created': resp[15]
            }
        else:
            inst = {
                'id': resp[0],
                'uuid': resp[1],
                'hostname': resp[2],
                'state': resp[3],
                'memory': resp[4],
                'cpu': resp[5],
                'disk': resp[6],
                'ip': resp[7],
                'backend_storage': resp[8],
                'backend_hypervisor': resp[9],
                'backend_instance_id': resp[10],
                'backend_build_state': resp[11],
                'template_id': resp[12],
                'userdata': resp[13],
                'downloads': ast.literal_eval(resp[14]),
                'created': resp[15]
            }

        # If we are a build that is done, link a DL link as well
        if inst['state'] == "Build Complete" or inst['state'] == "Build Failed":
            inst['download_uri'] = "/api/v2.0/download/" + \
                inst['uuid'] + ".tar.gz"

        # Return to user
        return jsonify(instance=inst)

    def delete(self, id):
        args = self.reqparse.parse_args()
        # DB Connection
        dbconn = mysql.connect
        cur = dbconn.cursor()
        query = 'SELECT `state` FROM `instances` WHERE `uuid` = %(uuid)s LIMIT 1;'
        cur.execute(query, {'uuid': id})
        if cur.rowcount == 0:
            abort(404)
        else:
            inst = cur.fetchone()

        # Can we be destroyed?
        if args['force'] is False:
            allowed_destroy_states = [8, 11, 12, 50]
            if inst[0] not in allowed_destroy_states:
                return {"error": "Instance not in a state that allows removal!"}, 403

        # If we are here, our instance exists, so let's just mark it for a
        # destroy.
        query = 'UPDATE `instances` SET `state` = 20 WHERE `uuid` = %(uuid)s;'
        cur.execute(query, {'uuid': id})

        # Cleanup connections
        dbconn.commit()
        cur.close()
        dbconn.close()

        # Rely on our "get" for our response now that a destroy is set
        return self.get(id)

api.add_resource(InstanceListAPI, '/api/v2.0/instances', endpoint='instances')
api.add_resource(InstanceAPI, '/api/v2.0/instances/<id>', endpoint='instance')

# Route to download our builds
@app.route('/api/v2.0/download/<path:filename>', methods=['GET'], endpoint='download')
@auth.login_required
def download(filename):
    if os.path.exists(download_dir + '/' + filename):
        return send_from_directory(directory=download_dir, filename=filename)
    else:
        abort(404)

# Default Index Route
@app.route('/', endpoint='hello')
def hello():
    return jsonify({"message": "Hello, is it me you're looking for?", "version": frontend_ver})

if __name__ == '__main__':
    # Run app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
