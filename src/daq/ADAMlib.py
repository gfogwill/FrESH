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

import os, sys, traceback, re
from time import sleep

try:
    from .BaseInstrument import BaseInstrument
    from .misclib import dec2hex, hex2int
except:
    sys.path.append(os.path.join('../lib'))
    from BaseInstrument import BaseInstrument
    from misclib import dec2hex, hex2int


class ADAMConnection(BaseInstrument):

    def __init__(self, init_hash):
        super(ADAMConnection, self).__init__(init_hash)
        # self.DEBUG = True #init_hash['DEBUG']
        self.checksum = False
        self.EOLWRITE = '\r'


class ADAM(object):
    QUERY = '$'
    COMMD = '%'

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
        if self.DEBUG: print("VALID prefix:%s" % res)
        return res

    def _response_valid(self, line):
        if self.DEBUG: print("Comparing prefix:%s" % (line.strip()[0:3]))
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


class ADAM4021(ADAM):
    # output ranges
    dac_ranges = {'0-10V': '32', '0-20mA': '30', '4-20mA': '31'}

    def __init__(self, connection, adambase, range='0-10V'):
        super(ADAM4021, self).__init__(connection, adambase)
        self.range = range
        self.checksum = '00'
        self._initdevice()

    def _initdevice(self):
        print("---->Initializing...")
        errors = 0
        cmd = "%s%.2X%s" % (self.QUERY, self.ibase, self.HELO['PING'])
        res = self.send_command(cmd)
        if not self._response_valid(res):
            errors += 1
            print("Bah, got:%s  -> %d errors" % (res, errors))
            return errors

        cmd = "%%%.2X%.2X%s06%s" % (self.ibase, self.ibase, self.dac_ranges[self.range], self.checksum)
        res = self.send_command(cmd)
        sleep(self.quicksleep)
        ret = self.SetOutput(0, True)
        print("Output initialized to %f" % ret)
        return

    def GetSetValue(self):
        cmd = "$%.2X6" % self.ibase
        res = self.send_command(cmd)
        if res[0] != '!':
            return None  # something wrong
        return float(res[3:])

    def SetOutput(self, value, at_startup=False):
        '''
         Value must be in the form "00.000"
        '''
        # FCKING BULLSHIT PYTHON!!
        fs = "%.3f" % value
        if int(value) < 10:
            padval = "0%s" % fs
        else:
            padval = str(fs)

        cmd = "#%.2X%s" % (self.ibase, padval)
        res = self.send_command(cmd)
        if at_startup and res.find('>') >= 0:
            cmd = "$%.2X4" % self.ibase
            self.send_command(cmd)
        return self.GetSetValue()


class ADAM4017(ADAM):
    ch_ranges = {
        '00': (-.015, .015), '01': (-.05, .05), '02': (-.1, .1), '03': (-.5, .5),
        '06': (-20, 20), '07': (4., 20.), '08': (-10., 10.), '09': (-5., 5.),
        '0A': (-1., 1.), '0B': (-.5, .5), '0C': (-.15, .15), '0D': (-20., 20.),
        '0E': (0., 760.), '0F': (0., 1370.), '10': (-100., 400.), '11': (0., 1000.),
        '12': (500., 1750.), '13': (500., 1750.), '14': (500., 1800.),
        '15': (-15., 15.), '20': (-50, 150), '21': (0, 100),
        '22': (0, 200), '23': (0, 400), '24': (-200, 200), '25': (-50, 150), '26': (0, 100),
        '27': (0, 200), '28': (0, 400), '29': (-200, 200), '2A': (-40, 160), '2B': (-30, 120),
        '2C': (-80, 100), '2D': (0, 100), '48': (0., 10), '49': (0., 5.),
        '4A': (0., 1.), '4B': (0., .5), '4C': (0., .15), '4D': (0., 20.), '55': (0., 15.),
    }
    # 0E - 14: thermocouple ranges
    # 2? ranges are for PT-100: not used
    mV_ranges = ['02', '03', '07', '0B', '0C', '0D', '4B', '4C', '4D']  # also mA

    def __init__(self, connection, adambase, scale=None, chs_to_enable=[0, 1, 2, 3, 4, 5, 6, 7], conv_eqs=None):
        super(ADAM4017, self).__init__(connection, adambase)
        self.input_range_dict = {"0.15": "0C", "0.5": "0B", "1": "0A", "5": "09", "10": "08", "4-20mA": "07"}
        self._initdevice(scale, chs_to_enable, conv_eqs)

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

    def _initdevice(self, scale, chs_to_enable, conv_eqs):
        assert conv_eqs is None or type(conv_eqs) == type({})
        self.checksum = '0'
        if self.conn.checksum: self.checksum = '4'

        # reg exp to get data from Analog Data In (all channels)
        self.get_readings_re = re.compile(r'''
         [+|-]          # starts with + or -
         [\d.]*         # digit or decimal point
         [\b]*          # white space (should not occur)
         ''', re.VERBOSE)

        rng = "00"
        fmat = "0"
        sc = 10
        self.inHex = False
        self.toV = {}
        for i in range(8):
            self.toV[i] = 1.

        if type(scale) == type({}):
            sc = 0
            for i in scale:
                try:
                    if int(scale[i]) > sc:
                        sc = int(scale[i])
                except:
                    pass
        elif scale is not None:
            sc = scale

        rng = self.input_range_dict[str(sc)]
        if rng in ["0B", "0C"]:
            for i in range(8):
                self.toV[i] = 1e-3  # convert mv to V

        cmd = "%%%.2X%.2X%s06%s%s" % (self.ibase, self.ibase, rng, self.checksum, fmat)
        res = self.conn.send_command(cmd)
        if self.DEBUG: print("Scale init returned:%s" % res)
        sleep(self.shortsleep)  # some sleep required

        rng = None
        onerng = False
        if type(scale) == type("") or type(scale) == type(10):
            onerng = True
            rng = self.input_range_dict[str(scale)]

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
        # self.ReadChRanges()  # read from ADAM
        self.rawreadings = []  # raw (not in units) from ADAM

    def SetMultiplexing(self, chs_to_enable):
        '''
        Disable/enable channels for multiplexing (faster read).
        By default all the channels will be enabled (i.e.
        chs_to_enable=[0,1,2,3,4,5,6,7])

        Command sent: $AA5VV (VV=chs to enable as hex)
        Seems to require some wait before next cmd
        '''
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

    def GetReadings(self):
        """
        Return voltage (in volts) readings for all the enabled channels
        as a dict of floats, e.g. {0:None,1:value,...,7:None}.

        Data returned by ADAM in format (no spaces???):
        +1.1111+2.2222+...(cr)
        """
        cmd = "#%.2X" % self.ibase
        for iii in range(3):
            xx = cmd[:]
            s = self.send_command(cmd)
            cmd = xx
            if not s: return None
            try:
                if not self.inHex:  # == 4017,4015,4017+
                    res = [float(x) for x in self.get_readings_re.findall(s)]
                    for i, ch in enumerate(self.enabled):
                        res[i] = res[i] * self.toV[ch]
                else:
                    res = []
                    for i in range(8):
                        res.append(self._fromHex(i, s[1 + i * 4:1 + i * 4 + 4]))
                break
            except:
                print("--stacktrace start")
                print(traceback.print_exc())
                print("--end")
                sout = "Could not parse data:'%s'" % s
                print(sout)
                if iii == 2:
                    return None

        ret = {}
        for i in range(8):
            v = None
            if i in self.enabled and len(res):
                v = res.pop(0)
            elif self.inHex:  # always gives values for all the chans
                res.pop(0)
            ret[i] = v

        self.rawreadings = ret
        # print(ret)
        return ret

    def GetReadingsInUnits(self):
        '''
        Return all the enabled channel readings converted to
        units (not as voltages) as a dict of floats, e.g. {x:value,}
        '''
        volts = self.GetReadings()
        ret = {}
        for ch in volts:
            v = volts[ch]
            if v == None: continue
            ret[ch] = eval(self.eqs[ch])
        return ret

    def GetAReading(self, ch=0):
        '''
        Return voltage reading of channel ch
        '''
        if not 0 <= ch <= 7:
            raise ADAM_ValueError("Illegal ADAM Analog Input ch:%d" % ch)
        cmd = "#%.2X%d" % (self.ibase, ch)
        resp = self.send_command(cmd)

        if not self.inHex:
            return self.toV[ch] * float(resp[1:])
        return self._fromHex(ch, resp[1:])

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


class ADAM4015(ADAM):
    """
      ADAM 6 ch RTD input module
    """

    def __init__(self, connection, adambase, scale=None, chs_to_enable=[0, 1], conv_eqs=None):
        super(ADAM4015, self).__init__(connection, adambase)
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
        if self.conn.checksum: self.checksum = '4'

        # reg exp to get data from Analog Data In (all channels)
        self.get_readings_re = re.compile(r'' '\n'
                                          r'         [+|-]          # starts with + or -' '\n'
                                          r'         [\d.]*         # digit or decimal point' '\n'
                                          r'         [\b]*          # white space (should not occur)' '\n'
                                          r'         ', re.VERBOSE)

        fmat = "0"
        sc = 10
        self.inHex = False
        self.toV = {}
        for i in range(8):
            self.toV[i] = 1.

        if type(scale) == type({}):
            sc = 0
            for i in scale:
                try:
                    if int(scale[i]) > sc:
                        sc = int(scale[i])
                except:
                    pass

        elif scale is not None:
            sc = scale

        rng = '00'  # self.input_range_dict[str(sc)]

        cmd = "%%00%.2X%s06%s%s" % (self.ibase, rng, self.checksum, fmat)
        res = self.send_command(cmd)
        if self.DEBUG:
            print("Scale init returned:%s" % res)
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
        '''
        Disable/enable channels for multiplexing (faster read).
        By default all the channels will be enabled (i.e.
        chs_to_enable=[0,1,2,3,4,5,6,7])

        Command sent: $AA5VV (VV=chs to enable as hex)
        Seems to require some wait before next cmd
        '''
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

    def GetAReading(self, ch=0):
        """
        Return voltage reading of channel ch
        """
        if not 0 <= ch <= 7:
            raise ADAM_ValueError("Illegal ADAM Analog Input ch:%d" % ch)

        cmd = "#00%d" % (ch)

        resp = self.conn.send_command(cmd)

        return resp  # self._fromHex(ch, resp[1:])

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
    from src.daq.IniLoader import IniLoader

    ini = IniLoader.load('perezfo', '../../notebooks/test.ini')

    conn = ADAMConnection(ini['SERIAL'])

    ain = ADAM4015(conn, 0x24)
    ain.GetAReading(ch=1)
