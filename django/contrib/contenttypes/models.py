from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import smart_unicode
from google.appengine.ext import db
from ragendja.dbutils import get_object, FakeModel

class ContentTypeManager(models.Manager):

    # Cache to avoid re-looking up ContentType objects all over the place.
    # This cache is shared by all the get_for_* methods.
    _cache = {}

    def get_for_model(self, model):
        """
        Returns the ContentType object for a given model, creating the
        ContentType if necessary. Lookups are cached so that subsequent lookups
        for the same model don't hit the database.
        """
        opts = model._meta
        while opts.proxy:
            model = opts.proxy_for_model
            opts = model._meta
        return ContentType(app_label=opts.app_label,
                           model=opts.object_name.lower(),
                           name=opts.verbose_name)

    def get_for_id(self, id):
        """
        Lookup a ContentType by ID. Uses the same shared cache as get_for_model
        (though ContentTypes are obviously not created on-the-fly by get_by_id).
        """
        from django.db import models
        if '.' in id:
            id = id.split('.', 1)
        else:
            id = id.split('_', 1)
        opts = models.get_model(*id)._meta
        return ContentType(app_label=opts.app_label,
                           model=opts.object_name.lower(),
                           name=opts.verbose_name)

    def clear_cache(self):
        """
        Clear out the content-type cache. This needs to happen during database
        flushes to prevent caching of "stale" content type IDs (see
        django.contrib.contenttypes.management.update_contenttypes for where
        this gets called).
        """
        self.__class__._cache.clear()

    def _add_to_cache(self, ct):
        """Insert a ContentType into the cache."""
        model = ct.model_class()
        key = (model._meta.app_label, model._meta.object_name.lower())
        self.__class__._cache[key] = ct
        self.__class__._cache[ct.id] = ct

class ContentType(FakeModel):
    fields = ('app_label', 'model')
    objects = ContentTypeManager()

    def __init__(self, app_label=None, model=None, name=None):
        self.app_label, self.model, self.name = app_label, model.lower(), name

    @classmethod
    def all(cls):
        from django.db.models.loading import get_models
        return [cls.objects.get_for_model(model) for model in get_models()]

    def get_value_for_datastore(self):
        return '%s.%s' % (self.app_label, self.model)

    @classmethod
    def make_value_from_datastore(cls, value):
        return cls.objects.get_for_id(value)

    def __unicode__(self):
        return unicode(self.name)

    def model_class(self):
        "Returns the Python model class for this type of content."
        from django.db import models
        return models.get_model(self.app_label, self.model)

    def get_object_for_this_type(self, *filters_or_key, **kwargs):
        """
        Returns an object of this type for the keyword arguments given.
        The parameters have the same format as ragendja's get_object_or_404().
        """
        if 'pk' in kwargs:
            filters_or_key = (kwargs['pk'],)
            del kwargs['pk']
        return get_object(self.model_class(), *filters_or_key, **kwargs)
