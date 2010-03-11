from django.contrib.redirects.models import Redirect
from django import http
from django.conf import settings
from google.appengine.ext import db

class RedirectFallbackMiddleware(object):
    def process_response(self, request, response):
        if response.status_code != 404:
            return response # No need to check for a redirect for non-404 responses.
        path = request.get_full_path()
        r = Redirect.all().filter('site =', db.Key(settings.SITE_ID)).filter(
            'old_path =', path).get()
        if r is None and settings.APPEND_SLASH:
            # Try removing the trailing slash.
            r = Redirect.all().filter('site =', db.Key(settings.SITE_ID)).filter(
                'old_path =', path[:path.rfind('/')]+path[path.rfind('/')+1:]
                ).get()
        if r is not None:
            if r.new_path == '':
                return http.HttpResponseGone()
            return http.HttpResponsePermanentRedirect(r.new_path)

        # No redirect was found. Return the response.
        return response
