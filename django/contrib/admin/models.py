from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.contrib.admin.util import quote
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import smart_unicode
from django.utils.safestring import mark_safe
from google.appengine.ext import db
from ragendja.dbutils import FakeModelProperty

ADDITION = 1
CHANGE = 2
DELETION = 3

class LogEntryManager(models.Manager):
    def log_action(self, user_id, content_type_id, object_id, object_repr, action_flag, change_message=''):
        e = LogEntry(user=db.Key(user_id), content_type=content_type_id, object_id=smart_unicode(object_id), object_repr=object_repr[:200], action_flag=action_flag, change_message=change_message)
        e.save()

class LogEntry(db.Model):
    action_time = db.DateTimeProperty(required=True,
        verbose_name=_('action time'), auto_now=True)
    user = db.ReferenceProperty(User, required=True)
    content_type = FakeModelProperty(ContentType)
    object_id = db.StringProperty(verbose_name=_('object id'))
    object_repr = db.TextProperty(required=True,
        verbose_name=_('object repr'))
    action_flag = db.IntegerProperty(required=True,
        verbose_name=_('action flag'))
    change_message = db.TextProperty(verbose_name=_('change message'))
    objects = LogEntryManager()
    class Meta:
        verbose_name = _('log entry')
        verbose_name_plural = _('log entries')
        db_table = 'django_admin_log'
        ordering = ('-action_time',)

    def __repr__(self):
        return smart_unicode(self.action_time)

    def is_addition(self):
        return self.action_flag == ADDITION

    def is_change(self):
        return self.action_flag == CHANGE

    def is_deletion(self):
        return self.action_flag == DELETION

    def get_edited_object(self):
        "Returns the edited object represented by this log entry"
        return self.content_type.get_object_for_this_type(pk=self.object_id)

    def get_admin_url(self):
        """
        Returns the admin URL to edit the object represented by this log entry.
        This is relative to the Django admin index page.
        """
        return mark_safe(u"%s/%s/%s/" % (self.content_type.app_label, self.content_type.model, quote(self.object_id)))
