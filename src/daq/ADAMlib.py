#!/usr/bin/env python3
"""
Implemented devices:

 ADAM 4017 (Analog in)
 ADAM 4021 (Analog out)

 Based on ADAM.py by jah
 Partially rewritten for python3
 2021/12 hs

 Instantiate an ADAMConnection first with proper serial params.
 Then instantiate each ADAM class, passing the connection as first argument.

"""

import os
import sys
import logging
from time import sleep

try:
    from .BaseInstrument import BaseInstrument
except ImportError:
    sys.path.append(os.path.join('../lib'))
    from BaseInstrument import BaseInstrument


def dec2hex(d):
    """
    Convert decimal to two character upper case hex (for ADAM addressing)
    """
    try:
        dec = int(d)
        if not 0 <= dec <= 255:
            raise RuntimeError("Invalid ADAM address:%d" % dec)
        hx = hex(dec).upper()[-2:]
        if hx[0] == 'X':
            return "0" + hx[1]
        return hx
    except:
        return None


def hex2int(hexs):
    """
    Convert two's complement hex string (four chars, e.g. 10FF)
    to integer (range -32768 - 32767).
    """
    try:
        print("Converting:%s" % hexs)
        i = int(hexs, 16)
        if i > 32767:
            i -= 65536
        return i
    except:
        return None


class ADAMConnection(BaseInstrument):

    def __init__(self, init_hash):
        super(ADAMConnection, self).__init__(init_hash)
        # self.DEBUG = True #init_hash['DEBUG']
        self.checksum = False
        self.EOLWRITE = '\r'


class ADAM(object):
    QUERY = '$'
    COMMAND = '%'

    HELO = {'PING': '2',
            'MODEL': 'M'
            }

    def __init__(self, connection, adambase):
        self.conn = connection
        self.ibase = int(adambase)
        self.hbase = dec2hex(adambase)
        self.quicksleep = 1.0
        self.shortsleep = 2.0
        self.longsleep = 5.0
        self.checksum = False
        self.DEBUG = True

    def _initdevice(self):
        raise BaseException("Implement me in actual subclass")

    def _valid_response_prefix(self):
        res = "!%.2X" % self.ibase
        logging.debug("VALID prefix:%s" % res)
        return res

    def _response_valid(self, line):
        logging.debug("Comparing prefix:%s" % (line.strip()[0:3]))
        if line.strip()[0:3] == self._valid_response_prefix():
            return True

        return False

    def get_model(self):
        cmd = "%s%.2X%s" % (self.QUERY, self.ibase, self.HELO['MODEL'])
        res = self.send_command(cmd)
        if res:
            return res

        return "Unknown"

    def send_command(self, cmd):
        res = self.conn.send_command(cmd)
        return res

    def shutdown(self):
        self.conn.shutdown()


class ADAM4015(ADAM):
    """
      ADAM 6 ch RTD input module
    """

    def __init__(self, connection, adambase, scale=None, chs_to_enable=None):
        super(ADAM4015, self).__init__(connection, adambase)
        if chs_to_enable is None:
            chs_to_enable = []
        self.type = "4015"
        self._initdevice(scale, chs_to_enable)

    def _fromHex(self, chn, hexs):
        """
        Return value in Volts based on channel number and A/D conversion
        results as two complement (in hex)

        Revision history:
            2007-10-25 also unipolar range gives same reading as bipolar!
        """
        i = hex2int(hexs)
        rng = self.rng[chn]
        if i < 0:
            return -i * rng[0] / 32768.
        return i * rng[1] / 32767.

    def _initdevice(self, scale, chs_to_enable):

        self.checksum = '0'
        if self.conn.checksum:
            self.checksum = '4'

        fmat = "0"
        self.inHex = False
        self.toV = {}
        for i in range(8):
            self.toV[i] = 1.

        rng = '00'  # self.input_range_dict[str(sc)]

        cmd = "%%%.2X%.2X%s06%s%s" % (self.ibase, self.ibase, rng, self.checksum, fmat)
        res = self.send_command(cmd)
        logging.debug("Scale init returned:%s" % res)

        if res.__len__() == 0:
            logging.error("Couldn't connect to ADAM")
            sys.exit()

        sleep(self.shortsleep)  # some sleep required

        self.eqs = {}
        for ch in chs_to_enable:
            try:
                self.eqs[ch] = compile(conv_eqs[ch], 'adc_eq', 'eval')
            except:
                self.eqs[ch] = compile("v*1.", 'adc_eq', 'eval')

        sleep(self.longsleep)
        self.enabled = chs_to_enable[:]
        self.enabled.sort()  # added 2008-01-18
        self.SetMultiplexing(self.enabled)
        self.rawreadings = []  # raw (not in units) from ADAM

    def SetMultiplexing(self, chs_to_enable):
        """
        Disable/enable channels for multiplexing (faster read).
        By default, all the channels will be enabled (i.e.
        chs_to_enable=[0,1,2,3,4,5,6,7])

        Command sent: $AA5VV (VV=chs to enable as hex)
        Seems to require some wait before next cmd
        """
        # form a decimal value from channels...
        v = 0
        for ch in chs_to_enable:
            v += pow(2, ch)

        # and convert it to hex
        vhex = dec2hex(v)
        cmd = "$%.2X5%s" % (self.ibase, vhex)
        self.send_command(cmd)
        self.enabled = chs_to_enable
        sleep(self.shortsleep)

    def GetLatestRawReadings(self):
        return self.rawreadings

    def GetTemp(self, ch=0):
        """
        Return temperature in ºC reading of channel ch
        """
        if not 0 <= ch <= 7:
            logging.error("Illegal ADAM Analog Input ch:%d" % ch)
            raise ADAM_ValueError("Illegal ADAM Analog Input ch:%d" % ch)

        cmd = "#00%d" % ch
        resp = self.conn.send_command(cmd)
        logging.debug(f"ADAM response for command {cmd}: {resp}")

        return float(resp[1:])

    def GetAllTemps(self):
        """
        Return temperature in ºC reading of all channels
        """

        cmd = "#00"
        resp = self.conn.send_command(cmd)
        logging.debug(f"ADAM response for command {cmd}: {resp}")

        return [float(resp[1+i:i+7]) for i in range(0, len(resp)-1, 7)]

    def ReadChRanges(self):
        """
        Get channel ranges to be used in fromHex()

        Set var self.ranges[]

        Revision history:
            2007-10-29 bug fix (self.rng)
        """
        self.rng = []
        cmd = "$%.2X2" % self.ibase

        s = self.send_command(cmd)
        for i in range(8):
            self.rng.append(self.ch_ranges[s[3:5]])


if __name__ == '__main__':
    print("Import me!")
