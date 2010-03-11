from google.appengine.ext import db
from django.contrib.sites.models import Site
from django.utils.translation import ugettext_lazy as _
from ragendja.dbutils import KeyListProperty

class FlatPage(db.Model):
    url = db.StringProperty(required=True, verbose_name=_('URL'))
    title = db.StringProperty(required=True, verbose_name=_('title'))
    content = db.TextProperty(verbose_name=_('content'), default='')
    enable_comments = db.BooleanProperty(default=False,
        verbose_name=_('enable comments'))
    template_name = db.StringProperty(verbose_name=_('template name'))
    registration_required = db.BooleanProperty(default=False,
        verbose_name=_('registration required'))
    sites = KeyListProperty(Site)

    class Meta:
        verbose_name = _('flat page')
        verbose_name_plural = _('flat pages')
        db_table = 'django_flatpage'

    def __unicode__(self):
        return u"%s -- %s" % (self.url, self.title)

    def get_absolute_url(self):
        return self.url
