from django.core.management.base import NoArgsCommand
from django.core.management.color import no_style
from django.utils.importlib import import_module
from optparse import make_option
import sys

try:
    set
except NameError:
    from sets import Set as set   # Python 2.3 fallback

class Command(NoArgsCommand):
    option_list = NoArgsCommand.option_list + (
        make_option('--noinput', action='store_false', dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.'),
    )
    help = "Create the database tables for all apps in INSTALLED_APPS whose tables haven't already been created."

    def handle_noargs(self, **options):
        import logging
        from django.db import connection, transaction, models
        from django.conf import settings
        from django.core.management.sql import custom_sql_for_model, emit_post_sync_signal

        verbosity = int(options.get('verbosity', 1))
        interactive = options.get('interactive')
        show_traceback = options.get('traceback', False)

        self.style = no_style()

        # Import the 'management' module within each installed app, to register
        # dispatcher events.
        for app_name in settings.INSTALLED_APPS:
            try:
                import_module('.management', app_name)
            except ImportError, exc:
                # This is slightly hackish. We want to ignore ImportErrors
                # if the "management" module itself is missing -- but we don't
                # want to ignore the exception if the management module exists
                # but raises an ImportError for some reason. The only way we
                # can do this is to check the text of the exception. Note that
                # we're a bit broad in how we check the text, because different
                # Python implementations may not use the same text.
                # CPython uses the text "No module named management"
                # PyPy uses "No module named myproject.myapp.management"
                msg = exc.args[0]
                if not msg.startswith('No module named') or 'management' not in msg:
                    raise

        # Get a list of already installed *models* so that references work right.
        tables = []
        seen_models = set()
        created_models = set()
        pending_references = {}

        for app in models.get_apps():
            app_name = app.__name__.split('.')[-2]
            model_list = models.get_models(app)
            for model in model_list:
                # Create the model's database table, if it doesn't already exist.
                if verbosity >= 2:
                    print "Processing %s.%s model" % (app_name, model._meta.object_name)
                if not model.all().count(1):
                    seen_models.add(model)
                    created_models.add(model)

        # Send the post_syncdb signal, so individual apps can do whatever they need
        # to do at this point.
        emit_post_sync_signal(created_models, verbosity, interactive)

        # Install the 'initial_data' fixture, using format discovery
        from django.core.management import call_command
        call_command('loaddata', 'initial_data', verbosity=verbosity)
