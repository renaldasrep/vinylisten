#!/usr/bin/env python
import config
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

import time, os, thread, subprocess, requests, json, re, eventlet
import xml.etree.ElementTree as ET

eventlet.monkey_patch()

debug = True

def printr(x):
    if debug:
        print(x)
        return x

### SUBPROCESSES ###
ADB_DISCONNECT = "adb disconnect".split()
ADB_TCPIP = "adb tcpip 5555".split()
ADB_CONNECT = ("adb connect " + config.android_device_ip).split()
###
ADB_SHELL = "adb shell " if config.android_device_id is None else "adb -s " + config.android_device_id + " shell "
###
ADB_CLOSE_SHAZAM = (ADB_SHELL + "am force-stop com.shazam.android -W").split()
ADB_OPEN_SHAZAM_AND_LISTEN = (ADB_SHELL + "am start -n com.shazam.android/.activities.MainActivity -a com.shazam.android.intent.actions.START_TAGGING").split()
ADB_CHECK_CURRENT_ACTIVITY_STACK = (ADB_SHELL + "dumpsys activity activities | grep 'Hist #' | grep 'com.shazam.android'").split()
ADB_READ_LAYOUT = (ADB_SHELL + "cat $(uiautomator dump | grep -oE '[^ ]+.xml')").split()
###
FNULL = open(os.devnull, 'w')
### END OF SUBPROCESSES LIST ###

app = Flask(__name__ , static_url_path='/static')
socketio = SocketIO(app)

data, DATA_EMPTY = ({
    "artist": "",
    "title": "",
    "cover": False
},) * 2

def vinylisten():
    last_log, last_track, timeout_counter = "", "", 0
    while(True):
        global data
        if timeout_counter >= 3:
            printr("Resetting to blank")
            timeout_counter = 0
            data = DATA_EMPTY
            socketio.emit("data", data, namespace="/socket")

        if (config.android_device_ip != None):
            subprocess.call(ADB_DISCONNECT, stdout=FNULL, stderr=FNULL)
            subprocess.call(ADB_TCPIP, stdout=FNULL, stderr=FNULL)
            subprocess.call(ADB_CONNECT, stdout=FNULL, stderr=FNULL)


        subprocess.call(ADB_CLOSE_SHAZAM, stdout=FNULL, stderr=FNULL)
        subprocess.call(ADB_OPEN_SHAZAM_AND_LISTEN, stdout=FNULL, stderr=FNULL)

        tagging = True

        timeout = time.time() + 15

        while(tagging):
            try:
                output = subprocess.check_output(ADB_CHECK_CURRENT_ACTIVITY_STACK, stderr=FNULL)
            except (subprocess.CalledProcessError) as e:
                if last_log != "Device not found or is failing to read Shazam":
                    last_log = printr("Device not found or is failing to read Shazam")
                break
            if "TaggingActivity" in output:
                if time.time() > timeout:
                    printr("Timeout at TaggingActivity")
                    last_log = ""
                    timeout_counter += 1
                    break
                if last_log != "Listening":
                    last_log = printr("Listening")
            elif "MusicDetailsInterstitialActivity" in output:
                if time.time() > timeout:
                    printr("Timeout at MusicDetailsInterstitialActivity")
                    last_log = ""
                    timeout_counter += 1
                    break
                if last_log != "Loading":
                    last_log = printr("Loading")
            elif "MusicDetailsActivity" in output:
                if time.time() > timeout:
                    printr("Timeout at MusicDetailsActivity")
                    last_log = ""
                    timeout_counter += 1
                    break
                tagging = False
                printr("Fetching result")
                try:
                    output = subprocess.check_output(ADB_READ_LAYOUT, stderr=FNULL)
                except (subprocess.CalledProcessError) as e:
                    if last_log != "Device not found":
                        last_log = printr("Device not found")
                    break
                try:
                    root = ET.fromstring(output)
                    data["title"] = root.findall(".//node[@resource-id='com.shazam.android:id/music_details_title']")[0].get("text")
                    data["artist"] = root.findall(".//node[@resource-id='com.shazam.android:id/music_details_subtitle']")[0].get("text")
                except (ET.ParseError, IndexError) as e:
                    printr("Failed to read layout")
                    break
                timeout_counter = 0
                if (last_track != data["artist"] + " - " + data["title"]):
                    last_track = data["artist"] + " - " + data["title"]
                    print(last_track)
                    try:
                        response = requests.post("https://accounts.spotify.com/api/token", data = {"client_id" : config.spotify_client_id, "client_secret": config.spotify_client_secret, "grant_type": "client_credentials"})
                        spotify_access_token = json.loads(response.text)["access_token"]
                    except (requests.ConnectionError, IndexError) as e:
                        printr("Failed to authorize")
                        break
                    try:
                        spotify_search_query = "artist:" + re.sub(r"\".*?\" ", "", data["artist"].lower().replace(" & ", ", ").replace(" feat. ", ", ")) + " track:" + data["title"].lower().replace("'", "")
                        response = requests.get("https://api.spotify.com/v1/search", params = { "access_token": spotify_access_token, "q": spotify_search_query, "type": "track", "limit": "1" })
                        with open("./static/cover.jpg", "wb") as outfile: 
                            outfile.write(requests.get(json.loads(response.text)["tracks"]["items"][0]["album"]["images"][0]["url"]).content)
                            outfile.close()
                        data["cover"] = True
                    except (requests.ConnectionError, IndexError) as e:
                        printr("Failed to get cover image")
                        data["cover"] = False
                        pass
                    socketio.emit("data", data, namespace="/socket")
                else:
                    printr("No change")
            elif "MainActivity" in output:
                if time.time() > timeout:
                    printr("Timeout at MainActivity")
                    last_log = ""
                    timeout_counter += 1
                    break
                if last_log != "Waiting":
                    last_log = printr("Waiting")
            else:
                if time.time() > timeout:
                    printr("Timeout at UnknownActivity")
                    last_log = ""
                    timeout_counter += 1
                    break
                if last_log != "UnknownActivity":
                    last_log = printr("UnknownActivity")

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

@app.route("/")
def index():
    return render_template("index.html")

@socketio.on("connect", namespace="/socket")
def client_connect():
    printr("Client connected")
    emit("data", data, namespace="/socket")

@socketio.on("disconnect", namespace="/socket")
def client_disconnect():
    printr("Client disconnected")

if __name__ == "__main__":
    thread.start_new_thread(vinylisten)
    socketio.run(app, host="0.0.0.0")