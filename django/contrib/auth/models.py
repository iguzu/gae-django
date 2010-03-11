from django.conf import settings
import datetime
import urllib

from django.contrib import auth
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.manager import EmptyManager
from django.contrib.contenttypes.models import ContentType
from django.utils.encoding import smart_str
from django.utils.hashcompat import md5_constructor, sha_constructor
from django.utils.translation import ugettext_lazy as _
from google.appengine.ext import db
from ragendja.dbutils import FakeModelListProperty, KeyListProperty
from string import ascii_letters, digits
import hashlib, random

UNUSABLE_PASSWORD = '!' # This will never be a valid hash

try:
    set
except NameError:
    from sets import Set as set   # Python 2.3 fallback

def get_hexdigest(algorithm, salt, raw_password):
    """
    Returns a string of the hexdigest of the given plaintext password and salt
    using the given algorithm ('md5', 'sha1' or 'crypt').
    """
    raw_password, salt = smart_str(raw_password), smart_str(salt)
    if algorithm == 'crypt':
        try:
            import crypt
        except ImportError:
            raise ValueError('"crypt" password algorithm not supported in this environment')
        return crypt.crypt(raw_password, salt)

    if algorithm == 'md5':
        return md5_constructor(salt + raw_password).hexdigest()
    elif algorithm == 'sha1':
        return sha_constructor(salt + raw_password).hexdigest()
    raise ValueError("Got unknown password algorithm type in password.")

def gen_hash(password, salt=None, algorithm='sha512'):
    hash = hashlib.new(algorithm)
    hash.update(smart_str(password))
    if salt is None:
        salt = ''.join([random.choice(ascii_letters + digits) for _ in range(8)])
    hash.update(salt)
    return (algorithm, salt, hash.hexdigest())

def check_password(raw_password, enc_password):
    """
    Returns a boolean of whether the raw_password was correct. Handles
    encryption formats behind the scenes.
    """
    try:
        algo, salt, hsh = enc_password.split('$')
    except:
        raise ValueError("You've mistakenly set the password directly. Please use set_password() instead.")
    if algo == 'sha512':
        return hsh == gen_hash(raw_password, salt, algo)[-1]
    return hsh == get_hexdigest(algo, salt, raw_password)

class SiteProfileNotAvailable(Exception):
    pass

class Permission(object):
    """The permissions system provides a way to assign permissions to specific users and groups of users.

    The permission system is used by the Django admin site, but may also be useful in your own code. The Django admin site uses permissions as follows:

        - The "add" permission limits the user's ability to view the "add" form and add an object.
        - The "change" permission limits a user's ability to view the change list, view the "change" form and change an object.
        - The "delete" permission limits the ability to delete an object.

    Permissions are set globally per type of object, not per specific object instance. It is possible to say "Mary may change news stories," but it's not currently possible to say "Mary may change news stories, but only the ones she created herself" or "Mary may only change news stories that have a certain status or publication date."

    Three basic permissions -- add, change and delete -- are automatically created for each Django model.
    """
    def __init__(self, name=None, content_type=None, codename=None):
        self.name, self.content_type = name, content_type
        self.codename = codename

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, unicode(self))

    def __unicode__(self):
        return u"%s | %s | %s" % (
            unicode(self.content_type.app_label),
            unicode(self.content_type),
            unicode(self.name))

    @classmethod
    def all(cls):
        return cls.get_permissions()

    def get_value_for_datastore(self):
        return '%s.%s' % (self.content_type.app_label, self.codename)

    @classmethod
    def make_value_from_datastore(cls, value):
        app_label, codename = value.split('.', 1)
        perms = [perm for perm in cls.get_permissions(app_label)
                 if perm.codename == codename]
        if perms:
            return perms[0]
        return Permission(codename=codename,
            content_type=ContentType(app_label=app_label, model='Unknown',
                                     name='Unknown'),
            name=codename + ' (Unknown)')

    @classmethod
    def get_permissions(cls, app_label=None, model_name=None):
        permissions = []
        from django.db.models.loading import get_models
        for model in get_models():
            for permission in model._meta.permissions:
                if app_label and app_label != model._meta.app_label or \
                        model_name and model_name != model._meta.object_name:
                    continue
                content_type = ContentType.objects.get_for_model(model)
                permissions.append(
                    Permission(codename=permission[0], name=permission[1],
                               content_type=content_type))
        return permissions

class Group(db.Model):
    """Groups are a generic way of categorizing users to apply permissions, or some other label, to those users. A user can belong to any number of groups.

    A user in a group automatically has all the permissions granted to that group. For example, if the group Site editors has the permission can_edit_home_page, any user in that group will have that permission.

    Beyond permissions, groups are a convenient way to categorize users to apply some label, or extended functionality, to them. For example, you could create a group 'Special users', and you could write code that would do special things to those users -- such as giving them access to a members-only portion of your site, or sending them members-only e-mail messages.
    """
    name = db.StringProperty(required=True, verbose_name=_('name'))
    permissions = FakeModelListProperty(Permission,
        verbose_name=_('permissions'))

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')

    def __repr__(self):
        return '<%s: %s>' % (self.__class__.__name__, unicode(self))

    def __unicode__(self):
        return self.name

class AnonymousUser(object):
    id = None
    username = ''
    is_staff = False
    is_active = False
    is_superuser = False
    _groups = EmptyManager()
    _user_permissions = EmptyManager()

    def __init__(self):
        pass

    def __unicode__(self):
        return 'AnonymousUser'

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return 1 # instances always return the same hash value

    def save(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    def set_password(self, raw_password):
        raise NotImplementedError

    def check_password(self, raw_password):
        raise NotImplementedError

    def _get_groups(self):
        return self._groups
    groups = property(_get_groups)

    def _get_user_permissions(self):
        return self._user_permissions
    user_permissions = property(_get_user_permissions)

    def has_perm(self, perm):
        return False

    def has_perms(self, perm_list):
        return False

    def has_module_perms(self, module):
        return False

    def get_and_delete_messages(self):
        return []

    def is_anonymous(self):
        return True

    def is_authenticated(self):
        return False

class UserManager(models.Manager):
    def create_user(self, username, email, password=None):
        "Creates and saves a User with the given username, e-mail and password."
        now = datetime.datetime.now()
        # Check if username is already taken
        count = User.all().filter('username =', username).count(1)
        if count:
            from django.db import IntegrityError
            raise IntegrityError('username already taken')
        user = User(username=username, email=email.strip().lower())
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        # Check for race condition (two users register at the same time)
        count = User.all().filter('username =', username).count(2)
        if count == 2:
            user.delete()
            from django.db import IntegrityError
            raise IntegrityError('username already taken')
        return user

    def create_superuser(self, username, email, password):
        u = self.create_user(username, email, password)
        u.is_staff = True
        u.is_active = True
        u.is_superuser = True
        u.save()
        return u

    def make_random_password(self, length=10, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
        "Generates a random password with the given length and given allowed_chars"
        # Note that default value of allowed_chars does not have "I" or letters
        # that look like it -- just to avoid confusion.
        from random import choice
        return ''.join([choice(allowed_chars) for i in range(length)])

class UserTraits(db.Model):
    last_login = db.DateTimeProperty(verbose_name=_('last login'))
    date_joined = db.DateTimeProperty(auto_now_add=True,
        verbose_name=_('date joined'))
    is_active = db.BooleanProperty(default=True, verbose_name=_('active'))
    is_staff = db.BooleanProperty(default=False,
        verbose_name=_('staff status'))
    is_superuser = db.BooleanProperty(default=False,
        verbose_name=_('superuser status'))
    password = db.StringProperty(default=UNUSABLE_PASSWORD,
        verbose_name=_('password'))
    groups = KeyListProperty(Group, verbose_name=_('groups'))
    user_permissions = FakeModelListProperty(Permission,
        verbose_name=_('user permissions'))

    objects = UserManager()

    class Meta:
        abstract = True

    def is_anonymous(self):
        "Always returns False. This is a way of comparing User objects to anonymous users."
        return False

    def is_authenticated(self):
        """Always return True. This is a way to tell if the user has been authenticated in templates.
        """
        return True

    def get_full_name(self):
        "Returns the first_name plus the last_name, with a space in between."
        full_name = u'%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def set_password(self, raw_password):
        import random
        algo = 'sha1'
        salt = get_hexdigest(algo, str(random.random()), str(random.random()))[:5]
        hsh = get_hexdigest(algo, salt, raw_password)
        self.password = '%s$%s$%s' % (algo, salt, hsh)

    def check_password(self, raw_password):
        """
        Returns a boolean of whether the raw_password was correct. Handles
        encryption formats behind the scenes.
        """
        # Backwards-compatibility check. Older passwords won't include the
        # algorithm or salt.
        if '$' not in self.password:
            is_correct = (self.password == get_hexdigest('md5', '', raw_password))
            if is_correct:
                # Convert the password to the new, more secure format.
                self.set_password(raw_password)
                self.save()
            return is_correct
        # Backwards-compatibility check for old app-engine-patch hash format
        if self.password.split('$')[0] == 'sha512':
            valid = check_password(raw_password, self.password)
            if valid:
                self.set_password(raw_password)
                self.save()
            return valid
        return check_password(raw_password, self.password)

    def set_unusable_password(self):
        # Sets a value that will never be a valid hash
        self.password = UNUSABLE_PASSWORD

    def has_usable_password(self):
        return self.password != UNUSABLE_PASSWORD

    def get_group_permissions(self):
        """
        Returns a list of permission strings that this user has through
        his/her groups. This method queries all available auth backends.
        """
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_group_permissions"):
                permissions.update(backend.get_group_permissions(self))
        return permissions

    def get_all_permissions(self):
        permissions = set()
        for backend in auth.get_backends():
            if hasattr(backend, "get_all_permissions"):
                permissions.update(backend.get_all_permissions(self))
        return permissions

    def has_perm(self, perm):
        """
        Returns True if the user has the specified permission. This method
        queries all available auth backends, but returns immediately if any
        backend returns True. Thus, a user who has permission from a single
        auth backend is assumed to have permission in general.
        """
        # Inactive users have no permissions.
        if not self.is_active:
            return False

        # Superusers have all permissions.
        if self.is_superuser:
            return True

        # Otherwise we need to check the backends.
        for backend in auth.get_backends():
            if hasattr(backend, "has_perm"):
                if backend.has_perm(self, perm):
                    return True
        return False

    def has_perms(self, perm_list):
        """Returns True if the user has each of the specified permissions."""
        for perm in perm_list:
            if not self.has_perm(perm):
                return False
        return True

    def has_module_perms(self, app_label):
        """
        Returns True if the user has any permissions in the given app
        label. Uses pretty much the same logic as has_perm, above.
        """
        if not self.is_active:
            return False

        if self.is_superuser:
            return True

        for backend in auth.get_backends():
            if hasattr(backend, "has_module_perms"):
                if backend.has_module_perms(self, app_label):
                    return True
        return False

    def get_and_delete_messages(self):
        messages = []
        for m in self.message_set:
            messages.append(m.message)
            m.delete()
        return messages

    def get_profile(self):
        """
        Returns site-specific profile for this user. Raises
        SiteProfileNotAvailable if this site does not allow profiles.
        """
        if not hasattr(self, '_profile_cache'):
            from django.conf import settings
            if not getattr(settings, 'AUTH_PROFILE_MODULE', False):
                raise SiteProfileNotAvailable
            try:
                app_label, model_name = settings.AUTH_PROFILE_MODULE.split('.')
                model = models.get_model(app_label, model_name)
                profile = model.all().filter('user =', self).get()
                if profile:
                    self._profile_cache = profile
                    profile.user = self
                return profile
            except (ImportError, ImproperlyConfigured):
                raise SiteProfileNotAvailable
        return self._profile_cache

class EmailUserTraits(UserTraits):
    def email_user(self, subject, message, from_email=None):
        """Sends an e-mail to this user."""
        from django.core.mail import send_mail
        send_mail(subject, message, from_email, [self.email])

    class Meta:
        abstract = True

    def __unicode__(self):
        return unicode(self.email)

class EmailUser(EmailUserTraits):
    email = db.EmailProperty(required=True, verbose_name=_('e-mail address'))
    # This can be used to distinguish between banned users and unfinished
    # registrations
    is_banned = db.BooleanProperty(default=False,
        verbose_name=_('banned status'))

    class Meta:
        abstract = True

class User(EmailUserTraits):
    """Default User class that mimics Django's User class."""
    username = db.StringProperty(required=True, verbose_name=_('username'))
    email = db.EmailProperty(verbose_name=_('e-mail address'))
    first_name = db.StringProperty(verbose_name=_('first name'))
    last_name = db.StringProperty(verbose_name=_('last name'))

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __unicode__(self):
        return self.get_full_name()

DjangoCompatibleUser = User

AUTH_USER_MODULE = getattr(settings, 'AUTH_USER_MODULE', None)
if AUTH_USER_MODULE and AUTH_USER_MODULE != 'ragendja.auth.models':
    from django.db.models.loading import cache
    module = __import__(AUTH_USER_MODULE, {}, {}, [''])
    User = cache.app_models['auth']['user'] = module.User
    try:
        AnonymousUser = module.AnonymousUser
    except:
        pass

class Message(db.Model):
    """
    The message system is a lightweight way to queue messages for given
    users. A message is associated with a User instance (so it is only
    applicable for registered users). There's no concept of expiration or
    timestamps. Messages are created by the Django admin after successful
    actions. For example, "The poll Foo was created successfully." is a
    message.
    """
    user = db.ReferenceProperty(User, required=True)
    message = db.TextProperty(required=True, verbose_name=_('message'))

    def __unicode__(self):
        return self.message
