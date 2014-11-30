from genericpath import isfile
import os
import re
import urllib
import datetime

from flask import render_template, request, url_for, redirect, jsonify, Response
import myapp
from persistence import Tourney, TourneyList, PersistenceManager, List, Faction, Ship, ShipUpgrade, UpgradeType, Upgrade

import xwingmetadata

app =  myapp.create_app()
UPLOAD_FOLDER = "static/tourneys"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = set( ['png', 'jpg', 'jpeg', 'gif'])

is_maintenance_mode = False

here = os.path.dirname(__file__)
static_dir = os.path.join( here, app.config['UPLOAD_FOLDER'] )

ADMINS = ['sozinsky@gmail.com']

session = myapp.db_connector.get_session()

@app.before_request
def check_for_maintenance():
    if is_maintenance_mode and request.path != url_for('down'):
        return redirect(url_for('down'))

@app.teardown_appcontext
def shutdown_session(exception=None):
    session.remove()

@app.route("/about")
def about():
    return render_template('about.html')

@app.route("/tourneys")
def tourneys():
    admin_on = request.args.get('admin')
    if admin_on is not None:
        admin_on = True
    else:
        admin_on = False
    summary = PersistenceManager(myapp.db_connector).get_tourney_summary()
    return render_template('tourneys.html', tourneys=summary, admin=admin_on )


@app.route("/new")
def new():
    return render_template('new.html')

def generate( rows ):
    for r in rows:
        yield ",".join(r) + "\n"

def get_tourney_lists_as_text(tourney, make_header=True ):

    rows   = []
    header =  xwingmetadata.header()

    if make_header:
        rows.append( header )

    tourney_date = "%d/%d/%d" % ( tourney.tourney_date.month, tourney.tourney_date.day, tourney.tourney_date.year )
    row_defaults = [ tourney.tourney_name, tourney.tourney_type, tourney_date ]

    for tourney_list in tourney.tourney_lists:
        if tourney_list.list is None or tourney_list.list.ships is None or len(tourney_list.list.ships) == 0:
            new_row = []
            new_row.extend ( row_defaults )
            for i in range (len(new_row), len(header)):
                new_row.append('')
            rows.append(new_row)
        else:
            for ship in tourney_list.list.ships:
                new_row = []
                new_row.extend( row_defaults )
                new_row.extend( [ tourney_list.player_name,
                                  tourney_list.list.faction.description,
                                  str(tourney_list.list.points),
                                  str(tourney_list.tourney_standing),
                                  str(tourney_list.id),
                                  ship.ship_pilot.ship_type.description,
                                  ship.ship_pilot.pilot.name
                ] )

                for i in range(len(new_row), len(header)):
                    new_row.append( ship.get_upgrade( header[i]  ) )

                rows.append(new_row)
    return rows

def csv_response(rows, name):
    disposition = "attachment; filename=" + name
    return Response(generate(rows), mimetype='text/csv', headers={'Content-Disposition': disposition} )


@app.route("/export_all_lists")
def export_all_lists():
    pm          = PersistenceManager(myapp.db_connector)
    tourneys    = pm.get_tourneys();
    make_header = True
    rows        = []
    for tourney in tourneys:
        ret = get_tourney_lists_as_text(tourney, make_header)
        make_header = False
        rows.extend( ret )
    return csv_response( rows, "all_lists_download.csv")


@app.route("/export_tourney_lists")
def export_tourney_lists():
    tourney_id = request.args.get('tourney_id')
    pm         = PersistenceManager(myapp.db_connector)
    tourney    = pm.get_tourney_by_id(tourney_id)

    ret = get_tourney_lists_as_text(tourney)
    return csv_response( ret, "tourney_list_download.csv")




@app.route("/delete_tourney")
def delete_tourney():
    tourney_name = request.args.get('tourney')
    pm = PersistenceManager(myapp.db_connector)
    pm.delete_tourney(tourney_name)
    return redirect(url_for('tourneys') )

@app.route("/add_tourney",methods=['POST'])
def add_tourney():
    name   = request.form['name']
    folder = request.form['folder']
    type   = request.form['tourney_type']
    mmddyyyy = request.form['date'].split('/')
    date   = datetime.date( int(mmddyyyy[2]),int(mmddyyyy[0]), int(mmddyyyy[1]))

    #load all the files in the folder
    folder_path = os.path.join(static_dir, folder)
    tourney_files = {}
    for f in os.listdir(folder_path):
        if isfile(os.path.join(folder_path,f)):
            player_name = os.path.splitext(f)[0]
            tourney_files[player_name] = UPLOAD_FOLDER +  "/" + folder + "/" + f

    tourney = Tourney(tourney_name=name, tourney_date=date, tourney_type=type)
    myapp.db_connector.get_session().add(tourney)
    myapp.db_connector.get_session().commit()

    lists   = []
    for player_name in tourney_files.keys():
        f = tourney_files[player_name]

        try:

            match = re.match(r'^(.*?)\s+(\d+)',player_name)

            tourney_list = TourneyList( tourney_id=tourney.id,
                                        image=f,
                                        player_name=match.group(1),
                                        tourney_standing=match.group(2))
            lists.append( tourney_list )
        except:
            print ("unable to load file name %s" % ( player_name ))

    myapp.db_connector.get_session().add_all( lists )
    myapp.db_connector.get_session().commit()

    return redirect(url_for('tourneys') )



@app.route("/browse_list")
def browse_list():
    tourney_name = request.args.get('tourney')
    admin        = request.args.get('admin')
    pm = PersistenceManager(myapp.db_connector)
    tourney = pm.get_tourney(tourney_name)
    tourney_lists = tourney.tourney_lists
    return render_template( 'tourney_lists.html', tourney=tourney, tourney_lists=tourney_lists, admin=admin)

@app.route("/delete_list_and_retry")
def delete_list_and_retry():
    tourney_list_id = request.args.get('tourney_list_id')

    pm = PersistenceManager(myapp.db_connector)
    tourney_list = pm.get_tourney_list(tourney_list_id)
    pm.delete_tourney_list_details( tourney_list )
    return redirect( url_for('enter_list', tourney=tourney_list.tourney.id, tourney_list_id=tourney_list.id ) )


@app.route("/delete_list")
def delete_list():
    tourney_list_id = request.args.get('tourney_list_id')
    tourney_name    = request.args.get('tourney')
    admin           = request.args.get('admin')

    pm = PersistenceManager(myapp.db_connector)
    tourney_list = pm.get_tourney_list(tourney_list_id)
    pm.delete_tourney_list_details( tourney_list )
    return redirect( url_for('browse_list', tourney=tourney_name, admin=admin ) )



@app.route( "/success")
def success():
    tourney_name = request.args.get("tourney_name")
    return render_template( "success_kid.html", tourney_name=tourney_name)


@app.route("/enter_list")
def enter_list():
    tourney_id    = request.args.get('tourney')
    tourney_list_id = request.args.get('tourney_list_id')

    pm = PersistenceManager(myapp.db_connector)
    tourney_list = None
    tourney = None

    if tourney_list_id is None:
        tourney = pm.get_tourney_by_id(tourney_id)
        tourney_list = pm.get_random_tourney_list(tourney)
        if tourney_list is None:
            return redirect(url_for( "success", tourney_name=tourney.tourney_name ) )
    else:
        tourney_list = pm.get_tourney_list(tourney_list_id)
        tourney      = tourney_list.tourney

    m = xwingmetadata.XWingMetaData()
    return render_template('list_entry.html',
                           meta=m,
                           image_src=urllib.quote(tourney_list.image),
                           tourney_list=tourney_list,
                           tourney_list_id=tourney_list.id,
                           tourney_id=tourney.id )

@app.route("/add_squad",methods=['POST'])
def add_squad():
         data    = request.json['data']
         points  = request.json['points']
         faction = request.json['faction']

         tourney_id = request.args.get('tourney_id')
         tourney_list_id = request.args.get('tourney_list_id')

         pm = PersistenceManager(myapp.db_connector)
         tourney_list = pm.get_tourney_list(tourney_list_id)
         list = List(faction=Faction.from_string(faction), points=points)
         tourney_list.list = list
         pm.db_connector.get_session().add( list )
         pm.db_connector.get_session().commit()

         ships = []
         for squad_member in data:
             ship_pilot = pm.get_ship_pilot( squad_member['ship'], squad_member['pilot'] )
             ship       = Ship( ship_pilot_id=ship_pilot.id, list_id=list.id)
             list.ships.append( ship )
             for upgrade in squad_member['upgrades']:
                 ship_upgrade = ShipUpgrade( ship_id=ship.id,
                                             upgrade=Upgrade( upgrade_type= UpgradeType.from_string( upgrade['type'] ),
                                                                     name = upgrade['name'] ) )
                 ship.upgrades.append( ship_upgrade )
             ships.append( ship )

         pm.db_connector.get_session().add_all( ships )
         pm.db_connector.get_session().commit()

         return jsonify(tourney_id=tourney_id, tourney_list_id=tourney_list.id)

@app.route('/display_list')
def display_list():
    tourney_list_id = request.args.get('tourney_list_id')
    admin           = request.args.get('admin')
    pm = PersistenceManager(myapp.db_connector)
    tourney_list = pm.get_tourney_list(tourney_list_id)
    m = xwingmetadata.XWingMetaData()
    return render_template('list_display.html',
                           meta=m,
                           admin=admin,
                           image_src=urllib.quote(tourney_list.image),
                           tourney_list=tourney_list,
                           tourney_list_id=tourney_list.id,
                           tourney=tourney_list.tourney,
                           tourney_id=tourney_list.tourney.id )

@app.route('/down')
def down():
    return render_template( 'down.html')

@app.route('/')
def index():
    return redirect(url_for('tourneys') )

def to_float(dec):
    return float("{0:.2f}".format( float(dec) * float(100)))


@app.route("/charts")
def charts():
    pm = PersistenceManager(myapp.db_connector)
    faction_breakout    = pm.get_faction_breakout()
    ship_breakout       = pm.get_ship_breakout()
    ship_pilot_breakout = pm.get_ship_pilot_breakout()

    faction_data = []
    faction_drilldowns = {}

    for fba in faction_breakout.all():
        drilldown =  {
              'name': fba[0].description,
              'categories': [],
              'data' : [],
              'color' : None
        }
        faction_drilldowns[ fba[0].description] = drilldown
        faction_data.append( { 'y' : to_float(fba[1]),
            'color' : None,
            'drilldown' : drilldown
        })

    for sba in ship_breakout.all():
        drilldown = faction_drilldowns[ sba[0].description]
        drilldown[ 'categories'].append( sba[1].description)
        drilldown[ 'data'].append(to_float(sba[2]) )

    spd_drilldowns = {}
    ship_pilot_data = []
    for sba in ship_breakout.all():
        drilldown = {
            'name' : sba[1].description,
            'categories': [],
            'data' : [],
            'color' : None,
            'faction' : sba[0].description
        }
        spd_drilldowns[ sba[1].description ] = drilldown
        ship_pilot_data.append( { 'y' : to_float( sba[2]),
                       'color': None,
                       'drilldown' : drilldown } )

    for spb in ship_pilot_breakout.all():
        drilldown = spd_drilldowns[ spb[1].description ]
        drilldown[ 'categories'].append( spb[2])
        drilldown[ 'data' ].append( to_float( spb[3]))

    ut_drilldowns    = {}
    ut_data          = []

    upgrade_type_breakout = pm.get_upgrade_type_breakout()
    upgrade_breakout = pm.get_upgrade_breakout()

    for utb in upgrade_type_breakout.all():
        drilldown = {
            'name': utb[0].description,
            'categories': [],
            'data': [],
            'color': None,
        }
        ut_drilldowns[utb[0].description] = drilldown
        ut_data.append({'y': to_float(utb[1]),
                        'color': None,
                        'drilldown': drilldown})


    for ub in upgrade_breakout.all():
        drilldown = ut_drilldowns[ub[0].description]
        drilldown['categories'].append(ub[1])
        drilldown['data'].append(to_float(ub[2]))



    return render_template('charts.html', faction_data=faction_data,
                                          pilot_data=ship_pilot_data,
                                          upgrade_data=ut_data)

if __name__ == '__main__':
    app.debug = True
    app.run()
