"""
XML serializer.
"""

from django.conf import settings
from django.core.serializers import base
from django.db import models
from django.utils.xmlutils import SimplerXMLGenerator
from django.utils.encoding import smart_unicode
from xml.dom import pulldom

from google.appengine.api import datastore_types
from google.appengine.ext import db

from python import FakeParent, parse_datetime

class Serializer(base.Serializer):
    """
    Serializes a QuerySet to XML.
    """

    def __init__(self, *args, **kwargs):
        super(Serializer, self).__init__(*args, **kwargs)
        self._objects = []

    def getvalue(self):
        """Wrap the serialized objects with XML headers and return."""
        str = u"""<?xml version="1.0" encoding="utf-8"?>\n"""
        str += u"""<django-objects version="1.0">\n"""
        str += u"".join(self._objects)
        str += u"""</django-objects>"""
        return str

    def indent(self, level):
        if self.options.get('indent', None) is not None:
            self.xml.ignorableWhitespace('\n' + ' ' * self.options.get('indent', None) * level)

    def start_serialization(self):
        """
        Start serialization -- open the XML document and the root element.
        """
        self.xml = SimplerXMLGenerator(self.stream, self.options.get("encoding", settings.DEFAULT_CHARSET))
        self.xml.startDocument()
        self.xml.startElement("django-objects", {"version" : "1.0"})

    def end_serialization(self):
        """
        End serialization -- end the document.
        """
        self.indent(0)
        self.xml.endElement("django-objects")
        self.xml.endDocument()

    def start_object(self, obj):
        """Nothing needs to be done to start an object."""
        pass

    def end_object(self, obj):
        """Serialize the object to XML and add to the list of objects to output.

        The output of ToXml is manipulated to replace the datastore model name in
        the "kind" tag with the Django model name (which includes the Django
        application name) to make importing easier.
        """
        xml = obj._entity.ToXml()
        xml = xml.replace(u"""kind="%s" """ % obj._entity.kind(),
                                            u"""kind="%s" """ % unicode(obj._meta))
        self._objects.append(xml)

    def handle_field(self, obj, field):
        """Fields are not handled individually."""
        pass

    def handle_fk_field(self, obj, field):
        """Fields are not handled individually."""
        pass

    def handle_m2m_field(self, obj, field):
        """
        Called to handle a ManyToManyField. Related objects are only
        serialized as references to the object's PK (i.e. the related *data*
        is not dumped, just the relation).
        """
        if field.creates_table:
            self._start_relational_field(field)
            for relobj in getattr(obj, field.name).iterator():
                self.xml.addQuickElement("object", attrs={"pk" : smart_unicode(relobj._get_pk_val())})
            self.xml.endElement("field")

    def _start_relational_field(self, field):
        """
        Helper to output the <field> element for relational fields
        """
        self.indent(2)
        self.xml.startElement("field", {
            "name" : field.name,
            "rel"  : field.rel.__class__.__name__,
            "to"   : smart_unicode(field.rel.to._meta),
        })

class Deserializer(base.Deserializer):
    """
    Deserialize XML.
    """

    def __init__(self, stream_or_string, **options):
        super(Deserializer, self).__init__(stream_or_string, **options)
        self.event_stream = pulldom.parse(self.stream)

    def next(self):
        """Replacement next method to look for 'entity'.

        The default next implementation exepects 'object' nodes which is not
        what the entity's ToXml output provides.
        """
        for event, node in self.event_stream:
            if event == "START_ELEMENT" and node.nodeName == "entity":
                self.event_stream.expandNode(node)
                return self._handle_object(node)
        raise StopIteration

    def _handle_object(self, node):
        """Convert an <entity> node to a DeserializedObject"""
        Model = self._get_model_from_node(node, "kind")
        data = {}
        key = db.Key(node.getAttribute("key"))
        if key.name():
            data["key_name"] = key.name()
        parent = None
        if key.parent():
            parent = FakeParent(key.parent())
        m2m_data = {}

        # Deseralize each field.
        for field_node in node.getElementsByTagName("property"):
            # If the field is missing the name attribute, bail (are you
            # sensing a pattern here?)
            field_name = field_node.getAttribute("name")
            if not field_name:
                    raise base.DeserializationError("<field> node is missing the 'name' "
                                                                                    "attribute")
            field = Model.properties()[field_name]
            field_value = getInnerText(field_node).strip()
            field_type = field_node.getAttribute('type')
            if not field_value:
                field_value = None
            if field_type == 'int':
                field_value = int(field_value)
            elif field_type == 'gd:when':
                field_value = parse_datetime(field_value)

            if isinstance(field, db.ReferenceProperty):
                m = re.match("tag:.*\[(.*)\]", field_value)
                if not m:
                    raise base.DeserializationError(u"Invalid reference value: '%s'" %
                                                                                    field_value)
                key = m.group(1)
                key_obj = db.Key(key)
                if not key_obj.name():
                    raise base.DeserializationError(u"Cannot load Reference with "
                                                                                    "unnamed key: '%s'" % field_value)
                data[field.name] = key_obj
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
        return base.DeserializedObject(object, m2m_data)

    def _handle_fk_field_node(self, node, field):
        """
        Handle a <field> node for a ForeignKey
        """
        # Check if there is a child node named 'None', returning None if so.
        if node.getElementsByTagName('None'):
            return None
        else:
            return field.rel.to._meta.get_field(field.rel.field_name).to_python(
                       getInnerText(node).strip())

    def _handle_m2m_field_node(self, node, field):
        """
        Handle a <field> node for a ManyToManyField.
        """
        return [field.rel.to._meta.pk.to_python(
                    c.getAttribute("pk"))
                    for c in node.getElementsByTagName("object")]

    def _get_model_from_node(self, node, attr):
        """
        Helper to look up a model from a <object model=...> or a <field
        rel=... to=...> node.
        """
        model_identifier = node.getAttribute(attr)
        if not model_identifier:
            raise base.DeserializationError(
                "<%s> node is missing the required '%s' attribute" \
                    % (node.nodeName, attr))
        try:
            Model = models.get_model(*model_identifier.split("."))
        except TypeError:
            Model = None
        if Model is None:
            raise base.DeserializationError(
                "<%s> node has invalid model identifier: '%s'" % \
                    (node.nodeName, model_identifier))
        return Model


def getInnerText(node):
    """
    Get all the inner text of a DOM node (recursively).
    """
    # inspired by http://mail.python.org/pipermail/xml-sig/2005-March/011022.html
    inner_text = []
    for child in node.childNodes:
        if child.nodeType == child.TEXT_NODE or child.nodeType == child.CDATA_SECTION_NODE:
            inner_text.append(child.data)
        elif child.nodeType == child.ELEMENT_NODE:
            inner_text.extend(getInnerText(child))
        else:
           pass
    return u"".join(inner_text)
