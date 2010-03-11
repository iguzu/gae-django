"""
>>> from django.contrib.sites.models import Site
>>> from django.conf import settings
>>> old_SITE_ID = getattr(settings, 'SITE_ID', None)
>>> site = Site(domain="example.com", name="example.com")
>>> site.save()
>>> settings.__class__.SITE_ID = site.pk

# Make sure that get_current() does not return a deleted Site object.
>>> s = Site.objects.get_current()
>>> isinstance(s, Site)
True

>>> s.delete()
>>> Site.objects.get_current()

# After updating a Site object (e.g. via the admin), we shouldn't return a
# bogus value from the SITE_CACHE.
>>> site = Site(domain="example.com", name="example.com")
>>> site.save()
>>> settings.__class__.SITE_ID = site.pk
>>> site = Site.objects.get_current()
>>> site.name
u"example.com"
>>> s2 = Site.get(settings.SITE_ID)
>>> s2.name = "Example site"
>>> s2.save()
>>> site = Site.objects.get_current()
>>> site.name
u"Example site"
>>> settings.SITE_ID = old_SITE_ID
"""
