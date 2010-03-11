"""
A Python "serializer". Doesn't do much serializing per se -- just converts to
and from basic Python data types (lists, dicts, strings, etc.). Useful as a basis for
other serializers.
"""

from django.conf import settings
from django.core.serializers import base
from django.db import models
from django.utils.encoding import smart_unicode, is_protected_type

from google.appengine.api import datastore_types
from google.appengine.ext import db

import re
from datetime import datetime

def parse_datetime(s):
    """Create datetime object representing date/time
       expressed in a string
 
    Takes a string in the format produced by calling str()
    on a python datetime object and returns a datetime
    instance that would produce that string.
 
    Acceptable formats are: "YYYY-MM-DD HH:MM:SS.ssssss+HH:MM",
                            "YYYY-MM-DD HH:MM:SS.ssssss",
                            "YYYY-MM-DD HH:MM:SS+HH:MM",
                            "YYYY-MM-DD HH:MM:SS"
    Where ssssss represents fractional seconds.     The timezone
    is optional and may be either positive or negative
    hours/minutes east of UTC.
    """
    if s is None:
        return None
    # Split string in the form 2007-06-18 19:39:25.3300-07:00
    # into its constituent date/time, microseconds, and
    # timezone fields where microseconds and timezone are
    # optional.
    m = re.match(r'(.*?)(?:\.(\d+))?(([-+]\d{1,2}):(\d{2}))?$',
                 str(s))
    datestr, fractional, tzname, tzhour, tzmin = m.groups()
 
    # Create tzinfo object representing the timezone
    # expressed in the input string.  The names we give
    # for the timezones are lame: they are just the offset
    # from UTC (as it appeared in the input string).  We
    # handle UTC specially since it is a very common case
    # and we know its name.
    if tzname is None:
        tz = None
    else:
        tzhour, tzmin = int(tzhour), int(tzmin)
        if tzhour == tzmin == 0:
            tzname = 'UTC'
        tz = FixedOffset(timedelta(hours=tzhour,
                                   minutes=tzmin), tzname)
 
    # Convert the date/time field into a python datetime
    # object.
    x = datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S")
 
    # Convert the fractional second portion into a count
    # of microseconds.
    if fractional is None:
        fractional = '0'
    fracpower = 6 - len(fractional)
    fractional = float(fractional) * (10 ** fracpower)
 
    # Return updated datetime object with microseconds and
    # timezone information.
    return x.replace(microsecond=int(fractional), tzinfo=tz)


class FakeParent(object):
    """Fake parent 'model' like object.

    This class exists to allow a parent object to be provided to a new model
    without having to load the parent instance itself.
    """

    def __init__(self, parent_key):
        self._entity = parent_key

class Serializer(base.Serializer):
    """
    Serializes a QuerySet to basic Python objects.
    """

    internal_use_only = True

    def start_serialization(self):
        self._current = None
        self.objects = []

    def end_serialization(self):
        pass

    def start_object(self, obj):
        self._current = {}

    def end_object(self, obj):
        self.objects.append({
            "model"  : smart_unicode(obj._meta),
            "pk"     : smart_unicode(obj._get_pk_val(), strings_only=True),
            "fields" : self._current
        })
        self._current = None

    def handle_field(self, obj, field):
        data = getattr(obj, field.name)
        if isinstance(data, (list, tuple)):
            serialized = [smart_unicode(item, strings_only=True) for item in data]
        elif isinstance(data, datetime):
            serialized = unicode(data)
        else:
            serialized = smart_unicode(data, strings_only=True)
        self._current[field.name] = serialized

    def handle_fk_field(self, obj, field):
        related = getattr(obj, field.name)
        if related is not None:
            if field.rel.field_name == related._meta.pk.name:
                # Related to remote object via primary key
                related = related._get_pk_val()
            else:
                # Related to remote object via other field
                related = getattr(related, field.rel.field_name)
        self._current[field.name] = smart_unicode(related, strings_only=True)

    def handle_m2m_field(self, obj, field):
        if field.creates_table:
            self._current[field.name] = [smart_unicode(related._get_pk_val(), strings_only=True)
                               for related in getattr(obj, field.name).iterator()]

    def getvalue(self):
        return self.objects

def Deserializer(object_list, **options):
    """Deserialize simple Python objects back into Model instances.

    It's expected that you pass the Python objects themselves (instead of a
    stream or a string) to the constructor
    """
    models.get_apps()
    for d in object_list:
        # Look up the model and starting build a dict of data for it.
        Model = _get_model(d["model"])
        data = {}
        key = resolve_key(Model._meta.module_name, d["pk"])
        if key.name():
            data["key_name"] = key.name()
        parent = None
        if key.parent():
            parent = FakeParent(key.parent())
        m2m_data = {}

        # Handle each field
        for (field_name, field_value) in d["fields"].iteritems():
            if isinstance(field_value, str):
                field_value = smart_unicode(
                        field_value, options.get("encoding",
                            settings.DEFAULT_CHARSET),
                        strings_only=True)
            field = Model.properties()[field_name]

            if isinstance(field, db.ReferenceProperty):
                # Resolve foreign key references.
                data[field.name] = resolve_key(Model._meta.module_name, field_value)
                if not data[field.name].name():
                    raise base.DeserializationError(u"Cannot load Reference with "
                                                                                    "unnamed key: '%s'" % field_value)
            elif isinstance(field, db.DateTimeProperty):
                data[field.name] = parse_datetime(field_value)
            else:
                data[field.name] = field.validate(field_value)
        # Create the new model instance with all it's data, but no parent.
        object = Model(**data)
        # Now add the parent into the hidden attribute, bypassing the type checks
        # in the Model's __init__ routine.
        object._parent = parent
        # When the deserialized object is saved our replacement DeserializedObject
        # class will set object._parent to force the real parent model to be loaded
        # the first time it is referenced.
        yield base.DeserializedObject(object, m2m_data)

def _get_model(model_identifier):
    """
    Helper to look up a model from an "app_label.module_name" string.
    """
    try:
        Model = models.get_model(*model_identifier.split("."))
    except TypeError:
        Model = None
    if Model is None:
        raise base.DeserializationError(u"Invalid model identifier: '%s'" % model_identifier)
    return Model

def resolve_key(model, key_data):
    """Creates a Key instance from a some data.

    Args:
        model: The name of the model this key is being resolved for. Only used in
            the fourth case below (a plain key_name string).
        key_data: The data to create a key instance from. May be in four formats:
            * The str() output of a key instance. Eg. A base64 encoded string.
            * The repr() output of a key instance. Eg. A string for eval().
            * A list of arguments to pass to db.Key.from_path.
            * A single string value, being the key_name of the instance. When this
                format is used the resulting key has no parent, and is for the model
                named in the model parameter.

    Returns:
        An instance of db.Key. If the data cannot be used to create a Key instance
        an error will be raised.
    """
    if isinstance(key_data, list):
        # The key_data is a from_path sequence.
        return db.Key.from_path(*key_data)
    elif isinstance(key_data, basestring):
        if key_data.find("from_path") != -1:
            # key_data is encoded in repr(key) format
            return eval(key_data)
        else:
            try:
                # key_data encoded a str(key) format
                return db.Key(key_data)
            except datastore_types.datastore_errors.BadKeyError, e:
                # Final try, assume it's a plain key name for the model.
                return db.Key.from_path(model, key_data)
    else:
        raise base.DeserializationError(u"Invalid key data: '%s'" % key_data)
