# $Id: IniLoader.py 1728 2020-01-15 13:19:01Z  $
#
# Cascaded .ini file loader
# Load an ini file in the following procession. Stop on success.
#  -  filename given as argument
#  - <caller_name>.<hostname>.ini
#  - <caller_name>.default.ini
#
# By convention, the caller is set to the name of the calling program.


import configparser
import os


class IniLoader(object):
    @classmethod
    def load(cls, caller, fname=False):
        if bool(fname):
            if os.path.exists(fname):
                config = configparser.ConfigParser(interpolation=None)
                config.read(fname)
                return config
            else:
                print("Cannot find %s , bye." % fname)
                return False

        host_specific_ini = "%s.%s.ini" % (caller, os.popen('hostname').read().strip())
        default_ini = "%s.default.ini" % caller
        if os.path.exists(host_specific_ini):
            ini = host_specific_ini
        else:
            if os.path.exists(default_ini):
                ini = default_ini
            else:
                print("No default or host specific ini file! Bye..")
                return False

        config = configparser.ConfigParser(interpolation=None)
        config.read(ini)

        return config
