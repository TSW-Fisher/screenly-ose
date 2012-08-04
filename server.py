#!/usr/bin/env python
# -*- coding: utf8 -*-

__author__ = "Viktor Petersson"
__copyright__ = "Copyright 2012, WireLoad Inc"
__license__ = "Dual License: GPLv2 and Commercial License"
__version__ = "0.1.1"
__email__ = "vpetersson@wireload.net"

import json, hashlib, os, requests, mimetypes, sys, sqlite3, socket, netifaces
from datetime import datetime, timedelta
from bottle import route, run, debug, template, request, validate, error, static_file, get
from dateutils import datestring
from StringIO import StringIO
from PIL import Image
from urlparse import urlparse
from hurry.filesize import size

# Define settings
configdir = os.getenv("HOME") + "/.screenly/"
database = configdir + "screenly.db"
nodetype = "standalone"

def time_lookup():
    if nodetype == "standalone":
        return datetime.now()
    elif nodetype == "managed":
        return datetime.utcnow()

def get_playlist():
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    c.execute("SELECT * FROM assets ORDER BY name")
    assets = c.fetchall()
    
    playlist = []
    for asset in assets:
        # Match variables with database
        asset_id = asset[0]  
        name = asset[1]
        filename = asset[2]
        uri = asset[3] # Path in local database
	input_start_date = asset[5]
	input_end_date = asset[6]

        try:
            start_date = datestring.date_to_string(asset[5])
        except:
            start_date = None

        try:
            end_date = datestring.date_to_string(asset[6])
        except:
            end_date = None
            
        duration = asset[7]
        mimetype = asset[8]

        playlistitem = { "name" : name, "uri" : uri, "duration" : duration, "mimetype" : mimetype, "asset_id" : asset_id, "start_date" : start_date, "end_date" : end_date}
        if (start_date and end_date) and (input_start_date < time_lookup() and input_end_date > time_lookup()):
		playlist.append(playlistitem)
    
    return json.dumps(playlist)

def get_assets():
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    c.execute("SELECT * FROM assets ORDER BY name")
    assets = c.fetchall()
    
    playlist = []
    for asset in assets:
        # Match variables with database
        asset_id = asset[0]  
        name = asset[1]
        filename = asset[2]
        uri = asset[3] # Path in local database

        try:
            start_date = datestring.date_to_string(asset[5])
        except:
            start_date = ""

        try:
            end_date = datestring.date_to_string(asset[6])
        except:
            end_date = ""
            
        duration = asset[7]
        mimetype = asset[8]

        playlistitem = { "name" : name, "uri" : uri, "duration" : duration, "mimetype" : mimetype, "asset_id" : asset_id, "start_date" : start_date, "end_date" : end_date}
	playlist.append(playlistitem)
    
    return json.dumps(playlist)



def initiate_db():

    # Create config dir if it doesn't exist
    if not os.path.isdir(configdir):
       os.makedirs(configdir)

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    # Check if the asset-table exist. If it doesn't, create it.
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
    asset_table = c.fetchone()
    
    if not asset_table:
        c.execute("CREATE TABLE assets (asset_id TEXT, name TEXT, filename TEXT, uri TEXT, md5 TEXT, start_date TIMESTAMP, end_date TIMESTAMP, duration TEXT, mimetype TEXT)")
        return "Initiated database."
    
@route('/process_asset', method='POST')
def process_asset():

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('name','').strip() and 
        request.POST.get('uri','').strip() and
        request.POST.get('mimetype','').strip()
        ):

        name =  request.POST.get('name','').strip()
        uri = request.POST.get('uri','').strip()
        mimetype = request.POST.get('mimetype','').strip()

        # Make sure it's a valid resource
        uri_check = urlparse(uri)
        if not (uri_check.scheme == "http" or uri_check.scheme == "https"):
            header = "Ops!"
            message = "URL must be HTTP or HTTPS."
            return template('templates/message', header=header, message=message)

        file = requests.get(uri)

        # Only proceed if fetch was successful. 
        if file.status_code == 200:
            asset_id = hashlib.md5(name+uri).hexdigest()
            
            strict_uri = uri_check.scheme + "://" + uri_check.netloc + uri_check.path

            if "image" in mimetype:
                resolution = Image.open(StringIO(file.content)).size
            else:
                resolution = "N/A"

            if "video" in mimetype:
                duration = "N/A"

            filename = uri_check.path.split('/')[-1]
            start_date = ""
            end_date = ""
            duration = ""
            
            c.execute("INSERT INTO assets (asset_id, name, filename, uri, start_date, end_date, duration, mimetype) VALUES (?,?,?,?,?,?,?,?)", (asset_id, name, filename, uri, start_date, end_date, duration, mimetype))
            conn.commit()
            
            header = "Yay!"
            message =  "Added asset (" + asset_id + ") to the database."
            return template('templates/message', header=header, message=message)
            
        else:
            header = "Ops!"
            message = "Unable to fetch file."
            return template('templates/message', header=header, message=message)
    else:
        header = "Ops!"
        message = "Invalid input."
        return template('templates/message', header=header, message=message)

@route('/process_schedule', method='POST')
def process_schedule():
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('asset','').strip() and 
        request.POST.get('start_date','').strip() and
        request.POST.get('start_time','').strip() and
        request.POST.get('end_date','').strip() and
        request.POST.get('end_time','').strip()
        ):

        asset_id =  request.POST.get('asset','').strip()
        input_start_date = request.POST.get('start_date','').strip()
        input_start_time = request.POST.get('start_time','').strip()
        start_date = datetime.strptime(input_start_date+"T"+input_start_time, '%Y-%m-%dT%H:%M:%S')
        input_end_date = request.POST.get('end_date','').strip()
        input_end_time = request.POST.get('end_time','').strip()
        end_date = datetime.strptime(input_end_date+"T"+input_end_time, '%Y-%m-%dT%H:%M:%S')

        query = c.execute("SELECT mimetype FROM assets WHERE asset_id=?", (asset_id,))
        asset_mimetype = c.fetchone()
        
        if "image" or "web" in asset_mimetype:
            try:
                duration = request.POST.get('duration','').strip()
            except:
                header = "Ops!"
                message = "Duration missing. This is required for images and web-pages."
                return template('templates/message', header=header, message=message)
        else:
            duration = "N/A"

        c.execute("UPDATE assets SET start_date=?, end_date=?, duration=? WHERE asset_id=?", (start_date, end_date, duration, asset_id))
        conn.commit()
        
        header = "Yes!"
        message = "Successfully scheduled asset."
        return template('templates/message', header=header, message=message)
        
    else:
        header = "Ops!"
        message = "Failed to process schedule."
        return template('templates/message', header=header, message=message)

@route('/update_asset', method='POST')
def update_asset():
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    if (request.POST.get('asset_id','').strip() and 
        request.POST.get('name','').strip() and
        request.POST.get('uri','').strip() and
        request.POST.get('duration','').strip() and
        request.POST.get('mimetype','').strip() and
        request.POST.get('start_date','').strip() and
        request.POST.get('start_time','').strip() and
        request.POST.get('end_date','').strip() and
        request.POST.get('end_time','').strip()
        ):

        asset_id =  request.POST.get('asset_id','').strip()
        name = request.POST.get('name','').strip()
        uri = request.POST.get('uri','').strip()
        duration = request.POST.get('duration','').strip()    
        mimetype = request.POST.get('mimetype','').strip()
        input_start_date = request.POST.get('start_date','').strip()
        input_start_time = request.POST.get('start_time','').strip()
        start_date = datetime.strptime(input_start_date+"T"+input_start_time, '%Y-%m-%dT%H:%M:%S')
        input_end_date = request.POST.get('end_date','').strip()
        input_end_time = request.POST.get('end_time','').strip()
        end_date = datetime.strptime(input_end_date+"T"+input_end_time, '%Y-%m-%dT%H:%M:%S')

        c.execute("UPDATE assets SET start_date=?, end_date=?, duration=?, name=?, uri=?, duration=?, mimetype=? WHERE asset_id=?", (start_date, end_date, duration, name, uri, duration, mimetype, asset_id))
        conn.commit()

        header = "Yes!"
        message = "Successfully updated asset."
        return template('templates/message', header=header, message=message)


    else:
        header = "Ops!"
        message = "Failed to update asset."
        return template('templates/message', header=header, message=message)


@route('/delete_asset/:asset_id')
def delete_asset(asset_id):
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()
    
    c.execute("DELETE FROM assets WHERE asset_id=?", (asset_id,))
    try:
        conn.commit()
        
        header = "Success!"
        message = "Deleted asset."
        return template('templates/message', header=header, message=message)
    except:
        header = "Ops!"
        message = "Failed to delete asset."
        return template('templates/message', header=header, message=message)

@route('/')
def viewIndex():
    return template('templates/server_standalone/index')


@route('/system_info')
def system_info():

    f = open('/tmp/screenly_viewer.log', 'r')
    viewlog = f.readlines()    
    f.close()

    loadavg = os.getloadavg()[2]
    
    # Calculate disk space
    slash = os.statvfs("/")
    free_space = size(slash.f_bsize * slash.f_bavail)
    
    # Get uptime
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
        uptime = str(timedelta(seconds = uptime_seconds))

    return template('templates/server_standalone/system_info', viewlog=viewlog, loadavg=loadavg, free_space=free_space, uptime=uptime)

@route('/splash_page')
def splash_page():

    # Make sure the database exist and that it is initated.
    initiate_db()

    my_ip = netifaces.ifaddresses('eth0')[2][0]['addr']

    return template('templates/splash_page', my_ip=my_ip)


@route('/view_playlist')
def view_node_playlist():

    nodeplaylist = json.loads(get_playlist())
    
    return template('templates/server_standalone/view_playlist', nodeplaylist=nodeplaylist)

@route('/view_assets')
def view_assets():

    nodeplaylist = json.loads(get_assets())
    
    return template('templates/server_standalone/view_assets', nodeplaylist=nodeplaylist)


@route('/add_asset')
def add_asset():
    return template('templates/server_standalone/add_asset')


@route('/schedule_asset')
def schedule_asset():
    
    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    c.execute("SELECT * FROM assets ORDER BY name")
    assetlist = c.fetchall()
    
    return template('templates/server_standalone/schedule_asset', assetlist=assetlist)
        
@route('/edit_asset/:asset_id')
def edit_asset(asset_id):

    conn = sqlite3.connect(database, detect_types=sqlite3.PARSE_DECLTYPES)
    c = conn.cursor()

    c.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,))
    asset = c.fetchone()
    
    asset_id = asset[0]
    name = asset[1]
    filename = asset[2]
    uri = asset[3]
    md5 = asset[4]

    if asset[5]:
	    start_date = datestring.date_to_string(asset[5])
    else:
	    start_date = None

    if asset[6]:
	    end_date = datestring.date_to_string(asset[6])
    else:
	    end_date = None

    duration = asset[7]
    mimetype = asset[8]

    assetdict = { "name" : name, "uri" : uri, "duration" : duration, "mimetype" : mimetype, "asset_id" : asset_id, "start_date" : start_date, "end_date" : end_date}

    return template('templates/server_standalone/edit_asset', asset=assetdict)
        
# Static
@route('/static/:path#.+#', name='static')
def static(path):
    return static_file(path, root='static')

@error(403)
def mistake403(code):
    return 'The parameter you passed has the wrong format!'

@error(404)
def mistake404(code):
    return 'Sorry, this page does not exist!'

run(host='0.0.0.0', port=8080, reloader=True)