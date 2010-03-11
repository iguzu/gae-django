from django import http
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from google.appengine.ext import db

def shortcut(request, content_type_id, object_id):
    "Redirect to an object's page based on a content-type ID and an object ID."
    # Look up the object, making sure it's got a get_absolute_url() function.
    content_type = ContentType.objects.get_for_id(content_type_id)
    obj = content_type and content_type.get_object_for_this_type(pk=object_id)
    if not content_type or not obj:
        raise http.Http404("Content type %s object %s doesn't exist" % (content_type_id, object_id))
    try:
        absurl = obj.get_absolute_url()
    except AttributeError:
        raise http.Http404("%s objects don't have get_absolute_url() methods" % content_type.name)

    # Try to figure out the object's domain, so we can do a cross-site redirect
    # if necessary.

    # If the object actually defines a domain, we're done.
    if absurl.startswith('http://') or absurl.startswith('https://'):
        return http.HttpResponseRedirect(absurl)

    # Otherwise, we need to introspect the object's relationships for a
    # relation to the Site object
    object_domain = None
    opts = obj._meta

    # First, look for an many-to-many relationship to Site.
    for field in opts.many_to_many:
        if field.rel.to is Site:
            try:
                # Caveat: In the case of multiple related Sites, this just
                # selects the *first* one, which is arbitrary.
                tmpsite = Site.get(getattr(obj, field.name)[0])
                if tmpsite:
                    object_domain = tmpsite.domain
            except IndexError:
                pass
            if object_domain is not None:
                break

    # Next, look for a many-to-one relationship to Site.
    if object_domain is None:
        for field in obj._meta.fields:
            if field.rel and field.rel.to is Site and \
                    not isinstance(field, db.ListProperty):
                tmpsite = getattr(obj, field.name)
                if tmpsite:
                    object_domain = tmpsite.domain
                if object_domain is not None:
                    break

    # Fall back to the current site (if possible).
    if object_domain is None:
        tmpsite = Site.objects.get_current()
        if tmpsite:
            object_domain = tmpsite.domain

    # If all that malarkey found an object domain, use it. Otherwise, fall back
    # to whatever get_absolute_url() returned.
    if object_domain is not None:
        protocol = request.is_secure() and 'https' or 'http'
        return http.HttpResponseRedirect('%s://%s%s' % (protocol, object_domain, absurl))
    else:
        return http.HttpResponseRedirect(absurl)
