"""
Module defining several DB utility function for other scripts
"""
import os
from object_recognition_core.boost.interface import ObjectDbParameters, ObjectDbTypes
from object_recognition_core.db.object_db import core_db_types
import tools as dbtools

DEFAULT_DB_COLLECTION = 'object_recognition'
DEFAULT_DB_ROOT = 'http://localhost:5984'
DEFAULT_DB_TYPE = 'CouchDB'


def create_db(db_name, couch):
    ''' Create and return a handle to the specified couch db database.
    Will attempt to find the existing db,
    and create if it doesn't already exist.
    @param db_name: The short name for the database, e.g. 'bags','objects','sessions'
    '''
    if db_name in couch:
        db = couch[db_name]
    else:
        db = couch.create(db_name)
    return db


def init_object_databases(couch, db_name='object_recognition'):
    db = create_db('object_recognition', couch)
    import models
    models.sync_models(db)
    return db


def add_db_arguments(parser, do_default=True, do_commit=True):
    '''Appends some common arguments to the argparse parser.
    db_type will contain the type of DB (CouchDB, SQL ...).
    db_root will contain the server url.
    '''
    group = parser.add_argument_group('Database Parameters')
    if do_default:
        group.add_argument('--db_type', metavar='DB_TYPE', dest='db_type', type=str, choices=['CouchDB'],
                           default=DEFAULT_DB_TYPE,
                           help='The type of database used: one of [%(choices)s]. Default: %(default)s')
        group.add_argument('--db_root', metavar='DB_ROOT_URL', dest='db_root', type=str, default=DEFAULT_DB_ROOT,
                           help='The database root URL to connect to. Default: %(default)s')
        group.add_argument('--db_collection', metavar='DB_COLLECTION', dest='db_collection', type=str,
                           default=DEFAULT_DB_COLLECTION,
                           help='The database root URL to connect to. Default: %(default)s')
    else:
        group.add_argument('--db_type', metavar='DB_TYPE', dest='db_type', type=str, choices=['CouchDB'],
                           help='The type of database used: one of [%(choices)s].')
        group.add_argument('--db_root', metavar='DB_ROOT_URL', dest='db_root', type=str,
                           help='The database root URL to connect to.')
        group.add_argument('--db_collection', metavar='DB_COLLECTION', dest='db_collection', type=str,
                           default='object_recognition', help='The database root URL to connect to.')
    if do_commit:
        group.add_argument('--commit', dest='commit', action='store_true',
                           default=False, help='Commit the data to the database.')
    return group


def args_to_db_params(args, secondary_parameters={}):
    """
    Given command line parsed args, create an ObjectDbParameters object. The keys in args have to be:
    'db_type', 'db_root', 'db_collection'
    Any parameter that is not in the args will be taken from the dictionary secondary_parameters, where the keys are:
    'type', 'url', 'collection'
    """
    dic = {}
    remap_dic = {'db_type': 'type', 'db_root': 'root',
                 'db_collection': 'collection'}
    for args_key, secondary_key in remap_dic.iteritems():
        if hasattr(args, args_key):
            dic[secondary_key] = getattr(args, args_key)
        if secondary_parameters.has_key(secondary_key):
            dic[secondary_key] = secondary_parameters[secondary_key]
    return ObjectDbParameters(dic)


def db_params_to_db(db_params):
    """
    Given a ObjectDbParameters, return  db object
    """
    if db_params.type == ObjectDbTypes.COUCHDB:
        import couchdb
        return init_object_databases(couchdb.Server(db_params.raw['root']))

########################################################################################################################


def upload_mesh(db, object_id, original_path, cloud_path=None, mesh_path=None, use_material=False):

    import models
    r = models.find_model_for_object(db, object_id, 'mesh')
    m = None
    for model in r:
        m = models.Model.load(db, model)
        print "updating model:", model
        break
    if not m:
        m = models.Model(object_id=object_id, method='mesh')
        print "creating new model."
    m.store(db)
    with open(original_path, 'r') as mesh:
        db.put_attachment(m, mesh, filename='original' +
                          os.path.splitext(original_path)[1])
    if cloud_path:
        with open(cloud_path, 'r') as mesh:
            db.put_attachment(m, mesh, filename='cloud.ply',
                              content_type='application/octet-stream')
    # else:
    # TODO: convert the original to mesh/cloud if not given
    if mesh_path:
        with open(mesh_path, 'r') as mesh:
            db.put_attachment(m, mesh, filename='mesh.stl',
                              content_type='application/octet-stream')

    if use_material and original_path.endswith('.obj'):
        material_path = get_material_path(original_path)

        with open(material_path, 'r') as material:
            db.put_attachment(m, material, filename=os.path.basename(
                material_path), content_type='application/octet-stream')
            print('Adding material: ' + material_path)

        # with open()
        texture_paths = get_texture_paths(material_path)
        for texture_path in texture_paths:
            with open(texture_path, 'r') as texture:
                db.put_attachment(m, texture, filename=os.path.basename(
                    texture_path), content_type='application/octet-stream')
                print('Adding texture: ' + texture_path)

        return


def get_material_path(mesh_path):
    dir = os.path.abspath('./')
    for line in open(mesh_path):
        if line.startswith('mtllib'):
            material_path = line.split()[-1]
            if not material_path.startswith('/'):
                material_path = dir + '/' + material_path
            elif material_path.startswith('./'):
                material_path = material_path[2:]
                material_path = dir + material_path

    return material_path


def get_texture_paths(material_path):
    texture_paths = []
    dir = os.path.abspath('./')
    for line in open(material_path):
        if line.startswith('map_Kd'):
            texture_path = line.split()[-1]
            if not texture_path.startswith('/'):
                texture_path = dir + '/' + texture_path
            elif texture_path.startswith('./'):
                texture_path = texture_path[2:]
                texture_path = dir + texture_path

            texture_paths.append(texture_path)

    return texture_paths

########################################################################################################################


def interpret_object_ids(db_params, ids=[], names=[]):
    """
    Given db parameters, clean the 'object_ids' field to be a list of object ids
    (as it could be the string 'all')
    """
    db_type = eval(db_params).get('type', '')
    if db_type.lower() not in core_db_types():
        return []

    # initialize the DB
    if isinstance(ids, str) and ids != 'all' and ids != 'missing':
        ids = eval(ids)
    if isinstance(names, str) and names != 'all' and names != 'missing':
        names = eval(names)

    if not ids and not names:
        return []

    object_ids = set()

    db = dbtools.db_params_to_db(ObjectDbParameters(db_params))
    import models
    if 'all' in (ids, names):
        # unicode without the str()
        return set([str(x.id) for x in models.Object.all(db)])
    if 'missing' in (ids, names):
        tmp_object_ids = set([str(x.id) for x in models.Object.all(db)])
        tmp_object_ids_from_names = set(
            [str(x.object_id) for x in models.Model.all(db)])
        object_ids.update(tmp_object_ids.difference(tmp_object_ids_from_names))

    if ids and ids != 'missing':
        object_ids.update(ids)
    if names and names != 'missing':
        for object_name in names:
            object_ids.update([str(x.id)
                               for x in models.objects_by_name(db, object_name)])

    if isinstance(object_ids, set):
        return list(object_ids)
    else:
        return []
