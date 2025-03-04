import os
import flask
from flask import request, render_template, jsonify
from flask_wtf.csrf import CSRFProtect
from flask_minify import minify
import json
import time, threading
import logging
import logging.config
from lib.dxtelnet import who
from lib.adxo import get_adxo_events
from lib.qry import query_manager
__author__ = 'IU1BOW - Corrado'


logging.config.fileConfig("cfg/webapp_log_config.ini", disable_existing_loggers=True)
logger = logging.getLogger(__name__)
logger.info("Start")

app = flask.Flask(__name__)
app.config["DEBUG"] = False
app.config['SECRET_KEY'] = 'secret!'
app.config['WTF_CSRF_SECRET_KEY']='wtfsecret!'
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
)

csrf = CSRFProtect(app)
minify(app=app, html=True, js=True,cssless=False)
#minify(app=app, html=False, js=False,cssless=False)


#load config file
with open('cfg/config.json') as json_data_file:
        cfg = json.load(json_data_file)

#load bands file
with open('cfg/bands.json') as json_bands:
        band_frequencies = json.load(json_bands)

#load mode file
with open('cfg/modes.json') as json_modes:
        modes_frequencies = json.load(json_modes)

#load continents-cq file
with open('cfg/continents.json') as json_continents:
        continents_cq = json.load(json_continents)

#create object query manager
qm=query_manager()

#load country file (and send it to front-end)
def load_country():
#    filename = os.path.join(app.static_folder, 'country.json')
#    with open(filename) as country_file:
#        return json.load(country_file)
     with open('cfg/country.json') as json_country:
        return  json.load(json_country)
	

#find id  in json : ie frequency / continent
def find_id_json(json_object, name):
    return [obj for obj in json_object if obj['id']==name][0]

#the main query to show spots
#it gets url parameter in order to apply the build the right query
#and apply the filter required. It returns a json with the spots
def spotquery():

    try:
        #get url parameters
        band=(request.args.getlist('b'))
        dere=(request.args.getlist('e'))
        dxre=(request.args.getlist('x'))
        mode=(request.args.getlist('m'))
        callsign=request.args.get('c')  

        query_string=''
        if callsign:
            #construct the query, to show last 6 month
            if len(callsign)<=14:
                query_string="(SELECT rowid, spotter AS de, freq, spotcall AS dx, comment AS comm, time, spotdxcc from dxcluster.spot WHERE spotter='"+callsign+"'"                    
                query_string+=" ORDER BY rowid desc limit 10)"
                query_string+=" UNION "
                query_string+="(SELECT rowid, spotter AS de, freq, spotcall AS dx, comment AS comm, time, spotdxcc from dxcluster.spot WHERE spotcall='"+callsign+"'" 
                query_string+=" ORDER BY rowid desc limit 10);"
            else:
                logging.warning('callsign too long')

        else:    
            #construct band query decoding frequencies with json file
            band_qry_string = ' AND (('
            for i in range(len(band)):
                freq=find_id_json(band_frequencies["bands"],band[i])
                if i > 0:
                    band_qry_string += ') OR ('

                band_qry_string += 'freq BETWEEN ' + str(freq["min"]) + ' AND ' + str(freq["max"])

            band_qry_string += '))'

            #construct mode query 
            mode_qry_string = ' AND  (('
            for i in range(len(mode)):
                single_mode=find_id_json(modes_frequencies["modes"],mode[i])
                if i > 0: 
                        mode_qry_string +=') OR ('
                for j in range(len(single_mode["freq"])):
                    if j > 0: 
                        mode_qry_string +=') OR ('
                    mode_qry_string += 'freq BETWEEN ' +str(single_mode["freq"][j]["min"]) + ' AND ' + str(single_mode["freq"][j]["max"])

            mode_qry_string += '))'

            #construct DE continent region query
            dere_qry_string = ' AND spottercq IN ('
            for i in range(len(dere)):
                continent=find_id_json(continents_cq["continents"],dere[i])
                if i > 0:
                    dere_qry_string +=','
                dere_qry_string += str(continent["cq"])
            dere_qry_string +=')'
        
            #construct DX continent region query
            dxre_qry_string = ' AND spotcq IN ('
            for i in range(len(dxre)):
                continent=find_id_json(continents_cq["continents"],dxre[i])
                if i > 0:
                    dxre_qry_string +=','
                dxre_qry_string += str(continent["cq"])
            dxre_qry_string +=')'


            query_string="SELECT rowid, spotter AS de, freq, spotcall AS dx, comment AS comm, time, spotdxcc from dxcluster.spot WHERE 1=1"                                  
            if len(band) > 0:
                query_string += band_qry_string

            if len(mode) > 0:
                query_string += mode_qry_string

            if len(dere) > 0:
                query_string += dere_qry_string

            if len(dxre) > 0:
                query_string += dxre_qry_string

            query_string += " ORDER BY rowid desc limit 50;"  

        logger.debug(query_string)
        qm.qry(query_string)
        data=qm.get_data()
        row_headers=qm.get_headers()

        logger.debug("query done")
        logger.debug (data)

        if data is None or len(data)==0:
              logger.warning("no data found")

        payload=[]
        for result in data:
            payload.append(dict(zip(row_headers,result)))
        return payload
    except Exception as e:
        logger.error(e)

#find adxo events
adxo_events=None

def get_adxo():
    global adxo_events
    adxo_events=get_adxo_events()
    threading.Timer(12*3600,get_adxo).start()

get_adxo()

@app.route('/spotlist', methods=['GET']) 
def spotlist():
    response=flask.Response(json.dumps(spotquery()))
    return response

def who_is_connected():
    host_port=cfg['telnet'].split(':')
    response=who(host_port[0],host_port[1],cfg['mycallsign'])
    return response

@app.route('/', methods=['GET']) 
@app.route('/index.html', methods=['GET']) 
def spots():
    payload=spotquery()
    country_data=load_country()
    response=flask.Response(render_template('index.html',mycallsign=cfg['mycallsign'],telnet=cfg['telnet'],mail=cfg['mail'],menu_list=cfg['menu']['menu_list'],payload=payload,timer_interval=cfg['timer']['interval'],country_data=country_data,adxo_events=adxo_events))
    return response

@app.route('/service-worker.js', methods=['GET'])
def sw():
    return app.send_static_file('service-worker.js')

@app.route('/offline.html')
def root():
        return app.send_static_file('html/offline.html')


@app.route('/plotlist', methods=['GET']) 
def plotlist():
    #get url parameters
    idxfile=os.path.join(app.root_path,os.path.basename(app.static_url_path),'plots','plots.json')
    if os.path.exists(idxfile):
        with open(idxfile,'r') as jsonfile:
            json_content = json.load(jsonfile)
    else:
        json_content={}

    response=json_content
    return response

@app.route('/plots.html')
def plots():
    payload=plotlist()  
    whoj=who_is_connected()
    response=flask.Response(render_template('plots.html',mycallsign=cfg['mycallsign'],telnet=cfg['telnet'],mail=cfg['mail'],menu_list=cfg['menu']['menu_list'],payload=payload,timer_interval=cfg['plot_refresh_timer']['interval'],who=whoj))
    return response


@app.route('/cookies.html', methods=['GET'])
def cookies():
    response=flask.Response(render_template('cookies.html',mycallsign=cfg['mycallsign'],telnet=cfg['telnet'],mail=cfg['mail'],menu_list=cfg['menu']['menu_list']))
    return response

@app.route('/privacy.html', methods=['GET'])
def privacy():
    response=flask.Response(render_template('privacy.html',mycallsign=cfg['mycallsign'],telnet=cfg['telnet'],mail=cfg['mail'],menu_list=cfg['menu']['menu_list']))
    return response

@app.route('/sitemap.xml')
def sitemap():
        return app.send_static_file('sitemap.xml')

@app.route('/callsign.html', methods=['GET']) 
def callsign():
    payload=spotquery()  
    country_data=load_country()
    callsign=request.args.get('c')
    response=flask.Response(render_template('callsign.html',mycallsign=cfg['mycallsign'],telnet=cfg['telnet'],mail=cfg['mail'],menu_list=cfg['menu']['menu_list'],payload=payload,timer_interval=cfg['timer']['interval'],country_data=country_data,callsign=callsign,adxo_events=adxo_events))
    return response

@app.after_request
def add_security_headers(resp):
#    resp.headers['Content-Security-Policy']='script-src \'self\' cdnjs.cloudflare.com cdn.jsdelivr.net \'unsafe-inline\''
    resp.headers['Strict-Transport-Security']='max-age=1000'
    resp.headers['X-Xss-Protection']='1; mode=block'
    resp.headers['X-Frame-Options']='SAMEORIGIN'
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    #resp.headers['Cache-Control']='no-store, max-age=0'
    resp.headers['Cache-Control']='no-cache, no-store, must-revalidate'
    resp.headers['Pragma']='no-cache'
   # resp.headers['Access-Control-Allow-Origin']='https://cdnjs.cloudflare.com'
    return resp
	
    
if __name__ == '__main__':
    app.run(host='0.0.0.0')
