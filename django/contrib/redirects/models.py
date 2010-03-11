from django.contrib.sites.models import Site
from django.utils.translation import ugettext_lazy as _
from google.appengine.ext import db

class Redirect(db.Model):
    site = db.ReferenceProperty(Site)
    old_path = db.StringProperty(required=True,
        verbose_name=_('redirect from'))
    # TODO: how can we add a help text???
    #    help_text=_("This should be an absolute path, excluding the domain name. Example: '/events/search/'."))
    new_path = db.StringProperty(required=True, verbose_name=_('redirect to'))
    # TODO: how can we add a help text???
    #    help_text=_("This can be either an absolute path (as above) or a full URL starting with 'http://'."))

    class Meta:
        verbose_name = _('redirect')
        verbose_name_plural = _('redirects')
        db_table = 'django_redirect'

    def __unicode__(self):
        return "%s ---> %s" % (self.old_path, self.new_path)
