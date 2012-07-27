from __future__ import with_statement
import os

from django.core import management
# We have to re-name this to avoid clashes with fabric.api.settings.
import ohbooklist.conf.local.settings as django_settings
management.setup_environ(django_settings)

from fabric.api import *

"""
Here are some deployment related settings. These can be pulled from your
settings.py if you'd prefer. We keep strictly deployment-related stuff in
our fabfile.py, but you don't have to.
"""
# The path on your servers to your codebase's root directory. This needs to
# be the same for all of your servers. Worse case, symlink away.
env.GIT_REPO_URL = 'git@github.com:fengli/ohbooklist.com.git'
env.REMOTE_CODEBASE_PATH = '/home/okidogi/projects/ohbooklist.com'
# Path relative to REMOTE_CODEBASE_PATH.
env.PIP_REQUIREMENTS_PATH = '%s/requirements.pip' % env.REMOTE_CODEBASE_PATH
# The standardized virtualenv name to use.
env.REMOTE_VIRTUALENV_NAME = 'ohbooklist'
env.user = 'okidogi'

# This is used for reloading gunicorn processes after code updates.
# Only needed for gunicorn-related tasks.
env.GUNICORN_PID_PATH = os.path.join(env.REMOTE_CODEBASE_PATH, 'gunicorn.pid')

def local ():
    env.hosts = ['localhost']
    env.servername = 'local'

def staging():
    """
    Sets env.hosts to the sole staging server. No roledefs means that all
    deployment tasks get ran on every member of env.hosts.
    """
    env.hosts = ['ohbooklist.com']
    env.REMOTE_CODEBASE_PATH = '/home/okidogi/staging/ohbooklist.com'
    env.servername = 'staging'

def production():
    """
    Set env.roledefs according to our deployment setup. From this, an
    env.hosts list is generated, which determines which hosts can be
    messed with. The roledefs are only used to determine what each server is.
    """
    # Nginx proxies.
    env.roledefs['proxy_servers'] = ['ohbooklist.com']
    # The Django + gunicorn app servers.
    env.roledefs['webapp_servers'] = ['ohbooklist.com']
    # Static media servers
    env.roledefs['media_servers'] = ['static.ohbooklist.com']
    # Postgres servers.
    env.roledefs['db_servers'] = ['db.ohbooklist.com']

    # Combine all of the roles into the env.hosts list.
    env.hosts = [host[0] for host in env.roledefs.values()]
    env.servername = 'production'

# ======================================================================
# Setup setting
# ======================================================================
def setup_repo ():
    """
    git clone from repo in github. Need to add public key to github server.
    """
    print('=== CLONE FROM GITHUB ===')
    with cd(os.path.dirname(env.REMOTE_CODEBASE_PATH)):
        run("git clone %s %s" % (env.GIT_REPO_URL, os.path.basename(env.REMOTE_CODEBASE_PATH)))
    with cd(os.path.join(env.REMOTE_CODEBASE_PATH, "ohbooklist/conf/local")):
        run("ln -s ../production/settings.py")
        run("ln -s ../production/urls.py")
    with cd(env.REMOTE_CODEBASE_PATH):
        run("python ohbooklist/bin/manage.py syncdb")

def git_pull ():
    """
    git pull the latest version.
    """
    print('=== PULL LATEST SOURCE ===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run("git pull")
def migrate_database ():
    """
    Migrate database in remote server.
    """
    print ('===Migrate database===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run("workon ohbooklist && python ohbooklist/bin/manage.py migrate")

def setup_firewall ():
    """
    Right now deny all request except from specified ip address.
    """
    print ('===Setting up firewall===')
    sudo ('ufw disable')
    sudo ('ufw reset')
    sudo ('ufw default deny incoming')
    sudo ('ufw default allow outgoing')
    sudo ('ufw allow ssh')
    sudo ('ufw enable')

def setup_pip_require ():
    """
    Setup pip requirements.
    """
    print('=== SETUP PIP REQUIREMENTS===')
    run ("workon %s && pip install -r %s" %(env.REMOTE_VIRTUALENV_NAME, env.PIP_REQUIREMENTS_PATH))
    
def setup_sys_installs():
    """
    Setup system necessaries libraries.
    """
    print('=== SETUP LIBRARIES ====')
    sudo('apt-get -y update')
    sudo('apt-get -y install build-essential gcc scons libreadline-dev sysstat iotop git-core zsh python-dev locate python-software-properties libssl-dev make pgbouncer libmemcache0 python-memcache libyaml-0-2 python-yaml python-numpy python-scipy python-imaging curl monit')

def setup ():
    """
    Install for all the prequisitions.
    """
    setup_sys_installs ()
    setup_repo ()    
    setup_pip_require ()

def deploy_soft ():
    """
    Soft deploy without restarting servers.
    """
    git_pull ();
    migrate_database ();

def deploy (copy_asserts=False,full=True):
    """
    Deploy code to production server.
    """
    git_pull ()
    deploy_nginx (full)
    deploy_gunicorn (full)
    deploy_supervisor (full)

def stage (copy_asserts=False,full=True):
    """
    Deploy code to the staging server.
    """
    staging ()
    git_pull ()
    restart_nginx ()
    restart_gunicorn ()

# ======================================================================
# Configurations.
# ======================================================================
def deploy_supervisor (restart=True):
    print ('===deploy supervisor===')
    configure_supervisor ()
    if restart:
        reload_supervisor ()

def deploy_gunicorn (restart=True):
    print ('===deploy gunicorn===')
    configure_gunicorn ()
    if restart:
        restart_gunicorn ()

def deploy_nginx (restart=True):
    print ('===deploy nginx===')
    configure_nginx ()
    if restart:
        restart_nginx ()
def deploy_redis (restart=True):
    print ('===deploy redis===')
    configure_redis ()
    if restart:
        restart_redis ()

def start_supervisor ():
    print ('===start supervisor===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run ('workon ohbooklist && supervisord')
    
def reload_supervisor ():
    print ('===reload supervisor===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run ('workon ohbooklist && supervisorctl reload')

def configure_supervisor ():
    print ('===configure supervisor===')
    put ("server_configs/%s/supervisor/supervisord.conf"%env.servername, "/etc/supervisord.conf", use_sudo=True)

def restart_gunicorn ():
    print ('===restart gunicorn===')
    with cd(env.REMOTE_CODEBASE_PATH):
        with settings(warn_only=True):
            run('workon ohbooklist && supervisorctl restart gunicorn_%s'%env.servername)

def stop_gunicorn ():
    print ('===stop gunicorn===')
    with cd(env.REMOTE_CODEBASE_PATH):
        with settings(warn_only=True):
            run('workon ohbooklist && supervisorctl stop gunicorn_%s'%env.servername)

def restart_celery ():
    print ('===restart celery===')
    with cd(env.REMOTE_CODEBASE_PATH):
        with settings(warn_only=True):
            run('workon ohbooklist && supervisorctl restart celery')

def stop_celery ():
    print ('===stop celery===')
    with cd(env.REMOTE_CODEBASE_PATH):
        with settings(warn_only=True):
            run('workon ohbooklist && supervisorctl stop celery')

def configure_nginx (restart=True):
    print ('===configure nginx===')
    put ("server_configs/%s/nginx/ohbooklist.nginx.conf"%env.servername, "/etc/nginx/sites-available/ohbooklist.conf", use_sudo=True)
    with(settings(warn_only=True)):
        sudo ("ln -s /etc/nginx/sites-available/ohbooklist.conf /etc/nginx/sites-enabled/ohbooklist.conf")

def restart_nginx ():
    print ('===restart nginx===')
    sudo ("/etc/init.d/nginx restart")

def restart_memcached ():
    print ('===restart memcached===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run('workon ohbooklist && supervisorctl restart memcached')

def stop_memcached ():
    print ('===stop memcached===')
    with cd(env.REMOTE_CODEBASE_PATH):
        run('workon ohbooklist && supervisorctl stop memcached')
        
def configure_gunicorn (supervisor=True):
    print ('===configure gunicorn===')
    if supervisor:
        put ('server_configs/%s/supervisor/supervisord.conf'%env.servername, '/etc/supervisord.conf', use_sudo=True)

def restart_redis ():
    print ('===start redis===')
    sudo ('/etc/init.d/redis-server restart')

def stop_redis ():
    print ('===stop redis===')
    sudo ('/etc/init.d/redis-server stop')

def start_redis ():
    print ('===stop redis===')
    sudo ('/etc/init.d/redis-server start')

def configure_redis ():
    print ('===configure redis===')
    put ('server_configs/%s/redis/redis.conf'%env.servername, '/etc/redis/redis.conf', use_sudo=True)

    
def configure_mysql_utf8 ():
    print ('===configure mysql utf8===')
    put ('server_configs/%s/mysql/mysql_utf8.cnf'%env.servername, '/etc/mysql/conf.d/mysql_utf8.cnf', use_sudo=True)

def restart_mysql ():
    print ('===restart mysql===')
    sudo ('restart mysql')

def start_mysql ():
    print ('===start mysql===')
    sudo ('start mysql')

def stop_mysql ():
    print ('===stop mysql===')
    sudo ('stop mysql')

def install_memcached ():
    sudo ('apt-get install libmemcached-dev')
    sudo ('apt-get install memcached')
    sudo ('workon ohbooklist && pip install python-memcached')
        
